"""
Music cog — plays songs from a local library stored on the Railway Volume.

Songs live in <volume>/music (here: /app/playerdata/music). People add songs
by attaching audio files to !addsong in Discord.

Requirements:
    discord.py[voice]>=2.7.1, davey  (requirements.txt)
    ffmpeg on the system (Railway: RAILPACK_DEPLOY_APT_PACKAGES=ffmpeg)

Commands (prefix !):
    !addsong [name]      — attach audio file(s) to the same message to add them
    !songs [page]        — list the library
    !removesong <name>   — delete a song (admins only)
    !play <name>  (!p)   — play/queue a song from the library
    !playall             — queue the whole library, shuffled
    !shuffle             — shuffle the queue
    !repeat (!loop)      — repeat current song until !skip
    !join, !skip (!s), !pause, !resume, !queue (!q), !np, !volume <0-100> (!vol)
    !remove <position>, !clear, !stop, !leave (!dc)
"""

import asyncio
import difflib
import os
import random
import re
import traceback
from collections import deque
from dataclasses import dataclass

import discord
from discord.ext import commands

# ── Config ────────────────────────────────────────────────────────────────────
VOLUME_ROOT = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "/app/playerdata")
LIBRARY_DIR = os.path.join(VOLUME_ROOT, "music")
os.makedirs(LIBRARY_DIR, exist_ok=True)

ALLOWED_EXTS = {".mp3", ".m4a", ".ogg", ".opus", ".wav", ".flac", ".webm", ".aac"}
IDLE_TIMEOUT = 300   # seconds idle before leaving voice
MAX_QUEUE = 500
SONGS_PER_PAGE = 20


# ── Library helpers ───────────────────────────────────────────────────────────
def clean_name(name: str) -> str:
    """Make a safe, readable song name to use as a filename."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:100]


def library_songs() -> dict[str, str]:
    """{song name: full path} for every song in the library."""
    songs = {}
    for fn in os.listdir(LIBRARY_DIR):
        stem, ext = os.path.splitext(fn)
        if ext.lower() in ALLOWED_EXTS:
            songs[stem] = os.path.join(LIBRARY_DIR, fn)
    return songs


def find_songs(query: str) -> tuple[str | None, list[str]]:
    """Return (exact/unique match, other candidates)."""
    songs = library_songs()
    q = query.lower().strip()
    names = sorted(songs, key=str.lower)

    exact = [n for n in names if n.lower() == q]
    if exact:
        return exact[0], []

    contains = [n for n in names if q in n.lower()]
    if len(contains) == 1:
        return contains[0], []
    if contains:
        return None, contains

    # every word appears somewhere in the name
    words = q.split()
    all_words = [n for n in names if all(w in n.lower() for w in words)]
    if len(all_words) == 1:
        return all_words[0], []
    if all_words:
        return None, all_words

    lowered = {n.lower(): n for n in names}
    close = difflib.get_close_matches(q, list(lowered), n=5, cutoff=0.5)
    return None, [lowered[c] for c in close]


async def probe_duration(path: str) -> int | None:
    """Song length in seconds via ffprobe (comes with ffmpeg)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        return int(float(out.decode().strip()))
    except Exception:
        return None


@dataclass
class Track:
    title: str
    path: str
    duration: int | None
    requester: discord.Member

    @property
    def pretty_duration(self) -> str:
        if not self.duration:
            return "?:??"
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


async def make_track(name: str, requester: discord.Member) -> Track:
    path = library_songs()[name]
    return Track(name, path, await probe_duration(path), requester)


