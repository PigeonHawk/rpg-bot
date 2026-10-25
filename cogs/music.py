"""
Music cog — plays audio from YouTube in a voice channel.

Downloads each song's audio to a temp file with yt-dlp, then plays the file.
(Streaming the URL straight into FFmpeg gets 403 Forbidden from YouTube.)

Requirements:
    discord.py[voice]>=2.7.1, yt-dlp[default], deno  (requirements.txt)
    ffmpeg on the system (Railway: RAILPACK_DEPLOY_APT_PACKAGES=ffmpeg)

Optional env vars:
    YTDL_COOKIES_B64  — base64 of a cookies.txt (fixes "Sign in to confirm you're not a bot")
    YTDL_COOKIES      — path to a cookies.txt file instead

Commands (prefix):
    !join                   — join your voice channel
    !play <url or search>   (!p)
    !skip (!s), !pause, !resume, !queue (!q), !np, !volume <0-100> (!vol)
    !remove <position>, !clear, !stop, !leave (!dc)
"""

import asyncio
import base64
import os
import shutil
import tempfile
import traceback
from collections import deque
from dataclasses import dataclass

import discord
import yt_dlp
from discord.ext import commands

IDLE_TIMEOUT = 300          # seconds idle before leaving voice
MAX_QUEUE = 100
MAX_DURATION = 3 * 60 * 60  # refuse anything longer than 3 hours

DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "music_cache")
# wipe leftovers from a previous run
shutil.rmtree(DOWNLOAD_DIR, ignore_errors=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": False,
    "no_warnings": False,
    "verbose": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    # PO token provider (bgutil service on Railway) — gets past YouTube's bot check
    "extractor_args": {
        "youtubepot-bgutilhttp": {
            "base_url": [os.getenv("POT_PROVIDER_URL", "http://bgutil.railway.internal:4416")]
        }
    },
}

# ---- cookies (needed on Railway/datacenter IPs) ----
_cookie_b64 = os.getenv("YTDL_COOKIES_B64")
if _cookie_b64:
    _cookie_path = os.path.join(tempfile.gettempdir(), "yt_cookies.txt")
    with open(_cookie_path, "wb") as f:
        f.write(base64.b64decode(_cookie_b64))
    YTDL_OPTS["cookiefile"] = _cookie_path
    with open(_cookie_path, encoding="utf-8", errors="ignore") as f:
        _yt_lines = [l for l in f if "youtube.com" in l]
    print(f"[music] cookies loaded: {len(_yt_lines)} YouTube cookie lines")
elif os.getenv("YTDL_COOKIES"):
    YTDL_OPTS["cookiefile"] = os.getenv("YTDL_COOKIES")

# metadata/search only
ytdl_search = yt_dlp.YoutubeDL(YTDL_OPTS)
# actual downloading
ytdl_download = yt_dlp.YoutubeDL({
    **YTDL_OPTS,
    "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
    "overwrites": True,
})


@dataclass
class Track:
    title: str
    webpage_url: str
    duration: int | None
    requester: discord.Member

    @property
    def pretty_duration(self) -> str:
        if not self.duration:
            return "unknown"
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


async def search_track(query: str, requester: discord.Member, loop: asyncio.AbstractEventLoop) -> Track:
    data = await loop.run_in_executor(None, lambda: ytdl_search.extract_info(query, download=False))
    if "entries" in data:  # search results
        if not data["entries"]:
            raise ValueError("No results found.")
        data = data["entries"][0]
    if data.get("is_live") or data.get("live_status") == "is_live":
        raise ValueError("Live streams aren't supported.")
    duration = data.get("duration")
    if duration and duration > MAX_DURATION:
        raise ValueError("That's longer than 3 hours.")
    return Track(
        title=data.get("title", "Unknown"),
        webpage_url=data.get("webpage_url") or data.get("url"),
        duration=duration,
        requester=requester,
    )


async def download_track(url: str, loop: asyncio.AbstractEventLoop) -> str:
    def _download():
        info = ytdl_download.extract_info(url, download=True)
        return ytdl_download.prepare_filename(info)
    return await loop.run_in_executor(None, _download)


def _delete(path: str | None):
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


