"""
calm.py — !calm posts a random audio clip in the text channel.

    !calm              posts a random clip
    !calm @user        pings that person and posts a random clip (a name without the @ works too)
    !calmcheck         (admin) show which folder and clips the bot found

Put your audio files in a folder in the repo, e.g.  assets/calm/  (mp3 is the safest format). The bot picks one
at random each time and avoids repeating the clip it just used in that channel. Add or remove clips any time
by changing the folder; the bot picks up changes after a redeploy.

Where it looks (first one that has audio files wins):
    1. CALM_AUDIO_DIR            (Railway variable, if you set one)
    2. cogs/calm_audio/
    3. assets/calm/
    4. assets/audio/
    5. audio/   or   calm/        at the top of the repo
    6. last resort: any audio file anywhere in the project whose name starts with "calm"

Limits: one clip per person every 10 seconds, and the same person can't be pinged more than once every 20
seconds. Clips bigger than the server's upload limit are skipped (10 MB on a normal server).
"""

import os
import random
import time
import logging
from pathlib import Path

import discord
from discord.ext import commands

log = logging.getLogger(__name__)

BUILD = "c1"
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".flac"}
TARGET_MESSAGE = "{mention} calm down 😌"      # what's posted with the clip when someone is pinged
AUTHOR_COOLDOWN = 10
TARGET_COOLDOWN = 20
DEFAULT_LIMIT = 10 * 1024 * 1024                # Discord's normal upload limit for bots
RESCAN_SECONDS = 120


def audio_in(folder):
    try:
        return sorted(p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXT)
    except OSError:
        return []


def find_clips(here=None, env=None):
    """-> (folder, clips, how). Checks the usual places, then searches the project for files named calm*."""
    here = Path(here or os.path.dirname(os.path.abspath(__file__)))
    env = os.getenv("CALM_AUDIO_DIR") if env is None else env
    root = here.parent
    candidates = ([Path(env)] if env else []) + [here / "calm_audio", root / "assets" / "calm",
                                                  root / "assets" / "audio", root / "audio", root / "calm"]
    for c in candidates:
        clips = audio_in(c)
        if clips:
            return c, clips, "folder"
    skip = {".git", ".venv", "venv", "node_modules", "__pycache__", "playerdata"}
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).relative_to(root).parts)
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")] if depth < 5 else []
        found = sorted(Path(dirpath) / f for f in filenames
                       if f.lower().startswith("calm") and Path(f).suffix.lower() in AUDIO_EXT)
        if found:
            return Path(dirpath), found, "search"
    return (candidates[0] if candidates else root / "assets" / "calm"), [], "none"


def match_member(members, text):
    """Exact name match ignoring capitalization: username, then display name, then server nickname."""
    want = text.strip().casefold()
    if not want:
        return None
    for field in ("name", "global_name", "nick"):
        for m in members:
            if (getattr(m, field, None) or "").casefold() == want:
                return m
    return None


def human_size(n):
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{max(1, n // 1024)} KB"


class Calm(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._clips, self._folder, self._how, self._scanned = [], None, "none", 0.0
        self._last_clip = {}        # channel id -> the clip used last, so repeats differ
        self._author_at, self._target_at = {}, {}
        self._rescan()
        log.warning("Calm build %s: %d clip(s) in %s", BUILD, len(self._clips), self._folder)

    def _rescan(self):
        self._folder, self._clips, self._how = find_clips()
        self._scanned = time.time()

    def _clip_list(self):
        if time.time() - self._scanned > RESCAN_SECONDS:
            self._rescan()
        return self._clips

    async def _resolve_target(self, ctx, text):
        if ctx.message.mentions:
            return ctx.message.mentions[0]
        if text:
            return match_member(ctx.guild.members, text)
        return None

    @commands.command(name="calm")
    async def calm(self, ctx, *, who: str = None):
        """Post a random calming audio clip, optionally pinging someone."""
        if not ctx.guild:
            return
        now = time.time()
        if now - self._author_at.get(ctx.author.id, 0) < AUTHOR_COOLDOWN:
            return await ctx.send("Easy, give it a few seconds.", delete_after=5)
        clips = self._clip_list()
        if not clips:
            return await ctx.send("I don't have any clips yet. An admin needs to add audio files "
                                  "(see `!calmcheck`).")
        try:
            limit = ctx.guild.filesize_limit
        except Exception:
            limit = DEFAULT_LIMIT
        usable = [c for c in clips if c.exists() and c.stat().st_size <= limit]
        if not usable:
            return await ctx.send(f"All my clips are over this server's upload limit ({human_size(limit)}).")

        target = await self._resolve_target(ctx, who)
        if target is not None and now - self._target_at.get(target.id, 0) < TARGET_COOLDOWN:
            return await ctx.send("They've just been told to calm down. Give them a moment.", delete_after=6)

        last = self._last_clip.get(ctx.channel.id)
        clip = random.choice([c for c in usable if c != last] or usable)
        self._last_clip[ctx.channel.id] = clip
        if target is not None:
            text = TARGET_MESSAGE.format(mention=target.mention)
            mentions = discord.AllowedMentions(users=[target], everyone=False, roles=False, replied_user=False)
        else:
            text, mentions = None, discord.AllowedMentions.none()
        try:
            await ctx.send(text, file=discord.File(clip), allowed_mentions=mentions)
        except discord.Forbidden:
            return await ctx.send("I need the **Attach Files** permission in this channel to post audio.")
        except discord.HTTPException as e:
            log.warning("Calm: couldn't send %s (%s)", clip.name, e)
            return await ctx.send("Discord wouldn't accept that clip. It may be too large or an odd format.")
        self._author_at[ctx.author.id] = now
        if target is not None:
            self._target_at[target.id] = now

    @commands.command(name="calmcheck")
    @commands.has_guild_permissions(manage_guild=True)
    async def calmcheck(self, ctx):
        """(Admin) Show which folder and clips the bot found."""
        self._rescan()
        try:
            limit = ctx.guild.filesize_limit
        except Exception:
            limit = DEFAULT_LIMIT
        L = [f"**Build:** `{BUILD}`", f"**Folder:** `{self._folder}`" +
             (" (found by searching, since none of the usual folders had audio)" if self._how == "search" else ""),
             f"**Upload limit here:** {human_size(limit)}"]
        if not self._clips:
            L.append("**Clips:** ❌ none found. Put audio files (mp3 works best) in `assets/calm/` in the repo, "
                     "or set `CALM_AUDIO_DIR`, then redeploy.")
        else:
            L.append(f"**Clips:** ✅ {len(self._clips)} found")
            for c in self._clips[:15]:
                size = c.stat().st_size
                L.append(f"• `{c.name}` {human_size(size)}" + (" ⚠️ over the upload limit, will be skipped" if size > limit else ""))
            if len(self._clips) > 15:
                L.append(f"…and {len(self._clips) - 15} more")
        await ctx.send(embed=discord.Embed(title="😌 Calm clips", description="\n".join(L), color=0x7AB8F5),
                       allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(Calm(bot))
