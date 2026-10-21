"""
gif.py — search Giphy and post a GIF.

    !gif <subject>       posts a matching GIF straight away. It picks at random from Giphy's top few matches,
                         so asking again gives a different one. Be as detailed as you like.
    !gifp <subject>      (alias !gifpick) shows results with buttons so you can flip through and choose:
                         ◀ Back · Next ▶ · 🎲 Random · ✅ Post · ✖ Cancel. Only the person who ran it can press
                         them. ✅ turns that message into the GIF; ✖ (or 90 seconds of nothing) removes it.
    !gifcheck            (admin) test the Giphy key and show what Giphy says

If a long, detailed subject finds nothing, it retries once with the first few words and says so.
Uses one Giphy search per command (new Giphy keys are limited to roughly 100 calls an hour). Repeated searches
within 10 minutes reuse the saved results, and the bot counts its own calls so it stops a little before the limit.

Env vars
    GIPHY_API_KEY     your Giphy key
    GIF_TOP           !gif picks randomly from this many top matches (default 5; set 1 to always post the top one)
    GIF_RATING        highest rating allowed: g, pg, pg-13 (default) or r. Age-restricted channels always allow r.
    GIF_HOURLY_LIMIT  most Giphy searches the bot makes per hour (default 80)
"""

import os
import re
import time
import random
import asyncio
import logging
from collections import deque
from urllib.parse import urlparse

import aiohttp
import discord
from discord.ext import commands

log = logging.getLogger(__name__)

BUILD = "g3"
API_URL = "https://api.giphy.com/v1/gifs/search"
RATINGS = ["g", "pg", "pg-13", "r"]
DEFAULT_RATING = os.getenv("GIF_RATING", "pg-13").lower()
if DEFAULT_RATING not in RATINGS:
    DEFAULT_RATING = "pg-13"
HOURLY_LIMIT = int(os.getenv("GIF_HOURLY_LIMIT", "80"))
RESULTS = 25                 # one search fetches this many; browsing is then free
TOP = max(1, min(RESULTS, int(os.getenv("GIF_TOP", "5"))))   # !gif picks randomly from this many best matches
CACHE_TTL = 600
USER_COOLDOWN = 5
VIEW_TIMEOUT = 90
MAX_BYTES = 8_000_000        # skip enormous files; Discord struggles to show them
COLOR = 0x00CCFF


async def with_deadline(coro, timeout):
    """Await `coro` but give up after `timeout` seconds even if it ignores cancellation."""
    task = asyncio.ensure_future(coro)
    task.add_done_callback(lambda t: t.cancelled() or t.exception())
    try:
        done, _ = await asyncio.wait({task}, timeout=timeout)
    except asyncio.CancelledError:
        task.cancel()
        raise
    if task in done:
        return task.result()
    task.cancel()
    raise asyncio.TimeoutError(f"gave up after {timeout}s")


# ---------- helpers ----------

def clean_subject(text):
    t = re.sub(r"<[@#&!]*\d+>", "", str(text or ""))
    return " ".join(t.replace("@everyone", "").replace("@here", "").split())[:100]


