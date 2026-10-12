"""
poop.py — a tiny cog: `!poop` in #bowel-updates pings one specific person.

    !poop                  posts "💩 @them I wanted to let you know that <you> has pooped."
    !poop it was a big one same, with your note added underneath as a quote
    !poopwho               (admin) show who it would ping and how it found them
    !poopset @user         (admin) pin the target to this exact person
    !poopset               (admin) un-pin, go back to finding them by name

Finding the person: it looks for TARGETS (default: idkk_9, then vivi) among the server's members, matching
exact names while ignoring capitalization. It checks, in order:
    1. their Discord USERNAME        (e.g. idkk_9)       <- most reliable, usernames are unique
    2. their global DISPLAY NAME
    3. their SERVER NICKNAME         (e.g. vivi)         <- can match more than one person
So it doesn't matter which name is which; either one finds them. Once found, the person's ID is remembered, so a
later nickname change won't break it. `!poopset @user` is the most reliable option, since it works from the person
themselves rather than a name.

Name lookup needs the bot's "Server Members Intent" turned on (Developer Portal + intents.members = True in code).
If that's off, use `!poopset @user` once instead, which doesn't need it.

Env vars (all optional)
    POOP_TARGETS       names to look for, comma separated. default: idkk_9,vivi
    POOP_USER_ID       pin the target by Discord user ID
    POOP_CHANNEL       channel name where !poop works. default: bowel-updates
    POOP_CHANNEL_ID    ...or the channel's ID, if you'd rather
    POOP_STATE_PATH    where the pin from !poopset is saved. default: data/poop.json (point at your Railway volume)
"""

import os
import json
import time
import logging

import discord
from discord.ext import commands

log = logging.getLogger(__name__)