class GuildPlayer:
    """Queue + playback state for one server."""

    def __init__(self, bot: commands.Bot, guild: discord.Guild, channel: discord.abc.Messageable):
        self.bot = bot
        self.guild = guild
        self.text_channel = channel
        self.queue: deque[Track] = deque()
        self.current: Track | None = None
        self.volume = 0.5
        self.next_event = asyncio.Event()
        self.task = bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        while True:
            self.next_event.clear()

            try:
                track = await asyncio.wait_for(self._wait_for_track(), timeout=IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                await self.text_channel.send("Idle for a while — leaving voice. 👋")
                return await self.destroy()

            vc = self.guild.voice_client
            if not vc:
                return await self.destroy()

            path = None
            try:
                async with self.text_channel.typing():
                    path = await download_track(track.webpage_url, self.bot.loop)
            except Exception as e:
                await self.text_channel.send(f"⚠️ Couldn't play **{track.title}**: `{e}`")
                continue

            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(path, options="-vn"), volume=self.volume
            )

            def after(err):
                if err:
                    print(f"[music] playback error: {err}")
                self.bot.loop.call_soon_threadsafe(self.next_event.set)

            self.current = track
            try:
                vc.play(source, after=after)
            except Exception as e:
                _delete(path)
                self.current = None
                await self.text_channel.send(f"⚠️ Playback failed: `{e}`")
                continue

            await self.text_channel.send(
                f"🎶 Now playing **{track.title}** `[{track.pretty_duration}]` — requested by {track.requester.display_name}"
            )

            try:
                await self.next_event.wait()
            finally:
                self.current = None
                _delete(path)

    async def _wait_for_track(self) -> Track:
        while not self.queue:
            await asyncio.sleep(1)
        return self.queue.popleft()

    async def destroy(self):
        cog = self.bot.get_cog("Music")
        if cog:
            cog.players.pop(self.guild.id, None)
        if self.guild.voice_client:
            await self.guild.voice_client.disconnect(force=True)
        if not self.task.done() and asyncio.current_task() is not self.task:
            self.task.cancel()


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, GuildPlayer] = {}

    def get_player(self, ctx: commands.Context) -> GuildPlayer:
        player = self.players.get(ctx.guild.id)
        if not player:
            player = GuildPlayer(self.bot, ctx.guild, ctx.channel)
            self.players[ctx.guild.id] = player
        return player

    async def cog_check(self, ctx: commands.Context) -> bool:
        if not ctx.guild:
            raise commands.NoPrivateMessage()
        return True

    async def cog_command_error(self, ctx: commands.Context, error):
        traceback.print_exception(type(error), error, error.__traceback__)
        original = getattr(error, "original", error)
        await ctx.send(f"⚠️ `{type(original).__name__}: {original}`")

    async def ensure_same_channel(self, ctx: commands.Context) -> bool:
        vc = ctx.voice_client
        if not ctx.author.voice or (vc and ctx.author.voice.channel != vc.channel):
            await ctx.send("You need to be in my voice channel for that.")
            return False
        return True

    # ---------- commands ----------

    @commands.command()
    async def join(self, ctx: commands.Context):
        if not ctx.author.voice:
            return await ctx.send("Join a voice channel first.")
        vc = ctx.voice_client
        if vc:
            await vc.disconnect(force=True)  # clear any half-dead connection
        vc = await ctx.author.voice.channel.connect(self_deaf=True)
        await asyncio.sleep(3)
        if vc.is_connected():
            await ctx.send("✅ Joined and staying connected.")
        else:
            await ctx.send("❌ Joined but got dropped. Check the logs.")

    @commands.command(aliases=["p"])
    async def play(self, ctx: commands.Context, *, query: str):
        if not ctx.author.voice:
            return await ctx.send("Join a voice channel first.")

        vc = ctx.voice_client
        if not vc:
            vc = await ctx.author.voice.channel.connect(self_deaf=True)
        elif vc.channel != ctx.author.voice.channel:
            return await ctx.send(f"I'm already playing in **{vc.channel.name}**.")

        player = self.get_player(ctx)
        if len(player.queue) >= MAX_QUEUE:
            return await ctx.send("Queue is full.")

        async with ctx.typing():
            try:
                track = await search_track(query, ctx.author, self.bot.loop)
            except Exception as e:
                return await ctx.send(f"⚠️ Couldn't find that: `{e}`")

        player.queue.append(track)
        if vc.is_playing() or vc.is_paused() or player.current:
            await ctx.send(f"➕ Queued **{track.title}** (position {len(player.queue)})")

    @commands.command(aliases=["s"])
    async def skip(self, ctx: commands.Context):
        if not await self.ensure_same_channel(ctx):
            return
        vc = ctx.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await ctx.message.add_reaction("⏭️")
        else:
            await ctx.send("Nothing's playing.")

    @commands.command()
    async def pause(self, ctx: commands.Context):
        if not await self.ensure_same_channel(ctx):
            return
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.message.add_reaction("⏸️")

    @commands.command()
    async def resume(self, ctx: commands.Context):
        if not await self.ensure_same_channel(ctx):
            return
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.message.add_reaction("▶️")

    @commands.command(aliases=["q"])
    async def queue(self, ctx: commands.Context):
        player = self.players.get(ctx.guild.id)
        if not player or (not player.queue and not player.current):
            return await ctx.send("Queue is empty.")

        lines = []
        if player.current:
            lines.append(f"**Now:** {player.current.title} `[{player.current.pretty_duration}]`")
        for i, t in enumerate(list(player.queue)[:10], start=1):
            lines.append(f"`{i}.` {t.title} `[{t.pretty_duration}]` — {t.requester.display_name}")
        if len(player.queue) > 10:
            lines.append(f"…and {len(player.queue) - 10} more")

        embed = discord.Embed(title="🎵 Queue", description="\n".join(lines), color=discord.Color.blurple())
        await ctx.send(embed=embed)

    @commands.command(aliases=["nowplaying"])
    async def np(self, ctx: commands.Context):
        player = self.players.get(ctx.guild.id)
        if not player or not player.current:
            return await ctx.send("Nothing's playing.")
        t = player.current
        await ctx.send(f"🎶 **{t.title}** `[{t.pretty_duration}]`\n<{t.webpage_url}>")

    @commands.command(aliases=["vol"])
    async def volume(self, ctx: commands.Context, vol: int):
        if not await self.ensure_same_channel(ctx):
            return
        if not 0 <= vol <= 100:
            return await ctx.send("Volume must be 0–100.")
        player = self.get_player(ctx)
        player.volume = vol / 100
        if ctx.voice_client and ctx.voice_client.source:
            ctx.voice_client.source.volume = player.volume
        await ctx.send(f"🔊 Volume set to {vol}%")

    @commands.command()
    async def remove(self, ctx: commands.Context, position: int):
        player = self.players.get(ctx.guild.id)
        if not player or not 1 <= position <= len(player.queue):
            return await ctx.send("Invalid position.")
        removed = player.queue[position - 1]
        del player.queue[position - 1]
        await ctx.send(f"🗑️ Removed **{removed.title}**")

    @commands.command()
    async def clear(self, ctx: commands.Context):
        player = self.players.get(ctx.guild.id)
        if player:
            player.queue.clear()
        await ctx.send("🧹 Queue cleared.")

    @commands.command()
    async def stop(self, ctx: commands.Context):
        if not await self.ensure_same_channel(ctx):
            return
        player = self.players.get(ctx.guild.id)
        if player:
            player.queue.clear()
        if ctx.voice_client:
            ctx.voice_client.stop()
        await ctx.message.add_reaction("⏹️")

    @commands.command(aliases=["dc", "disconnect"])
    async def leave(self, ctx: commands.Context):
        player = self.players.get(ctx.guild.id)
        if player:
            await player.destroy()
        elif ctx.voice_client:
            await ctx.voice_client.disconnect(force=True)
        await ctx.message.add_reaction("👋")

    # ---------- auto-leave when everyone else leaves ----------

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        vc = member.guild.voice_client
        if not vc or not before.channel or before.channel != vc.channel:
            return
        if not [m for m in vc.channel.members if not m.bot]:
            await asyncio.sleep(30)  # grace period
            if vc.is_connected() and not [m for m in vc.channel.members if not m.bot]:
                player = self.players.get(member.guild.id)
                if player:
                    await player.destroy()
                else:
                    await vc.disconnect(force=True)

    def cog_unload(self):
        for player in list(self.players.values()):
            self.bot.loop.create_task(player.destroy())


async def setup(bot: commands.Bot):
    print(f"[music] discord.py {discord.__version__}")
    print(f"[music] PO token provider: {YTDL_OPTS['extractor_args']['youtubepot-bgutilhttp']['base_url'][0]}")
    if not YTDL_OPTS.get("cookiefile"):
        print("[music] WARNING: no cookies set (YTDL_COOKIES_B64 missing)")
    await bot.add_cog(Music(bot))