def pick_gif(item):
    """The best playable GIF URL for one Giphy result, or None. Prefers the small versions so they load fast."""
    images = item.get("images") or {}
    for key in ("downsized_medium", "downsized", "fixed_height", "original"):
        img = images.get(key) or {}
        url = img.get("url")
        try:
            size = int(img.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        host = (urlparse(url).hostname or "") if isinstance(url, str) else ""
        if url and url.startswith("https://") and host.endswith("giphy.com") and size <= MAX_BYTES:
            return url
    return None


def parse_results(data):
    out = []
    for item in (data or {}).get("data") or []:
        url = pick_gif(item)
        if url:
            page = item.get("url") if isinstance(item.get("url"), str) and item["url"].startswith("https://giphy.com/") else None
            out.append({"url": url, "title": " ".join(str(item.get("title") or "").split())[:100], "page": page})
    return out


def api_error_message(status):
    if status in (401, 403):
        return "Giphy rejected the API key. Check `GIPHY_API_KEY` in Railway."
    if status == 429:
        return "Giphy says we've used up the hourly limit. Try again in a bit."
    return f"Giphy had a problem (HTTP {status}). Try again in a moment."


class GifError(Exception):
    pass


class GifView(discord.ui.View):
    def __init__(self, owner_id, subject, gifs, name, note=""):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.owner_id, self.subject, self.gifs, self.name, self.note = owner_id, subject, gifs, name, note
        self.i = 0
        self.message = None

    def embed(self):
        g = self.gifs[self.i]
        e = discord.Embed(title=discord.utils.escape_markdown(g["title"] or self.subject)[:200], url=g["page"],
                          color=COLOR,
                          description=f"Results for **{discord.utils.escape_markdown(self.subject)}**{self.note}")
        e.set_image(url=g["url"])
        e.set_footer(text=f"{self.i + 1} of {len(self.gifs)} · Powered by GIPHY · only {self.name} can use these buttons")
        return e

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Those buttons are for whoever searched. Use `!gif <subject>` "
                                                    "to find your own.", ephemeral=True)
            return False
        return True

    async def _show(self, interaction):
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Back", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def back(self, interaction, button):
        self.i = (self.i - 1) % len(self.gifs)
        await self._show(interaction)

    @discord.ui.button(label="Next", emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):
        self.i = (self.i + 1) % len(self.gifs)
        await self._show(interaction)

    @discord.ui.button(label="Random", emoji="🎲", style=discord.ButtonStyle.secondary)
    async def shuffle(self, interaction, button):
        if len(self.gifs) > 1:
            self.i = random.choice([n for n in range(len(self.gifs)) if n != self.i])
        await self._show(interaction)

    @discord.ui.button(label="Post", emoji="✅", style=discord.ButtonStyle.success)
    async def post(self, interaction, button):
        self.stop()
        await interaction.response.edit_message(content=f"{self.gifs[self.i]['url']}\n-# GIF via GIPHY · {self.name}",
                                                embed=None, view=None)

    @discord.ui.button(label="Cancel", emoji="✖️", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction, button):
        self.stop()
        await interaction.response.defer()
        await self._remove()

    async def _remove(self):
        try:
            if self.message:
                await self.message.delete()
        except discord.HTTPException:
            pass

    async def on_timeout(self):
        await self._remove()