# ── Per-server player ─────────────────────────────────────────────────────────
class GuildPlayer:
    def __init__(self, bot: commands.Bot, guild: discord.Guild, channel: discord.abc.Messageable):
        self.bot = bot
        self.guild = guild
        self.text_channel = channel
        self.queue: deque[Track] = deque()
        self.current: Track | None = None
        self.volume = 0.5
        self.repeat = False
        self.skip_requested = False
        self.next_event = asyncio.Event()
        self.task = bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        while True:
            try:
                track = await asyncio.wait_for(self._wait_for_track(), timeout=IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                await self.text_channel.send("Idle for a while — leaving voice. 👋")
                return await self.destroy()

            if not os.path.exists(track.path):
                await self.text_channel.send(f"⚠️ **{track.title}** isn't in the library anymore — skipping.")
                continue

            def after(err):
                if err:
                    print(f"[music] playback error: {err}")
                self.bot.loop.call_soon_threadsafe(self.next_event.set)

            self.current = track
            self.skip_requested = False
            announced = False
            try:
                while True:
                    self.next_event.clear()
                    vc = self.guild.voice_client
                    if not vc or not vc.is_connected():
                        return await self.destroy()
                    source = discord.PCMVolumeTransformer(
                        discord.FFmpegPCMAudio(track.path, options="-vn"), volume=self.volume
                    )
                    try:
                        vc.play(source, after=after)
                    except Exception as e:
                        await self.text_channel.send(f"⚠️ Playback failed: `{e}`")
                        break

                    if not announced:
                        loop_note = " 🔂" if self.repeat else ""
                        await self.text_channel.send(
                            f"🎶 Now playing **{track.title}** `[{track.pretty_duration}]` — "
                            f"requested by {track.requester.display_name}{loop_note}"
                        )
                        announced = True

                    await self.next_event.wait()
                    if not self.repeat or self.skip_requested:
                        break
            finally:
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


# ── Cog ───────────────────────────────────────────────────────────────────────
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
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(f"Missing `{error.param.name}` — try `!{ctx.command.name} <{error.param.name}>`.")
        if isinstance(error, commands.MissingPermissions):
            return await ctx.send("You don't have permission to do that.")
        if isinstance(error, commands.BadArgument):
            return await ctx.send("That doesn't look right — check the command and try again.")
        traceback.print_exception(type(error), error, error.__traceback__)
        original = getattr(error, "original", error)
        await ctx.send(f"⚠️ `{type(original).__name__}: {original}`")

    async def ensure_same_channel(self, ctx: commands.Context) -> bool:
        vc = ctx.voice_client
        if not ctx.author.voice or (vc and ctx.author.voice.channel != vc.channel):
            await ctx.send("You need to be in my voice channel for that.")
            return False
        return True

    async def ensure_voice(self, ctx: commands.Context) -> discord.VoiceClient | None:
        """Join the author's channel if needed. Returns None (and replies) on failure."""
        if not ctx.author.voice:
            await ctx.send("Join a voice channel first.")
            return None
        vc = ctx.voice_client
        if vc and vc.is_connected():
            if vc.channel != ctx.author.voice.channel:
                await ctx.send(f"I'm already playing in **{vc.channel.name}**.")
                return None
            return vc
        if vc:
            await vc.disconnect(force=True)
        return await ctx.author.voice.channel.connect(self_deaf=True)

    # ---------- library ----------

    @commands.command()
    async def addsong(self, ctx: commands.Context, *, name: str | None = None):
        files = ctx.message.attachments
        if not files:
            await self._delete_command(ctx)
            return await ctx.send(f"{ctx.author.mention} attach an audio file to the same message as `!addsong`.")

        added, problems = [], []
        existing = {n.lower() for n in library_songs()}

        for i, att in enumerate(files):
            stem, ext = os.path.splitext(att.filename)
            ext = ext.lower()
            if ext not in ALLOWED_EXTS:
                problems.append(f"`{att.filename}` isn't a supported audio file")
                continue

            # a custom name only applies when adding a single file
            song_name = clean_name(name if (name and len(files) == 1) else stem.replace("_", " "))
            if not song_name:
                problems.append(f"`{att.filename}` needs a name — try `!addsong <name>`")
                continue
            if song_name.lower() in existing:
                problems.append(f"**{song_name}** is already in the library")
                continue

            path = os.path.join(LIBRARY_DIR, song_name + ext)
            try:
                await att.save(path)
            except Exception as e:
                problems.append(f"`{att.filename}` failed to save: `{e}`")
                continue
            existing.add(song_name.lower())
            added.append(song_name)

        # files are saved, so the original message can go
        deleted = await self._delete_command(ctx)

        who = ctx.author.display_name
        lines = [f"✅ {who} added **{n}**" for n in added] + [f"⚠️ {p}" for p in problems]
        if not deleted:
            lines.append("-# (I couldn't delete the upload message — give me the Manage Messages permission here.)")
        await ctx.send("\n".join(lines))

    async def _delete_command(self, ctx: commands.Context) -> bool:
        """Delete the user's command message. Returns False if not allowed."""
        try:
            await ctx.message.delete()
            return True
        except discord.NotFound:
            return True   # already gone
        except discord.Forbidden:
            return False
        except discord.HTTPException:
            return False

    @commands.command(aliases=["library", "lib"])
    async def songs(self, ctx: commands.Context, page: int = 1):
        names = sorted(library_songs(), key=str.lower)
        if not names:
            return await ctx.send("The library is empty — add songs with `!addsong` and an attached file.")
        pages = (len(names) - 1) // SONGS_PER_PAGE + 1
        page = max(1, min(page, pages))
        start = (page - 1) * SONGS_PER_PAGE
        lines = [f"`{i}.` {n}" for i, n in enumerate(names[start:start + SONGS_PER_PAGE], start=start + 1)]
        embed = discord.Embed(title=f"🎵 Library — {len(names)} songs", description="\n".join(lines),
                              color=discord.Color.blurple())
        embed.set_footer(text=f"Page {page}/{pages} — !songs <page>")
        await ctx.send(embed=embed)

    @commands.command(aliases=["deletesong"])
    @commands.has_permissions(administrator=True)
    async def removesong(self, ctx: commands.Context, *, name: str):
        match, options = find_songs(name)
        if not match:
            if options:
                return await ctx.send("Which one? Be more specific:\n" + "\n".join(f"• {o}" for o in options[:10]))
            return await ctx.send("No song by that name.")
        player = self.players.get(ctx.guild.id)
        if player and player.current and player.current.title == match:
            return await ctx.send("That song is playing right now — skip it first.")
        os.remove(library_songs()[match])
        if player:
            player.queue = deque(t for t in player.queue if t.title != match)
        await ctx.send(f"🗑️ Removed **{match}** from the library.")

    # ---------- playback ----------

    @commands.command()
    async def join(self, ctx: commands.Context):
        vc = await self.ensure_voice(ctx)
        if not vc:
            return
        await asyncio.sleep(3)
        if vc.is_connected():
            await ctx.send("✅ Joined and staying connected.")
        else:
            await ctx.send("❌ Joined but got dropped. Check the logs.")

    @commands.command(aliases=["p"])
    async def play(self, ctx: commands.Context, *, name: str):
        match, options = find_songs(name)
        if not match:
            if options:
                return await ctx.send("Which one? Be more specific:\n" + "\n".join(f"• {o}" for o in options[:10]))
            return await ctx.send("Couldn't find that in the library. See what's there with `!songs`.")

        vc = await self.ensure_voice(ctx)
        if not vc:
            return
        player = self.get_player(ctx)
        if len(player.queue) >= MAX_QUEUE:
            return await ctx.send("Queue is full.")

        track = await make_track(match, ctx.author)
        player.queue.append(track)
        if player.current or vc.is_playing() or vc.is_paused():
            await ctx.send(f"➕ Queued **{track.title}** (position {len(player.queue)})")

    @commands.command()
    async def playall(self, ctx: commands.Context):
        names = list(library_songs())
        if not names:
            return await ctx.send("The library is empty.")
        vc = await self.ensure_voice(ctx)
        if not vc:
            return
        player = self.get_player(ctx)
        random.shuffle(names)
        room = MAX_QUEUE - len(player.queue)
        for n in names[:room]:
            player.queue.append(await make_track(n, ctx.author))
        await ctx.send(f"🔀 Queued {min(len(names), room)} songs in random order.")

    @commands.command()
    async def shuffle(self, ctx: commands.Context):
        player = self.players.get(ctx.guild.id)
        if not player or len(player.queue) < 2:
            return await ctx.send("Not enough songs in the queue to shuffle.")
        items = list(player.queue)
        random.shuffle(items)
        player.queue = deque(items)
        await ctx.message.add_reaction("🔀")

    @commands.command(aliases=["s"])
    async def skip(self, ctx: commands.Context):
        if not await self.ensure_same_channel(ctx):
            return
        vc = ctx.voice_client
        player = self.players.get(ctx.guild.id)
        if vc and (vc.is_playing() or vc.is_paused()):
            was_repeating = bool(player and player.repeat)
            if player:
                player.skip_requested = True
                player.repeat = False
            vc.stop()
            if was_repeating:
                await ctx.send("⏭️ Skipped — repeat is now off.")
            else:
                await ctx.message.add_reaction("⏭️")
        else:
            await ctx.send("Nothing's playing.")

    @commands.command(aliases=["loop"])
    async def repeat(self, ctx: commands.Context):
        if not await self.ensure_same_channel(ctx):
            return
        player = self.players.get(ctx.guild.id)
        if not player or not player.current:
            return await ctx.send("Nothing's playing.")
        player.repeat = not player.repeat
        if player.repeat:
            await ctx.send(f"🔂 Repeating **{player.current.title}** until someone uses `!skip`.")
        else:
            await ctx.send("➡️ Repeat off — the queue will continue after this song.")

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
            loop_note = " 🔂" if player.repeat else ""
            lines.append(f"**Now:** {player.current.title} `[{player.current.pretty_duration}]`{loop_note}")
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
        loop_note = " 🔂 (repeating)" if player.repeat else ""
        await ctx.send(f"🎶 **{t.title}** `[{t.pretty_duration}]`{loop_note} — requested by {t.requester.display_name}")

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
        await ctx.send(f"🗑️ Removed **{removed.title}** from the queue.")

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
            player.repeat = False
            player.skip_requested = True
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
                if player and player.repeat and player.current:
                    return  # stay put while a song is on repeat
                if player:
                    await player.destroy()
                else:
                    await vc.disconnect(force=True)

    def cog_unload(self):
        for player in list(self.players.values()):
            self.bot.loop.create_task(player.destroy())


async def setup(bot: commands.Bot):
    print(f"[music] library: {LIBRARY_DIR} ({len(library_songs())} songs)")
    await bot.add_cog(Music(bot))
