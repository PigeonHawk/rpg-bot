import discord
from discord.ext import commands
import random
import asyncio
import json
import os
from datetime import datetime

# ── Constants ─────────────────────────────────────────────────────────────────

# The board is a fixed 5x5 grid. All players in a session share the same square
# layout (same labels per coordinate), but each player marks their own squares.
#
# Columns: B I N G O  (indices 0–4)
# Rows:    1–5        (indices 0–4)
# Coordinate format: B1, I3, N5, G2, O4, etc.
# Center square: N3 (row 2, col 2, index 12) — FREE SPACE, always pre-marked.

COLUMN_LETTERS = ["B", "I", "N", "G", "O"]

# 25 squares in reading order (row-major). Index 12 = N3 = FREE SPACE.
BINGO_SQUARES = [
    # B col          I col                        N col                      G col                      O col
    "Bottom-frag duelist teammate",   "E-daters on the team",        "Yapper teammate >=1 min yap", "Sussy usernames",             "Win an all duelist team game",
    "Defused with <1 second left",    "WOMAN? (confirm by voice)",   "Get a kill by shotgun",       "Get a kill through smoke",    "Get a kill with only utility",
    "PROS DON'T FAKE defuse",         "Clutch in at least a 1v3",   "FREE SPACE",                  "Get asked to trade skins",    "Get knifed without knowing",
    "Teammates arguing in team vc",   "Ace (but 4k is ok too)",      "Win a mono-role team game",   "Win a game with no smokes",   "Impress a teammate (get praised)",
    "Knife someone",                  "Pick up a really shitty skin","Get the same map twice",       "Find an actual normal person","Top frag a game",
]

FREE_SPACE_IDX = 12  # N3

LOBBY_JOIN_SECONDS = 30
CARD_PATH = "assets/bingo_card.jpg"


def coord_to_index(col_letter: str, row_num: int) -> int | None:
    """Convert e.g. 'B', 1 → 0  or  'O', 5 → 24. Returns None if invalid."""
    col_letter = col_letter.upper()
    if col_letter not in COLUMN_LETTERS:
        return None
    if not 1 <= row_num <= 5:
        return None
    col = COLUMN_LETTERS.index(col_letter)
    row = row_num - 1
    return row * 5 + col