class Gif(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._session = None
        self._calls = deque()        # times of our Giphy searches, to stay under the hourly limit
        self._cache = {}
        self._last = {}
        self._recent = {}            # (channel, subject) -> the GIF last posted, so repeats differ
        log.warning("Gif build %s: key %s, rating %s, hourly limit %d", BUILD,
                    "set" if os.environ.get("GIPHY_API_KEY") else "NOT SET", DEFAULT_RATING, HOURLY_LIMIT)

    async def cog_unload(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ---------- Giphy ----------

    def _http(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _fetch(self, params):
        """-> (status, json, headers). Overridable in tests."""
        async with self._http().get(API_URL, params=params, timeout=aiohttp.ClientTimeout(total=8)) as r:
            try:
                data = await r.json(content_type=None)
            except Exception:
                data = {}
            return r.status, data, dict(r.headers)

    def _budget_left(self):
        now = time.time()
        while self._calls and now - self._calls[0] > 3600:
            self._calls.popleft()
        return HOURLY_LIMIT - len(self._calls)

    def _rating_for(self, channel):
        allow_r = False
        try:
            allow_r = bool(channel.is_nsfw())
        except Exception:
            pass
        return "r" if allow_r else DEFAULT_RATING

    async def _search(self, subject, rating):
        """-> a list of {url, title, page}. Raises GifError with a message that's safe to show."""
        key = os.environ.get("GIPHY_API_KEY")
        if not key:
            raise GifError("No `GIPHY_API_KEY` is set, so I can't search for GIFs.")
        ck = (subject.lower(), rating)
        hit = self._cache.get(ck)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return hit[1]
        if self._budget_left() <= 0:
            wait = int(3600 - (time.time() - self._calls[0])) // 60 + 1
            raise GifError(f"I've made as many GIF searches as I'm allowed this hour. Try again in about {wait} min.")
        self._calls.append(time.time())
        try:
            status, data, _ = await with_deadline(
                self._fetch({"api_key": key, "q": subject, "limit": RESULTS, "rating": rating, "lang": "en"}), 10)
        except asyncio.TimeoutError:
            raise GifError("Giphy took too long to answer. Try again.")
        except Exception as e:
            log.warning("Gif: request failed (%s: %s)", type(e).__name__, e)
            raise GifError("I couldn't reach Giphy right now.")
        if status != 200:
            log.warning("Gif: Giphy answered HTTP %s", status)
            raise GifError(api_error_message(status))
        gifs = parse_results(data)
        self._cache[ck] = (time.time(), gifs)
        if len(self._cache) > 100:
            self._cache.pop(next(iter(self._cache)))
        return gifs

    # ---------- commands ----------

    def _too_fast(self, user_id):
        now = time.time()
        if now - self._last.get(user_id, 0) < USER_COOLDOWN:
            return True
        self._last[user_id] = now
        return False

    async def _find(self, ctx, subject):
        """Search; if a long, detailed subject finds nothing, retry once with its first few words.
        -> (gifs, the subject actually searched). Raises GifError with a message that's safe to show."""
        rating = self._rating_for(ctx.channel)
        gifs = await self._search(subject, rating)
        used, words = subject, subject.split()
        if not gifs and len(words) > 3:
            used = " ".join(words[:3])
            gifs = await self._search(used, rating)
        return gifs, used

    async def _lookup(self, ctx, subject, usage):
        """Shared by both commands: clean up the subject, search, and explain any problem.
        -> (subject, gifs, subject actually searched) or None"""
        if not ctx.guild:
            return None
        subject = clean_subject(subject)
        if not subject:
            await ctx.send(usage)
            return None
        if self._too_fast(ctx.author.id):
            await ctx.send("One moment, then try again.", delete_after=5)
            return None
        async with ctx.typing():
            try:
                gifs, used = await self._find(ctx, subject)
            except GifError as e:
                await ctx.send(str(e))
                return None
        if not gifs:
            await ctx.send(f"I couldn't find a GIF for **{discord.utils.escape_markdown(subject)}**.")
            return None
        return subject, gifs, used

    @commands.command(name="gif")
    async def gif(self, ctx, *, subject: str = None):
        """Post a matching GIF right away."""
        found = await self._lookup(ctx, subject, "What kind of GIF? `!gif <subject>`")
        if not found:
            return
        subject, gifs, used = found
        key = (getattr(ctx.channel, "id", 0), subject.lower())
        last = self._recent.get(key)
        pool = gifs[:TOP]
        pick = random.choice([g for g in pool if g["url"] != last] or pool)
        self._recent[key] = pick["url"]
        if len(self._recent) > 200:
            self._recent.pop(next(iter(self._recent)))
        note = f" · closest match for “{used}”" if used != subject else ""
        await ctx.send(f"{pick['url']}\n-# GIF via GIPHY · {ctx.author.display_name[:40]}{note}",
                       allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="gifp", aliases=["gifpick"])
    async def gifp(self, ctx, *, subject: str = None):
        """Flip through results with buttons and pick one."""
        found = await self._lookup(ctx, subject, "What kind of GIF? `!gifp <subject>`")
        if not found:
            return
        subject, gifs, used = found
        note = f"\n*Nothing matched the full phrase, so these are for “{used}”.*" if used != subject else ""
        view = GifView(ctx.author.id, used, gifs, ctx.author.display_name[:40], note)
        view.message = await ctx.send(embed=view.embed(), view=view,
                                      allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="gifcheck")
    @commands.has_guild_permissions(manage_guild=True)
    async def gifcheck(self, ctx):
        """(Admin) Test the Giphy key and show what Giphy says."""
        L = [f"**Build:** `{BUILD}`", f"**Rating:** `{DEFAULT_RATING}` (age-restricted channels allow `r`)"]
        key = os.environ.get("GIPHY_API_KEY")
        if not key:
            L.append("**Giphy key:** ❌ `GIPHY_API_KEY` isn't set")
        else:
            t0 = time.time()
            try:
                status, data, headers = await with_deadline(
                    self._fetch({"api_key": key, "q": "cat", "limit": 3, "rating": "g"}), 10)
                self._calls.append(time.time())
                if status == 200:
                    n = len(parse_results(data))
                    L.append(f"**Giphy key:** ✅ working, {n} usable result(s) in {time.time() - t0:.1f}s")
                else:
                    L.append(f"**Giphy key:** ❌ {api_error_message(status)}")
                rl = {k: v for k, v in headers.items() if k.lower().startswith("x-ratelimit")}
                if rl:
                    L.append("**Giphy's rate-limit headers:** " + ", ".join(f"`{k}: {v}`" for k, v in rl.items()))
            except Exception as e:
                L.append(f"**Giphy key:** ❌ `{type(e).__name__}`: {str(e)[:150]}")
        L.append(f"**Searches this hour:** {HOURLY_LIMIT - self._budget_left()} of my limit of {HOURLY_LIMIT}")
        await ctx.send(embed=discord.Embed(title="🎞️ GIF setup check", description="\n".join(L), color=COLOR),
                       allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(Gif(bot))
