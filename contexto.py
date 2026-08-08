"""
contexto.py — a Contexto-style semantic word-guessing game cog for discord.py.

Clean UI model:
  * ONE live "board" message per game that is edited in place as guesses come in,
    showing all guesses sorted by rank with a proportional hot/warm/cold bar
    (like contexto.me). If an edit ever fails, it re-posts and removes the old one.
  * Each player's guess message is auto-deleted after a few seconds.
  * A tiny confir/❌ feedback message is posted per guess and auto-deleted too, so
    the channel stays focused on the board.
  Requires the bot to have "Manage Messages" to delete players' guesses.

Guess resolution (on a vocab miss): plurals/tenses -> base form, then a
frequency-preferred fuzzy match for typos. Corrections are shown, never silent.

Data files (ship in a `data/` folder next to the cog):
  data/contexto_vectors.npy   normalized float32 matrix, one row per vocab word
  data/contexto_vocab.txt     the vocab, one word per line, index-aligned
  data/contexto_targets.txt   curated secret words (must be in vocab)

Persistence (point at your Railway volume to survive redeploys):
  CONTEXTO_STATE_PATH   default: data/contexto_state.json

Only numpy is required at runtime.
"""

import os
import json
import math
import asyncio
import random
import logging
import difflib

import numpy as np
import discord
from discord.ext import commands

log = logging.getLogger(__name__)

