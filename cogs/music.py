"""
Music cog — streams audio from YouTube into a voice channel.

Requirements:
    pip install -U "discord.py[voice]" yt-dlp
    + ffmpeg on the system PATH
    + a JS runtime (deno) for yt-dlp's YouTube extraction

Commands (prefix):
    !play <url or search>   — queue a song (joins your channel)
    !skip                   — skip current song
    !pause / !resume
    !queue                  — show upcoming songs
    !np                     — now playing
    !volume <0-100>
    !remove <position>      — remove a song from the queue
    !clear                  — clear the queue (keeps current song)
    !stop                   — stop and clear everything
    !leave                  — disconnect
"""

import asyncio
import os
from collections import deque
from dataclasses import dataclass

import discord
import yt_dlp
from discord.ext import commands

IDLE_TIMEOUT = 300  # seconds before leaving an empty/idle channel
MAX_QUEUE = 100

YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}
# Optional: YouTube often blocks datacenter IPs (like Railway). Exporting
# browser cookies to a file and pointing this env var at it usually helps.
if os.getenv("YTDL_COOKIES"):
    YTDL_OPTS["cookiefile"] = os.getenv("YTDL_COOKIES")

FFMPEG_OPTS = {
    # reconnect flags stop streams from dying halfway through long songs
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)


@dataclass
class Track:
    title: str
    webpage_url: str
    duration: int | None
    requester: discord.Member

    @property
    def pretty_duration(self) -> str:
        if not self.duration:
            return "live/unknown"
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


class GuildPlayer:
    """Holds queue + state for one server."""

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

            # wait for a song, or leave after being idle
            try:
                track = await asyncio.wait_for(self._wait_for_track(), timeout=IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                await self.text_channel.send("Idle for a while — leaving voice. 👋")
                return await self.destroy()

            vc = self.guild.voice_client
            if not vc:
                return await self.destroy()

            # Stream URLs expire, so resolve right before playing
            try:
                stream_url = await resolve_stream_url(track.webpage_url, self.bot.loop)
            except Exception as e:
                await self.text_channel.send(f"⚠️ Couldn't play **{track.title}**: `{e}`")
                continue

            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTS), volume=self.volume
            )
            self.current = track
            vc.play(source, after=lambda err: self.bot.loop.call_soon_threadsafe(self.next_event.set))
            await self.text_channel.send(
                f"🎶 Now playing **{track.title}** `[{track.pretty_duration}]` — requested by {track.requester.display_name}"
            )

            await self.next_event.wait()
            self.current = None

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


async def search_track(query: str, requester: discord.Member, loop: asyncio.AbstractEventLoop) -> Track:
    """Look up metadata only (fast-ish, runs in a thread so the bot doesn't freeze)."""
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
    if "entries" in data:  # search results
        if not data["entries"]:
            raise ValueError("No results found.")
        data = data["entries"][0]
    return Track(
        title=data.get("title", "Unknown"),
        webpage_url=data.get("webpage_url") or data.get("url"),
        duration=data.get("duration"),
        requester=requester,
    )


async def resolve_stream_url(url: str, loop: asyncio.AbstractEventLoop) -> str:
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
    return data["url"]


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

    async def ensure_same_channel(self, ctx: commands.Context) -> bool:
        vc = ctx.voice_client
        if not ctx.author.voice or (vc and ctx.author.voice.channel != vc.channel):
            await ctx.send("You need to be in my voice channel for that.")
            return False
        return True

    # ---------- commands ----------

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
        if vc.is_playing() or vc.is_paused():
            await ctx.send(f"➕ Queued **{track.title}** (position {len(player.queue)})")

    @commands.command(aliases=["s"])
    async def skip(self, ctx: commands.Context):
        if not await self.ensure_same_channel(ctx):
            return
        vc = ctx.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()  # triggers the after-callback → next song
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
        humans = [m for m in vc.channel.members if not m.bot]
        if not humans:
            await asyncio.sleep(30)  # grace period in case they rejoin
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
    await bot.add_cog(Music(bot))