TARGETS = [t.strip() for t in os.getenv("POOP_TARGETS", "idkk_9,vivi").split(",") if t.strip()]
CHANNEL_NAME = os.getenv("POOP_CHANNEL", "bowel-updates").strip().lstrip("#").lower()
CHANNEL_ID = int(os.getenv("POOP_CHANNEL_ID") or 0)
ENV_PIN = int(os.getenv("POOP_USER_ID") or 0)
DATA_DIR = os.getenv("POOP_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
STATE_PATH = os.getenv("POOP_STATE_PATH", os.path.join(DATA_DIR, "poop.json"))
COOLDOWN = 60            # seconds between uses by the same person, so the target isn't spammed
NOTE_MAX = 150


def match_member(members, targets):
    """Best match: exact name, ignoring case. Username beats display name beats server nickname, and earlier
    targets beat later ones. Returns (member, which field matched, whether it was ambiguous)."""
    wanted = [t.casefold() for t in targets]
    for field, label in (("name", "username"), ("global_name", "display name"), ("nick", "server nickname")):
        hits = [(wanted.index((getattr(m, field, None) or "").casefold()), m) for m in members
                if (getattr(m, field, None) or "").casefold() in wanted]
        if hits:
            hits.sort(key=lambda h: h[0])
            best = hits[0][0]
            return hits[0][1], label, sum(1 for h in hits if h[0] == best) > 1
    return None, None, False


def tidy(text, n):
    t = discord.utils.escape_markdown(discord.utils.escape_mentions(" ".join(str(text or "").split())))
    return t[:n]


class Poop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pin = ENV_PIN or None
        self._found = {}         # guild id -> (user id, how), remembered after the first successful lookup
        self._last = {}          # author id -> time of their last !poop
        self._save_error = None
        self._load()
        log.warning("Poop: channel '%s', looking for %s, pinned user: %s",
                    CHANNEL_ID or CHANNEL_NAME, TARGETS, self.pin or "none (finds by name)")

    # ---------- saved pin ----------

    def _load(self):
        try:
            with open(STATE_PATH) as f:
                self.pin = int(json.load(f).get("user_id") or 0) or self.pin
        except (FileNotFoundError, ValueError, OSError):
            pass

    def _save(self):
        try:
            os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"user_id": self.pin}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, STATE_PATH)
            self._save_error = None
            return True
        except Exception as e:
            self._save_error = f"{type(e).__name__}: {e}"
            log.error("Poop: could not save the pin to %s: %s", STATE_PATH, self._save_error)
            return False

    # ---------- finding the person ----------

    async def _resolve(self, guild):
        """-> (user id, how it was found) or (None, None)"""
        if self.pin:
            return self.pin, "pinned with !poopset"
        if guild.id in self._found:
            return self._found[guild.id]
        member, label, ambiguous = match_member(guild.members, TARGETS)
        if member is None:                        # not in the cache: ask Discord (needs the Members intent)
            for name in TARGETS:
                try:
                    found = await guild.query_members(name, limit=10)
                except Exception as e:
                    log.warning("Poop: member search for %r failed (%s: %s)", name, type(e).__name__, e)
                    continue
                member, label, ambiguous = match_member(found, TARGETS)
                if member:
                    break
        if member is None:
            return None, None
        if ambiguous:
            log.warning("Poop: more than one member matched; using %s (%s). Use !poopset @user to be sure.",
                        member, member.id)
        self._found[guild.id] = (member.id, f"matched by {label}")
        return member.id, f"matched by {label}"

    def _right_channel(self, channel):
        return (CHANNEL_ID and channel.id == CHANNEL_ID) or (not CHANNEL_ID and
                                                              getattr(channel, "name", "").lower() == CHANNEL_NAME)

    # ---------- commands ----------

    @commands.command(name="poop")
    async def poop(self, ctx, *, note: str = None):
        """Post a bowel update that pings the one person who needs to know."""
        if not ctx.guild:
            return
        if not self._right_channel(ctx.channel):
            where = (ctx.guild.get_channel(CHANNEL_ID) if CHANNEL_ID
                     else discord.utils.get(ctx.guild.text_channels, name=CHANNEL_NAME))
            return await ctx.send(f"💩 That only works in {where.mention if where else '#' + CHANNEL_NAME}.",
                                  delete_after=8)
        wait = COOLDOWN - (time.time() - self._last.get(ctx.author.id, 0))
        if wait > 0:
            return await ctx.send(f"Easy there. Try again in {int(wait) + 1}s.", delete_after=8)
        uid, _ = await self._resolve(ctx.guild)
        if uid is None:
            return await ctx.send(f"I couldn't find {' or '.join(TARGETS)} in this server. "
                                  "An admin can fix it with `!poopset @user`.", delete_after=15)
        self._last[ctx.author.id] = time.time()
        text = f"💩 <@{uid}> I wanted to let you know that **{tidy(ctx.author.display_name, 40)}** has pooped."
        if note and tidy(note, NOTE_MAX):
            text += f"\n> {tidy(note, NOTE_MAX)}"
        await ctx.send(text, allowed_mentions=discord.AllowedMentions(
            users=[discord.Object(id=uid)], everyone=False, roles=False, replied_user=False))

    @commands.command(name="poopwho")
    @commands.has_guild_permissions(manage_guild=True)
    async def poopwho(self, ctx):
        """(Admin) Show who !poop would ping, and how they were found. Doesn't ping them."""
        uid, how = await self._resolve(ctx.guild)
        if uid is None:
            return await ctx.send(f"Couldn't find {' or '.join(TARGETS)}. Use `!poopset @user`, and check the "
                                  "bot has the Server Members Intent if you want it to find people by name.")
        who = ctx.guild.get_member(uid)
        label = f"**{who.display_name}** (username `{who.name}`)" if who else "someone not in my member cache"
        await ctx.send(f"Would ping {label}, ID `{uid}`: {how}.", allowed_mentions=discord.AllowedMentions.none())

    @commands.command(name="poopset")
    @commands.has_guild_permissions(manage_guild=True)
    async def poopset(self, ctx, member: discord.User = None):
        """(Admin) Pin the target with `!poopset @user`, or clear the pin with just `!poopset`."""
        self._found.pop(ctx.guild.id, None)
        self.pin = member.id if member else None
        ok = self._save()
        msg = (f"Pinned. `!poop` will now ping **{member.display_name}**." if member
               else "Unpinned. I'll find them by name again.")
        if not ok:
            msg += " ⚠️ I couldn't save that to disk, so it will reset on the next restart."
        await ctx.send(msg, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(Poop(bot))