def index_to_coord(idx: int) -> str:
    col = COLUMN_LETTERS[idx % 5]
    row = (idx // 5) + 1
    return f"{col}{row}"


def check_bingo(marked: list[bool]) -> bool:
    """Win by having at least one marked square in every column (B, I, N, G, O).
    N3 is always pre-marked so column N is always satisfied from the start."""
    for col in range(5):
        if not any(marked[row * 5 + col] for row in range(5)):
            return False
    return True


# ── Session data structure ────────────────────────────────────────────────────
#
# active_sessions[channel_id] = {
#   "host":    discord.Member,
#   "state":   "lobby" | "active" | None,
#   "players": {
#       user_id: {
#           "member": discord.Member,
#           "marked": [bool x25],          # which squares they've marked
#           "log":    [(coord, square_name, datetime), ...],
#       }
#   }
# }

active_sessions: dict[int, dict] = {}

# Win counts saved to data/bingo_wins.json so they persist across restarts.
LEADERBOARD_PATH = "data/bingo_wins.json"


def load_leaderboard() -> dict[int, dict]:
    """Load win data from disk, keyed by int user_id."""
    if not os.path.exists(LEADERBOARD_PATH):
        return {}
    try:
        with open(LEADERBOARD_PATH, "r") as f:
            raw = json.load(f)
        # JSON keys are always strings — convert back to int
        return {int(k): v for k, v in raw.items()}
    except (json.JSONDecodeError, OSError):
        return {}


def save_leaderboard(lb: dict[int, dict]) -> None:
    """Save win data to disk."""
    os.makedirs(os.path.dirname(LEADERBOARD_PATH), exist_ok=True)
    with open(LEADERBOARD_PATH, "w") as f:
        json.dump(lb, f, indent=2)


win_leaderboard: dict[int, dict] = load_leaderboard()


# ── Embed builders ────────────────────────────────────────────────────────────

def build_board_embed(member: discord.Member, marked: list[bool], log: list, won: bool = False) -> discord.Embed:
    color = discord.Color.gold() if won else discord.Color.red()
    title = f"🎉 BINGO! {member.display_name} wins!" if won else f"🎯 {member.display_name}'s Bingo Card"
    embed = discord.Embed(title=title, color=color)
    embed.set_thumbnail(url=member.display_avatar.url)

    # Column headers
    header = "　　 **B　　　I　　　N　　　G　　　O**"
    rows_text = [header]
    for row in range(5):
        cells = []
        for col in range(5):
            idx = row * 5 + col
            cells.append("✅" if marked[idx] else "🟥")
        rows_text.append(f"**{row+1}**  {'　'.join(cells)}")
    embed.add_field(name="Board", value="\n".join(rows_text), inline=False)

    # Recent activity log (last 5)
    if log:
        log_lines = [f"`{coord}` {name} — <t:{int(ts.timestamp())}:R>" for coord, name, ts in log[-5:]]
        embed.add_field(name="Recent Marks", value="\n".join(log_lines), inline=False)

    marked_count = sum(marked)
    embed.set_footer(text=f"Squares marked: {marked_count}/25 | Type e.g. !N4 to mark a square")
    return embed


def build_reference_embed() -> discord.Embed:
    """Show all 25 squares labelled by coordinate."""
    embed = discord.Embed(title="📋 Bingo Card Reference", color=discord.Color.blurple())
    for col_idx, letter in enumerate(COLUMN_LETTERS):
        lines = []
        for row in range(5):
            idx = row * 5 + col_idx
            coord = f"{letter}{row+1}"
            square = BINGO_SQUARES[idx]
            if idx == FREE_SPACE_IDX:
                lines.append(f"`{coord}` ✅ FREE SPACE")
            else:
                lines.append(f"`{coord}` {square}")
        embed.add_field(name=f"Column {letter}", value="\n".join(lines), inline=True)
    return embed


def build_shared_card_embed() -> discord.Embed:
    """Display the full bingo card as a grid with coordinates — shown to everyone on game start."""
    embed = discord.Embed(
        title="🎯 Valorant Bingo Card",
        description="Everyone shares this card. Type `!XY` to mark a square (e.g. `!N4`).\n`N3` is the FREE SPACE — already marked for all players.",
        color=discord.Color.red(),
    )
    # One field per row so it reads like a grid
    for row in range(5):
        cells = []
        for col in range(5):
            idx = row * 5 + col
            coord = f"{COLUMN_LETTERS[col]}{row+1}"
            square = BINGO_SQUARES[idx]
            if idx == FREE_SPACE_IDX:
                cells.append(f"`{coord}` ✅ **FREE SPACE**")
            else:
                cells.append(f"`{coord}` {square}")
        embed.add_field(
            name=f"Row {row+1}",
            value="\n".join(cells),
            inline=False,
        )
    embed.set_footer(text="B1–B5 | I1–I5 | N1–N5 | G1–G5 | O1–O5")
    return embed


def build_scoreboard_embed(session: dict) -> discord.Embed:
    embed = discord.Embed(title="📊 Bingo Scoreboard", color=discord.Color.orange())
    players = session["players"]
    if not players:
        embed.description = "No players yet."
        return embed
    for uid, data in players.items():
        count = sum(data["marked"]) - 1  # subtract FREE SPACE
        last = f" — last marked `{data['log'][-1][0]}`" if data["log"] else ""
        embed.add_field(
            name=data["member"].display_name,
            value=f"{count} square{'s' if count != 1 else ''} marked{last}",
            inline=False,
        )
    return embed


# ── Cog ───────────────────────────────────────────────────────────────────────

class ValorantBingo(commands.Cog):
    """Valorant Bingo — shared channel session with BINGO coordinate marking."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Helper: get session for channel ──────────────────────────────────────

    def get_session(self, channel_id: int) -> dict | None:
        return active_sessions.get(channel_id)

    # ── !bingo ────────────────────────────────────────────────────────────────

    @commands.group(name="bingo", invoke_without_command=True)
    async def bingo(self, ctx: commands.Context):
        """Start a Valorant Bingo lobby. Others have 30s to !bingo join."""
        channel_id = ctx.channel.id

        if channel_id in active_sessions:
            sess = active_sessions[channel_id]
            state = sess["state"]
            if state == "lobby":
                await ctx.send(f"⚠️ A lobby is already open! Type `!bingo join` to join before the timer runs out.")
            else:
                await ctx.send(f"⚠️ A bingo game is already running in this channel! Use `!bingo board` to see your card.")
            return

        # Create session in lobby state
        active_sessions[channel_id] = {
            "host": ctx.author,
            "state": "lobby",
            "players": {
                ctx.author.id: {
                    "member": ctx.author,
                    "marked": [False] * 25,
                    "log": [],
                }
            },
        }
        # Pre-mark FREE SPACE for host
        active_sessions[channel_id]["players"][ctx.author.id]["marked"][FREE_SPACE_IDX] = True

        embed = discord.Embed(
            title="🎮 Valorant Bingo Lobby",
            description=(
                f"**{ctx.author.display_name}** is starting a Valorant Bingo game!\n\n"
                f"Type `!bingo join` within **30 seconds** to join.\n"
                f"The game starts automatically when the timer ends."
            ),
            color=discord.Color.red(),
        )
        embed.set_footer(text="FREE SPACE (N3) is always pre-marked for everyone.")
        await ctx.send(embed=embed)

        # 30s countdown then start
        await asyncio.sleep(LOBBY_JOIN_SECONDS)

        # Re-check session still exists (could have been cancelled)
        if channel_id not in active_sessions or active_sessions[channel_id]["state"] != "lobby":
            return

        sess = active_sessions[channel_id]
        sess["state"] = "active"
        player_mentions = " ".join(d["member"].mention for d in sess["players"].values())
        count = len(sess["players"])

        start_embed = discord.Embed(
            title="🟥 Valorant Bingo — Game Started!",
            description=(
                f"**{count} player{'s' if count != 1 else ''} joined:** {player_mentions}\n\n"
                f"**How to win:** Spell out **B-I-N-G-O** — mark at least one square in each column (B, I, N, G, O). Any rows, any combo!\n\n"
                f"**How to mark a square:**\n"
                f"Each square has a coordinate — a **column letter** (B I N G O) + a **row number** (1–5).\n"
                f"Just type `!` followed by the coordinate, e.g. `!B1`, `!N4`, `!O5`.\n\n"
                f"🆓 `N3` is the **FREE SPACE** — already marked for everyone. You cannot call it.\n"
                f"🗑️ Square marks auto-delete after **10 seconds**.\n"
                f"🗑️ `!bingo board` and `!bingo ref` auto-delete after **15 seconds**.\n\n"
                f"**Useful commands:**\n"
                f"`!bingo board` — See your personal card & what you've marked *(15s)*\n"
                f"`!bingo ref` — See every square and its coordinate *(15s)*\n"
                f"`!bingo card` — Show the bingo card image\n"
                f"`!bingo scores` — See everyone's progress\n"
                f"`!help_bingo` — Full command list"
            ),
            color=discord.Color.red(),
        )
        card_embed = build_shared_card_embed()
        await ctx.send(embed=start_embed)
        await ctx.send(embed=card_embed)
        # Send the actual bingo card image
        try:
            await ctx.send(
                "📸 **Here's your bingo card for this session:**",
                file=discord.File(CARD_PATH, filename="bingo_card.jpg"),
            )
        except FileNotFoundError:
            await ctx.send("⚠️ Could not find the bingo card image at `assets/bingo_card.jpg`.")

    # ── !bingo join ───────────────────────────────────────────────────────────

    @bingo.command(name="join")
    async def bingo_join(self, ctx: commands.Context):
        """Join an open bingo lobby."""
        channel_id = ctx.channel.id
        sess = self.get_session(channel_id)

        if not sess:
            await ctx.send(f"❌ {ctx.author.mention} No lobby is open. Use `!bingo` to start one!")
            return
        if sess["state"] != "lobby":
            await ctx.send(f"❌ {ctx.author.mention} The game has already started — you can't join mid-game.")
            return
        if ctx.author.id in sess["players"]:
            await ctx.send(f"⚠️ {ctx.author.mention} You're already in the lobby!")
            return

        marked = [False] * 25
        marked[FREE_SPACE_IDX] = True
        sess["players"][ctx.author.id] = {
            "member": ctx.author,
            "marked": marked,
            "log": [],
        }
        count = len(sess["players"])
        await ctx.send(f"✅ {ctx.author.mention} joined the lobby! **{count}** player{'s' if count != 1 else ''} ready.")

    # ── !bingo board ──────────────────────────────────────────────────────────

    @bingo.command(name="board")
    async def bingo_board(self, ctx: commands.Context):
        """Show your current bingo board."""
        sess = self.get_session(ctx.channel.id)
        if not sess or sess["state"] != "active":
            await ctx.send(f"❌ {ctx.author.mention} No active game in this channel.")
            return
        if ctx.author.id not in sess["players"]:
            await ctx.send(f"❌ {ctx.author.mention} You're not in this game.")
            return

        data = sess["players"][ctx.author.id]
        embed = build_board_embed(ctx.author, data["marked"], data["log"])
        bot_msg = await ctx.send(embed=embed)
        await asyncio.sleep(15)
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        try:
            await bot_msg.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

    # ── !bingo ref ────────────────────────────────────────────────────────────

    @bingo.command(name="ref")
    async def bingo_ref(self, ctx: commands.Context):
        """Show the full coordinate reference card."""
        bot_msg = await ctx.send(embed=build_reference_embed())
        await asyncio.sleep(15)
        try:
            await ctx.message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        try:
            await bot_msg.delete()
        except (discord.Forbidden, discord.NotFound):
            pass

    # ── !bingo card ───────────────────────────────────────────────────────────

    @bingo.command(name="card")
    async def bingo_card(self, ctx: commands.Context):
        """Show the bingo card image."""
        try:
            await ctx.send(
                "🎯 **Valorant Bingo Card**",
                file=discord.File(CARD_PATH, filename="bingo_card.jpg"),
            )
        except FileNotFoundError:
            await ctx.send("⚠️ Could not find the bingo card image at `assets/bingo_card.jpg`.")

    # ── !bingo scores ─────────────────────────────────────────────────────────

    @bingo.command(name="scores")
    async def bingo_scores(self, ctx: commands.Context):
        """Show how many squares each player has marked."""
        sess = self.get_session(ctx.channel.id)
        if not sess or sess["state"] != "active":
            await ctx.send(f"❌ No active game in this channel.")
            return
        await ctx.send(embed=build_scoreboard_embed(sess))

    # ── !bingo end / !bingo stop ─────────────────────────────────────────────

    @bingo.command(name="end")
    async def bingo_end(self, ctx: commands.Context):
        """End the current game (host only). Alias: !bingo stop"""
        sess = self.get_session(ctx.channel.id)
        if not sess:
            await ctx.send(f"❌ No active session in this channel.")
            return
        if ctx.author.id != sess["host"].id:
            await ctx.send(f"⚠️ {ctx.author.mention} Only the host ({sess['host'].display_name}) can stop the game.")
            return
        del active_sessions[ctx.channel.id]
        await ctx.send(
            f"🛑 Bingo session stopped by {ctx.author.mention}. "
            f"The board has been reset — start a fresh game with `!bingo`."
        )

    @bingo.command(name="stop")
    async def bingo_stop(self, ctx: commands.Context):
        """Stop and reset the current game (host only). Alias: !bingo end"""
        await ctx.invoke(self.bingo_end)

    # ── Coordinate marking: !B1, !N4, !O5, etc. ──────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        content = message.content.strip()

        # Must match exactly: ! + column letter + row digit, e.g. !B1 !N4 !O5
        if not (len(content) == 3 and content.startswith("!") and
                content[1].upper() in COLUMN_LETTERS and content[2].isdigit()):
            return

        col_letter = content[1].upper()
        row_num = int(content[2])
        channel_id = message.channel.id
        sess = self.get_session(channel_id)

        if not sess or sess["state"] != "active":
            return  # silently ignore if no game running

        user_id = message.author.id
        if user_id not in sess["players"]:
            await message.channel.send(
                f"❌ {message.author.mention} You're not in this game. Spectating only!"
            )
            return

        idx = coord_to_index(col_letter, row_num)
        coord = f"{col_letter}{row_num}"

        if idx is None or not 1 <= row_num <= 5:
            await message.channel.send(f"⚠️ {message.author.mention} `{coord}` isn't a valid coordinate.")
            return

        # Block I3 (FREE SPACE)
        if idx == FREE_SPACE_IDX:
            await message.channel.send(
                f"🆓 {message.author.mention} `N3` is the FREE SPACE — it's already marked for everyone!"
            )
            return

        data = sess["players"][user_id]

        if data["marked"][idx]:
            square_name = BINGO_SQUARES[idx]
            await message.channel.send(
                f"⚠️ {message.author.mention} `{coord}` (**{square_name}**) is already marked on your card!"
            )
            return

        # Mark the square
        data["marked"][idx] = True
        square_name = BINGO_SQUARES[idx]
        data["log"].append((coord, square_name, datetime.now()))

        won = check_bingo(data["marked"])

        if won:
            # Delete the player's input immediately on a win
            try:
                await message.delete()
            except discord.Forbidden:
                pass  # Bot lacks Manage Messages permission — skip silently

            # Build win embed showing their completed board
            win_embed = build_board_embed(message.author, data["marked"], data["log"], won=True)

            # List all players' final square counts
            summary_lines = []
            for uid, pdata in sess["players"].items():
                count = sum(pdata["marked"]) - 1
                summary_lines.append(f"**{pdata['member'].display_name}** — {count} squares marked")

            summary_embed = discord.Embed(
                title="🏁 Final Standings",
                description="\n".join(summary_lines),
                color=discord.Color.gold(),
            )

            del active_sessions[channel_id]

            # Record win on leaderboard
            uid = message.author.id
            if uid not in win_leaderboard:
                win_leaderboard[uid] = {"name": message.author.display_name, "wins": 0}
            win_leaderboard[uid]["wins"] += 1
            win_leaderboard[uid]["name"] = message.author.display_name  # keep name fresh
            save_leaderboard(win_leaderboard)  # persist to disk

            await message.channel.send(
                f"🎉 **BINGO!** {message.author.mention} got **{square_name}** (`{coord}`) and wins!\n"
                f"Use `!bingo` to start a new game.",
                embeds=[win_embed, summary_embed],
            )
        else:
            # Send bot confirmation, then delete both it and the player's message after 10s
            bot_msg = await message.channel.send(
                f"✅ {message.author.mention} marked `{coord}` — **{square_name}**"
            )
            await asyncio.sleep(10)
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound):
                pass
            try:
                await bot_msg.delete()
            except (discord.Forbidden, discord.NotFound):
                pass

    # ── !bingo leaderboard ───────────────────────────────────────────────────

    @bingo.command(name="leaderboard")
    async def bingo_leaderboard(self, ctx: commands.Context):
        """Show the all-time bingo win leaderboard."""
        if not win_leaderboard:
            await ctx.send("🏆 No wins recorded yet — start a game with `!bingo`!")
            return

        sorted_lb = sorted(win_leaderboard.items(), key=lambda x: x[1]["wins"], reverse=True)

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (uid, data) in enumerate(sorted_lb):
            prefix = medals[i] if i < 3 else f"`{i+1}.`"
            lines.append(f"{prefix} **{data['name']}** — {data['wins']} win{'s' if data['wins'] != 1 else ''}")

        embed = discord.Embed(
            title="🏆 Valorant Bingo — Leaderboard",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        embed.set_footer(text="Wins are tracked for this session. Restarting the bot resets the leaderboard.")
        await ctx.send(embed=embed)

    # ── !help_bingo ───────────────────────────────────────────────────────────

    @commands.command(name="help_bingo")
    async def help_bingo(self, ctx: commands.Context):
        """Show all Valorant Bingo commands."""
        embed = discord.Embed(title="🎯 Valorant Bingo — How to Play", color=discord.Color.red())
        embed.add_field(
            name="🏆 How to Win",
            value=(
                "Spell out **B-I-N-G-O** — mark at least **one square in each column** (B, I, N, G, O).\n"
                "The squares don't need to be in the same row — any combination across columns counts!\n"
                "Column **N** is pre-satisfied since N3 (FREE SPACE) is always marked.\n"
                "The bot checks automatically after every mark — no manual call needed!"
            ),
            inline=False,
        )
        embed.add_field(
            name="📍 How Coordinates Work",
            value=(
                "The card is a 5x5 grid. Each square has a coordinate:\n"
                "**Columns:** `B` `I` `N` `G` `O` — left to right\n"
                "**Rows:** `1` `2` `3` `4` `5` — top to bottom\n\n"
                "To mark a square, type `!` + the coordinate:\n"
                "`!B1` = top-left | `!O5` = bottom-right | `!N4` = column N, row 4\n\n"
                "🆓 `N3` is the **FREE SPACE** — pre-marked for all, cannot be called.\n"
                "🗑️ Square marks auto-delete after **10 seconds**.\n"
                "🗑️ `!bingo board` and `!bingo ref` auto-delete after **15 seconds**."
            ),
            inline=False,
        )
        embed.add_field(
            name="🎮 Starting & Joining",
            value=(
                "`!bingo` / `!bstart` — Open a lobby (30 seconds for others to join)\n"
                "`!bingo join` / `!bjoin` — Join an open lobby before it starts\n"
            ),
            inline=False,
        )
        embed.add_field(
            name="📋 During the Game",
            value=(
                "`!B1` `!N4` `!O5` etc. — Mark a square *(auto-deletes in 10s)*\n"
                "`!bingo board` / `!bboard` — See your personal card *(auto-deletes in 15s)*\n"
                "`!bingo ref` / `!bref` — See every square and its coordinate *(auto-deletes in 15s)*\n"
                "`!bingo card` / `!bcard` — Show the bingo card image\n"
                "`!bingo scores` / `!bscores` — See how many squares each player has marked\n"
                "`!bingo stop` / `!bstop` — Stop & reset the session (host only)\n"
                "`!bingo leaderboard` / `!bleaderboard` — Show all-time win leaderboard\n"
            ),
            inline=False,
        )
        embed.set_footer(text="Good luck out there, Agent! 🎯")
        await ctx.send(embed=embed)


# ── Setup hook ────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot):
    await bot.add_cog(ValorantBingo(bot))


# ── Shortcut standalone commands (aliases for the bingo group) ────────────────
# These are registered AFTER the cog so they can reference it via bot.cogs.
# Added in setup() via add_command so they work as top-level prefix commands.

def _make_shortcuts(bot: commands.Bot):
    cog = bot.cogs.get("ValorantBingo")
    if not cog:
        return

    @bot.command(name="bstart")
    async def bstart(ctx):
        """Alias for !bingo — start a new bingo lobby."""
        await ctx.invoke(cog.bingo)

    @bot.command(name="bjoin")
    async def bjoin(ctx):
        """Alias for !bingo join."""
        await ctx.invoke(cog.bingo_join)

    @bot.command(name="bboard")
    async def bboard(ctx):
        """Alias for !bingo board."""
        await ctx.invoke(cog.bingo_board)

    @bot.command(name="bref")
    async def bref(ctx):
        """Alias for !bingo ref."""
        await ctx.invoke(cog.bingo_ref)

    @bot.command(name="bcard")
    async def bcard(ctx):
        """Alias for !bingo card."""
        await ctx.invoke(cog.bingo_card)

    @bot.command(name="bscores")
    async def bscores(ctx):
        """Alias for !bingo scores."""
        await ctx.invoke(cog.bingo_scores)

    @bot.command(name="bstop")
    async def bstop(ctx):
        """Alias for !bingo stop."""
        await ctx.invoke(cog.bingo_stop)

    @bot.command(name="bleaderboard")
    async def bleaderboard(ctx):
        """Alias for !bingo leaderboard."""
        await ctx.invoke(cog.bingo_leaderboard)


async def setup(bot: commands.Bot):  # noqa: F811 — intentional redefinition
    await bot.add_cog(ValorantBingo(bot))
    _make_shortcuts(bot)