DATA_DIR = os.getenv("CONTEXTO_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
STATE_PATH = os.getenv("CONTEXTO_STATE_PATH", os.path.join(DATA_DIR, "contexto_state.json"))

# Rank bands for the hot/warm/cold bar (tuned to the 316k vocab).
GREEN = 300       # very close
ORANGE = 1500     # getting warm
# past ORANGE is cold (red)

BAR_WIDTH = 10
BOARD_ROWS = 20            # how many sorted guesses to show on the board
GUESS_TTL = 3             # seconds before a player's guess message is deleted
FEEDBACK_TTL = 3          # seconds before the little confirm/❌ message is deleted
SHOW_FEEDBACK = True      # set False to rely on the board alone

# Inactivity timeout. The clock resets on every guess.
IDLE_WARN = 120           # seconds of silence before a "60s left" warning is posted
IDLE_GRACE = 60           # extra seconds after the warning before the game auto-ends

# Guess-resolution tuning.
FUZZY_CUTOFF = 0.82
FUZZY_MIN_LEN = 4


def _closeness(rank: int, vocab_size: int) -> float:
    if rank <= 1:
        return 1.0
    return max(0.0, 1.0 - math.log(rank) / math.log(vocab_size))


def _bar(rank: int, vocab_size: int, width: int = BAR_WIDTH) -> str:
    filled = max(1, round(_closeness(rank, vocab_size) * width))
    block = "🟩" if rank <= GREEN else "🟧" if rank <= ORANGE else "🟥"
    return block * filled + "⬛" * (width - filled)


def _morph_variants(word: str):
    out = []

    def add(w):
        if w and len(w) >= 2 and w not in out:
            out.append(w)

    if word.endswith("ies") and len(word) > 4:
        add(word[:-3] + "y")
    if word.endswith("es") and len(word) > 3:
        add(word[:-2])
        add(word[:-1])
    if word.endswith("s") and not word.endswith("ss"):
        add(word[:-1])
    if word.endswith("ing") and len(word) > 5:
        base = word[:-3]
        add(base)
        add(base + "e")
        if len(base) >= 2 and base[-1] == base[-2]:
            add(base[:-1])
    if word.endswith("ed") and len(word) > 4:
        add(word[:-1])
        add(word[:-2])
        base = word[:-2]
        if len(base) >= 2 and base[-1] == base[-2]:
            add(base[:-1])
    return out


class Game:
    __slots__ = ("target", "guesses", "started_by", "solved_by", "board_message_id", "last_word")

    def __init__(self, target, started_by):
        self.target = target
        self.guesses = {}
        self.started_by = started_by
        self.solved_by = None
        self.board_message_id = None
        self.last_word = None

    def to_dict(self):
        return {"target": self.target, "guesses": self.guesses,
                "started_by": self.started_by, "solved_by": self.solved_by,
                "board_message_id": self.board_message_id, "last_word": self.last_word}

    @classmethod
    def from_dict(cls, d):
        g = cls(d["target"], d.get("started_by"))
        g.guesses = {k: int(v) for k, v in d.get("guesses", {}).items()}
        g.solved_by = d.get("solved_by")
        g.board_message_id = d.get("board_message_id")
        g.last_word = d.get("last_word")
        return g


class Contexto(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.prefix = "!"

        self.vectors = np.load(os.path.join(DATA_DIR, "contexto_vectors.npy"))
        with open(os.path.join(DATA_DIR, "contexto_vocab.txt")) as f:
            self.vocab = f.read().split("\n")
        self.word_to_idx = {w: i for i, w in enumerate(self.vocab)}
        with open(os.path.join(DATA_DIR, "contexto_targets.txt")) as f:
            self.targets = [w for w in f.read().split("\n") if w in self.word_to_idx]
        self.vocab_size = len(self.vocab)

        self._by_first = {}
        for w in self.vocab:
            self._by_first.setdefault(w[0], []).append(w)

        log.info("Contexto loaded: %d vocab words, %d targets", self.vocab_size, len(self.targets))

        self.games = {}
        self.leaderboard = {}
        self._rank_cache = {}
        self._board_msgs = {}       # channel_id -> discord.Message (in-memory cache)
        self._timeout_tasks = {}    # channel_id -> asyncio.Task (inactivity watcher)
        self._warn_msgs = {}        # channel_id -> the standing "60s left" warning message
        self._lock = asyncio.Lock()
        self._load_state()

    # ---------- ranking ----------

    def _ranks_for(self, target: str) -> np.ndarray:
        cached = self._rank_cache.get(target)
        if cached is not None:
            return cached
        tvec = self.vectors[self.word_to_idx[target]]
        sims = self.vectors @ tvec
        order = np.argsort(-sims, kind="stable")
        ranks = np.empty(len(order), dtype=np.int32)
        ranks[order] = np.arange(1, len(order) + 1)
        self._rank_cache[target] = ranks
        return ranks

    # ---------- resolution ----------

    def _fuzzy(self, word: str):
        if len(word) < FUZZY_MIN_LEN:
            return None
        n = len(word)
        pool = [w for w in self._by_first.get(word[0], ()) if abs(len(w) - n) <= 2]
        cands = difflib.get_close_matches(word, pool, n=8, cutoff=FUZZY_CUTOFF)
        if not cands:
            return None
        return min(cands, key=lambda w: self.word_to_idx[w])

    def resolve(self, guess: str):
        if guess in self.word_to_idx:
            return guess, None
        for v in _morph_variants(guess):
            if v in self.word_to_idx:
                return v, f"`{guess}` → **{v}**"
        fz = self._fuzzy(guess)
        if fz:
            return fz, f"read `{guess}` as **{fz}**"
        return None, None

    def rank_of(self, target: str, word_in_vocab: str) -> int:
        return int(self._ranks_for(target)[self.word_to_idx[word_in_vocab]])

    # ---------- persistence ----------

    def _load_state(self):
        try:
            with open(STATE_PATH) as f:
                data = json.load(f)
            self.games = {int(cid): Game.from_dict(g) for cid, g in data.get("games", {}).items()}
            self.leaderboard = data.get("leaderboard", {})
        except (FileNotFoundError, json.JSONDecodeError):
            self.games, self.leaderboard = {}, {}

    def _save_state(self):
        os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"games": {str(cid): g.to_dict() for cid, g in self.games.items()},
                       "leaderboard": self.leaderboard}, f)
        os.replace(tmp, STATE_PATH)

    # ---------- board rendering ----------

    def _row(self, word, rank, marker=""):
        return f"{marker}`{rank:>6}` {_bar(rank, self.vocab_size)} **{word}**"

    def _board_embed(self, game: Game, solved=False):
        color = 0x2ecc71 if not solved else 0xf1c40f
        emb = discord.Embed(color=color)
        emb.set_author(name=f"Contexto  ·  {len(game.guesses)} guesses"
                             + ("  ·  solved!" if solved else ""))
        if not game.guesses:
            emb.description = "Type a word to begin! Lower rank = closer.  🟩 hot 🟧 warm 🟥 cold"
            return emb
        ordered = sorted(game.guesses.items(), key=lambda kv: kv[1])
        lines = []
        # highlight the most recent guess at the top, like contexto.me
        if game.last_word and game.last_word in game.guesses and not solved:
            lines.append(self._row(game.last_word, game.guesses[game.last_word], marker="▸ "))
            lines.append("")
        for w, r in ordered[:BOARD_ROWS]:
            lines.append(self._row(w, r))
        if len(ordered) > BOARD_ROWS:
            lines.append(f"…and {len(ordered) - BOARD_ROWS} more")
        emb.description = "\n".join(lines)
        return emb

    async def _update_board(self, channel, game: Game, solved=False):
        """Edit the live board message in place; re-post + remove old if editing fails."""
        embed = self._board_embed(game, solved=solved)
        msg = self._board_msgs.get(channel.id)
        if msg is None and game.board_message_id:
            try:
                msg = await channel.fetch_message(game.board_message_id)
            except discord.HTTPException:
                msg = None
        if msg is not None:
            try:
                await msg.edit(embed=embed)
                self._board_msgs[channel.id] = msg
                return
            except discord.HTTPException:
                pass  # fall through to re-post
        new_msg = await channel.send(embed=embed)
        if msg is not None:
            try:
                await msg.delete()
            except discord.HTTPException:
                pass
        game.board_message_id = new_msg.id
        self._board_msgs[channel.id] = new_msg

    # ---------- transient helpers ----------

    async def _delete_later(self, message, delay):
        try:
            await asyncio.sleep(delay)
            await message.delete()
        except discord.HTTPException:
            pass

    async def _flash(self, channel, text, delay=FEEDBACK_TTL):
        try:
            m = await channel.send(text)
        except discord.HTTPException:
            return
        await self._delete_later(m, delay)

    async def _safe_delete(self, message):
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    # ---------- inactivity timeout ----------

    def _cancel_timeout(self, channel_id):
        task = self._timeout_tasks.pop(channel_id, None)
        if task and not task.done():
            task.cancel()

    def _arm_timeout(self, channel, game):
        """(Re)start the inactivity clock and clear any standing warning."""
        self._cancel_timeout(channel.id)
        warn = self._warn_msgs.pop(channel.id, None)
        if warn is not None:
            asyncio.create_task(self._safe_delete(warn))
        self._timeout_tasks[channel.id] = asyncio.create_task(self._timeout_watcher(channel, game))

    def _stop_timeout(self, channel_id):
        """Cancel the clock and remove any warning (game solved / given up / restarted)."""
        self._cancel_timeout(channel_id)
        warn = self._warn_msgs.pop(channel_id, None)
        if warn is not None:
            asyncio.create_task(self._safe_delete(warn))

    async def _timeout_watcher(self, channel, game):
        try:
            await asyncio.sleep(IDLE_WARN)
            if self.games.get(channel.id) is not game or game.solved_by is not None:
                return
            try:
                warn = await channel.send(embed=discord.Embed(
                    description=f"⏳ Getting quiet — **{IDLE_GRACE}s** left to guess or the game ends.",
                    color=0xf39c12))
                self._warn_msgs[channel.id] = warn
            except discord.HTTPException:
                pass

            await asyncio.sleep(IDLE_GRACE)
            if self.games.get(channel.id) is not game or game.solved_by is not None:
                return

            async with self._lock:
                self.games.pop(channel.id, None)
                self._board_msgs.pop(channel.id, None)
                self._save_state()
            w = self._warn_msgs.pop(channel.id, None)
            if w is not None:
                await self._safe_delete(w)
            try:
                await channel.send(embed=discord.Embed(
                    title="🛑 Game ended — inactivity",
                    description=(f"No guesses for a few minutes, so I closed it. "
                                f"The word was **{game.target}**.\n`!contexto start` for a new one."),
                    color=0xe74c3c))
            except discord.HTTPException:
                pass
        except asyncio.CancelledError:
            return

    @commands.Cog.listener()
    async def on_ready(self):
        # re-arm inactivity clocks for any games restored from disk after a restart
        for cid, game in list(self.games.items()):
            if game.solved_by is None:
                ch = self.bot.get_channel(cid)
                if ch is not None:
                    self._arm_timeout(ch, game)

    # ---------- commands ----------

    @commands.group(name="contexto", aliases=["ctx"], invoke_without_command=True)
    async def contexto(self, ctx):
        """Contexto: guess the secret word by semantic closeness. Try `!contexto start`."""
        await ctx.send_help(ctx.command)

    @contexto.command(name="start")
    async def start(self, ctx, *, secret: str = None):
        """Start a new game. Optionally set a specific secret word (best in DM)."""
        async with self._lock:
            if ctx.channel.id in self.games and self.games[ctx.channel.id].solved_by is None:
                await self._flash(ctx.channel, "A game is already running here. "
                                               "`!contexto giveup` to end it.", 6)
                return
            if secret:
                secret = secret.strip().lower()
                if secret not in self.word_to_idx:
                    return await ctx.send(f"`{secret}` isn't in my word list, so I can't rank against it.")
                try:
                    await ctx.message.delete()
                except discord.HTTPException:
                    pass
                target = secret
            else:
                target = random.choice(self.targets)
                try:
                    await ctx.message.delete()
                except discord.HTTPException:
                    pass
            game = Game(target, ctx.author.id)
            self.games[ctx.channel.id] = game
            self._board_msgs.pop(ctx.channel.id, None)
            await self._update_board(ctx.channel, game)  # posts the initial live board
            self._arm_timeout(ctx.channel, game)
            self._save_state()

    @contexto.command(name="board", aliases=["ranks", "top"])
    async def board(self, ctx):
        """Re-post the live board (e.g. if it scrolled away)."""
        game = self.games.get(ctx.channel.id)
        if not game or game.solved_by is not None:
            return await self._flash(ctx.channel, "No active game here. `!contexto start`.", 6)
        self._board_msgs.pop(ctx.channel.id, None)
        game.board_message_id = None
        await self._update_board(ctx.channel, game)
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @contexto.command(name="hint")
    async def hint(self, ctx):
        """Reveal a word closer than the current best guess."""
        game = self.games.get(ctx.channel.id)
        if not game or game.solved_by is not None:
            return await self._flash(ctx.channel, "No active game here. `!contexto start`.", 6)
        best = min(game.guesses.values()) if game.guesses else self.vocab_size
        target_rank = max(2, best // 2)
        ranks = self._ranks_for(game.target)
        idx = int(np.argmin(np.abs(ranks - target_rank)))
        hint_word = self.vocab[idx]
        if hint_word == game.target:
            hint_word = self.vocab[int(np.where(ranks == 3)[0][0])]
        await self._flash(ctx.channel, f"💡 try something like **{hint_word}** "
                                       f"(rank {int(ranks[self.word_to_idx[hint_word]])})", 8)
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @contexto.command(name="giveup", aliases=["reveal", "stop"])
    async def giveup(self, ctx):
        """End the game and reveal the secret word."""
        async with self._lock:
            game = self.games.pop(ctx.channel.id, None)
            self._board_msgs.pop(ctx.channel.id, None)
            self._save_state()
        self._stop_timeout(ctx.channel.id)
        if not game:
            return await self._flash(ctx.channel, "No active game here.", 5)
        await ctx.send(embed=discord.Embed(
            title="🏳️ Game over",
            description=f"The word was **{game.target}**.\n`!contexto start` for another.",
            color=0xe74c3c))

    @contexto.command(name="leaderboard", aliases=["lb"])
    async def leaderboard_cmd(self, ctx):
        """Show the win leaderboard."""
        if not self.leaderboard:
            return await ctx.send("No wins recorded yet. `!contexto start`.")
        rows = sorted(self.leaderboard.items(), key=lambda kv: kv[1], reverse=True)[:10]
        lines = []
        for i, (uid, wins) in enumerate(rows, 1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"`{i}.`")
            lines.append(f"{medal} <@{uid}> — **{wins}** win{'s' if wins != 1 else ''}")
        await ctx.send(embed=discord.Embed(
            title="🏆 Contexto leaderboard", description="\n".join(lines), color=0xf1c40f))

    # ---------- guess listener ----------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        game = self.games.get(message.channel.id)
        if not game or game.solved_by is not None:
            return

        content = message.content.strip().lower()
        if not content or content.startswith(self.prefix):
            return
        if len(content.split()) != 1 or not content.isalpha():
            return

        # always clear the player's raw guess shortly, to keep focus on the board
        asyncio.create_task(self._delete_later(message, GUESS_TTL))

        word, note = self.resolve(content)
        if word is None:
            if SHOW_FEEDBACK:
                asyncio.create_task(self._flash(message.channel, f"❌ `{content}` isn't a word I know"))
            return

        async with self._lock:
            rank = self.rank_of(game.target, word)
            already = word in game.guesses
            game.guesses[word] = rank
            game.last_word = word

            if rank == 1:
                game.solved_by = message.author.id
                uid = str(message.author.id)
                self.leaderboard[uid] = self.leaderboard.get(uid, 0) + 1
                await self._update_board(message.channel, game, solved=True)
                self.games.pop(message.channel.id, None)
                self._board_msgs.pop(message.channel.id, None)
                self._save_state()
                self._stop_timeout(message.channel.id)
                await message.channel.send(embed=discord.Embed(
                    title="🎉 Solved!",
                    description=(f"{message.author.mention} got **{game.target}** "
                                f"in {len(game.guesses)} guesses.\n`!contexto start` for another."),
                    color=0x2ecc71))
                return

            await self._update_board(message.channel, game)
            self._arm_timeout(message.channel, game)
            self._save_state()

        if SHOW_FEEDBACK:
            band = "🟩" if rank <= GREEN else "🟧" if rank <= ORANGE else "🟥"
            bits = [f"{band} **{word}** · rank {rank}"]
            if note:
                bits.append(f"({note})")
            if already:
                bits.append("· already tried")
            asyncio.create_task(self._flash(message.channel, "  ".join(bits)))


async def setup(bot):
    await bot.add_cog(Contexto(bot))
