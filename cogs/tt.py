import discord
from discord.ext import commands
import json
import random
import asyncio
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import os
import io

# ── Standalone TT data manager ───────────────────────────────────────────────
import json as _json
from pathlib import Path as _Path

TT_DATA_FILE = _Path("playerdata/tt_players.json")

def _tt_load() -> dict:
    if not TT_DATA_FILE.exists():
        TT_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)  # /app/playerdata on Railway Volume
        return {}
    with open(TT_DATA_FILE) as f:
        return _json.load(f)

def _tt_save(data: dict):
    with open(TT_DATA_FILE, "w") as f:
        _json.dump(data, f, indent=2)

def tt_get(user_id: int) -> dict | None:
    return _tt_load().get(str(user_id))

def tt_register(user_id: int, username: str, cards: list) -> dict:
    data = _tt_load()
    player = {"id": user_id, "username": username, "gil": 200, "tt_cards": cards, "last_daily": 0, "decks": [[], [], []]}
    data[str(user_id)] = player
    _tt_save(data)
    return player

def tt_update(user_id: int, **kwargs):
    data = _tt_load()
    key = str(user_id)
    if key in data:
        data[key].update(kwargs)
        _tt_save(data)

def tt_is_registered(user_id: int) -> bool:
    return tt_get(user_id) is not None

# ── Paths ─────────────────────────────────────────────────────────────────────
CARDS_DIR  = Path("assets/cards")
TEMP_DIR   = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

# ── Load card database ────────────────────────────────────────────────────────
with open("data/cards.json") as f:
    ALL_CARDS = json.load(f)

CARD_BY_NAME = {c["name"]: c for c in ALL_CARDS}

# ── Gacha rates by level ──────────────────────────────────────────────────────
GACHA_RATES = {
    1:  40.00,
    2:  25.00,
    3:  15.00,
    4:   8.00,
    5:   5.00,
    6:   3.50,
    7:   2.00,
    8:   0.90,
    9:   0.55,
    10:  0.05,
}

# ── Gil constants ─────────────────────────────────────────────────────────────
GACHA_COST    = 500
WIN_GIL_CPU   = 100
WIN_GIL_PVP   = 100
LOSE_GIL_CPU  =  50
LOSE_GIL_PVP  = 100
START_GIL     = 200

# ── Starter cards — 6 random level 1 cards ───────────────────────────────────
LEVEL1_CARDS = [c["name"] for c in ALL_CARDS if c["level"] == 1]

# ── CPU difficulty card pools ─────────────────────────────────────────────────
# Easy: levels 1-3 only (common monsters, no rares)
CPU_EASY_POOL   = [c for c in ALL_CARDS if c["level"] <= 3]
# Normal: levels 2-6 (mix of common and uncommon)
CPU_NORMAL_POOL = [c for c in ALL_CARDS if 2 <= c["level"] <= 6]
# Hard: levels 5-10 (rare, GF, and character cards)
CPU_HARD_POOL   = [c for c in ALL_CARDS if c["level"] >= 5]

# ── Daily gil reward ──────────────────────────────────────────────────────────
DAILY_GIL      = 100
DAILY_COOLDOWN = 86400  # 24 hours in seconds

# ── Deck system ───────────────────────────────────────────────────────────────
MAX_DECKS      = 3
DECK_SIZE      = 5
DECK_NAMES     = ["Deck 1", "Deck 2", "Deck 3"]

# ── Active TT games ───────────────────────────────────────────────────────────
active_tt: dict[int, dict] = {}

# ── Font helper ───────────────────────────────────────────────────────────────
def _font(size):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()

FONT_LG = _font(22)
FONT_MD = _font(16)
FONT_SM = _font(13)

ELEMENT_EMOJI = {
    "Fire": "🔥", "Ice": "❄️", "Thunder": "⚡", "Earth": "🪨",
    "Poison": "☠️", "Wind": "🌪️", "Water": "💧", "Holy": "✨", "none": ""
}

# ── Gacha pull logic ──────────────────────────────────────────────────────────
def _weighted_pull() -> dict:
    """Pull one card using gacha rates."""
    levels    = list(GACHA_RATES.keys())
    weights   = list(GACHA_RATES.values())
    level     = random.choices(levels, weights=weights, k=1)[0]
    pool      = [c for c in ALL_CARDS if c["level"] == level]
    return random.choice(pool) if pool else random.choice(ALL_CARDS)

# ── Card image renderer ───────────────────────────────────────────────────────
def _render_card(card: dict, size=(200, 260)) -> Image.Image:
    """Render a single card as a PIL Image — clean artwork only, no overlays."""
    W, H = size
    img = Image.new("RGBA", (W, H), (20, 15, 40, 255))
    d   = ImageDraw.Draw(img)

    # Border color by level
    level = card.get("level", 1)
    if level >= 9:
        border = (255, 215,   0)   # gold
    elif level >= 7:
        border = (138,  43, 226)   # purple
    elif level >= 5:
        border = ( 30, 144, 255)   # blue
    elif level >= 3:
        border = ( 34, 139,  34)   # green
    else:
        border = (160, 160, 160)   # grey
    d.rectangle([0, 0, W-1, H-1], outline=border, width=3)

    # Card image — fill the entire card area cleanly
    card_path = CARDS_DIR / card["image"]
    if card_path.exists():
        try:
            art = Image.open(card_path).convert("RGBA")
            art = art.resize((W-6, H-6), Image.LANCZOS)
            img.paste(art, (3, 3), art)
        except:
            pass

    return img

def _render_pull_sheet(cards: list) -> Path:
    """Render 3 cards side by side into one image."""
    CARD_W, CARD_H = 200, 260
    GAP    = 16
    PAD    = 20
    total_w = PAD * 2 + CARD_W * 3 + GAP * 2
    total_h = PAD * 2 + CARD_H

    sheet = Image.new("RGBA", (total_w, total_h), (8, 6, 20, 255))
    for i, card in enumerate(cards):
        card_img = _render_card(card)
        x = PAD + i * (CARD_W + GAP)
        sheet.paste(card_img, (x, PAD), card_img)

    out = TEMP_DIR / "gacha_pull.png"
    sheet.save(str(out), "PNG")
    return out

def _render_collection(cards: list, page: int = 0) -> Path:
    """Render a page of cards from a player's collection."""
    PER_PAGE = 10
    COLS     = 5
    CARD_W, CARD_H = 160, 210
    GAP = 12
    PAD = 16

    page_cards = cards[page * PER_PAGE:(page + 1) * PER_PAGE]
    rows = (len(page_cards) + COLS - 1) // COLS

    total_w = PAD * 2 + CARD_W * COLS + GAP * (COLS - 1)
    total_h = PAD * 2 + CARD_H * rows + GAP * (rows - 1)

    sheet = Image.new("RGBA", (total_w, total_h), (8, 6, 20, 255))
    for i, card in enumerate(page_cards):
        row, col = divmod(i, COLS)
        x = PAD + col * (CARD_W + GAP)
        y = PAD + row * (CARD_H + GAP)
        card_img = _render_card(card, size=(CARD_W, CARD_H))
        sheet.paste(card_img, (x, y), card_img)

    out = TEMP_DIR / f"collection_p{page}.png"
    sheet.save(str(out), "PNG")
    return out

# ── Helper: get player card objects ──────────────────────────────────────────
def _get_player_cards(player: dict) -> list:
    owned = player.get("tt_cards", [])
    return [CARD_BY_NAME[n] for n in owned if n in CARD_BY_NAME]

# ── Card select view ──────────────────────────────────────────────────────────
class CardSelectView(discord.ui.View):
    """Let a player pick one card from their hand."""
    def __init__(self, hand: list, user_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.chosen  = None
        for i, card in enumerate(hand):
            lv  = card.get("level", 1)
            lbl = f"{card['name']} ({card['top']}/{card['right']}/{card['bottom']}/{card['left']})"
            if len(lbl) > 80:
                lbl = lbl[:77] + "..."
            btn = discord.ui.Button(label=lbl, style=discord.ButtonStyle.primary, row=i % 4)
            btn.callback = self._make_cb(card)
            self.add_item(btn)

    def _make_cb(self, card):
        async def cb(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("Not your turn!", ephemeral=True)
                return
            self.chosen = card
            self.stop()
            await interaction.response.defer()
        return cb

class SquareSelectView(discord.ui.View):
    """Let a player pick an empty square on the 3x3 board."""
    def __init__(self, board: list, user_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.chosen  = None
        labels = ["↖1","↑2","↗3","←4","·5","→6","↙7","↓8","↘9"]
        for i in range(9):
            if board[i] is None:
                btn = discord.ui.Button(
                    label=labels[i],
                    style=discord.ButtonStyle.secondary,
                    row=i // 3
                )
                btn.callback = self._make_cb(i)
                self.add_item(btn)

    def _make_cb(self, idx):
        async def cb(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("Not your turn!", ephemeral=True)
                return
            self.chosen = idx
            self.stop()
            await interaction.response.defer()
        return cb

# ── Deck select view — pick which deck to play ───────────────────────────────
class DeckSelectView(discord.ui.View):
    def __init__(self, player: dict, user_id: int):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.chosen  = None  # list of card dicts
        decks = player.get("decks", [[], [], []])
        owned = set(player.get("tt_cards", []))

        for i, deck in enumerate(decks):
            # Validate deck — only include cards still owned
            valid = [c for c in deck if c in owned]
            if len(valid) == DECK_SIZE:
                label = f"Deck {i+1} ({DECK_SIZE} cards)"
                style = discord.ButtonStyle.success
            elif valid:
                label = f"Deck {i+1} ({len(valid)}/{DECK_SIZE} cards)"
                style = discord.ButtonStyle.secondary
            else:
                label = f"Deck {i+1} (empty)"
                style = discord.ButtonStyle.secondary

            btn = discord.ui.Button(label=label, style=style, row=0)
            btn.callback = self._make_cb(i, valid)
            self.add_item(btn)

        # Random option always available
        rand_btn = discord.ui.Button(label="🎲 Random", style=discord.ButtonStyle.primary, row=0)
        rand_btn.callback = self._random_cb
        self.add_item(rand_btn)

    def _make_cb(self, deck_idx: int, valid_cards: list):
        async def cb(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("This is not your choice!", ephemeral=True)
                return
            if len(valid_cards) < DECK_SIZE:
                await interaction.response.send_message(
                    f"Deck {deck_idx+1} does not have {DECK_SIZE} cards! Build it with `!ttdeck {deck_idx+1} set`.",
                    ephemeral=True
                )
                return
            cards = [CARD_BY_NAME[n] for n in valid_cards if n in CARD_BY_NAME]
            self.chosen = cards
            self.stop()
            await interaction.response.defer()
        return cb

    async def _random_cb(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This is not your choice!", ephemeral=True)
            return
        self.chosen = "random"
        self.stop()
        await interaction.response.defer()

# ── Board renderer ────────────────────────────────────────────────────────────
def _render_board(board: list, owners: list, p1_name: str, p2_name: str,
                  p1_score: int, p2_score: int) -> Path:
    """Render the 3x3 TT board as an image."""
    CELL_W, CELL_H = 180, 230
    COLS, ROWS = 3, 3
    GAP = 8
    PAD = 20
    HDR = 50

    total_w = PAD * 2 + CELL_W * COLS + GAP * (COLS - 1)
    total_h = PAD + HDR + CELL_H * ROWS + GAP * (ROWS - 1) + PAD

    img = Image.new("RGBA", (total_w, total_h), (15, 12, 30, 255))
    d   = ImageDraw.Draw(img)

    # Header — scores
    d.text((PAD, 12),
           f"🔵 {p1_name}: {p1_score}    🔴 {p2_name}: {p2_score}",
           font=FONT_MD, fill=(240, 192, 64))

    for idx in range(9):
        row, col = divmod(idx, COLS)
        x = PAD + col * (CELL_W + GAP)
        y = PAD + HDR + row * (CELL_H + GAP)

        card  = board[idx]
        owner = owners[idx]

        if card is None:
            # Empty cell
            d.rectangle([x, y, x+CELL_W, y+CELL_H],
                        fill=(30, 25, 50), outline=(80, 60, 120), width=2)
            num = str(idx + 1)
            d.text((x + CELL_W//2 - 8, y + CELL_H//2 - 12),
                   num, font=FONT_LG, fill=(80, 70, 100))
        else:
            card_img = _render_card(card, size=(CELL_W, CELL_H))
            # Tint by owner
            tint_col = (0, 80, 200, 60) if owner == 1 else (200, 30, 30, 60)
            tint = Image.new("RGBA", (CELL_W, CELL_H), tint_col)
            card_img = Image.alpha_composite(card_img, tint)
            img.paste(card_img, (x, y), card_img)

    out = TEMP_DIR / "tt_board.png"
    img.save(str(out), "PNG")
    return out

# ── Flip logic ────────────────────────────────────────────────────────────────
def _do_flips(board, owners, placed_idx, placed_card, placed_owner):
    """Check adjacent cards and flip if placed card's edge > adjacent card's opposite edge."""
    adjacents = {
        0: [(1, "right", "left"), (3, "bottom", "top")],
        1: [(0, "left", "right"), (2, "right", "left"), (4, "bottom", "top")],
        2: [(1, "left", "right"), (5, "bottom", "top")],
        3: [(0, "top", "bottom"), (4, "right", "left"), (6, "bottom", "top")],
        4: [(3, "left", "right"), (1, "top", "bottom"), (5, "right", "left"), (7, "bottom", "top")],
        5: [(4, "left", "right"), (2, "top", "bottom"), (8, "bottom", "top")],
        6: [(3, "top", "bottom"), (7, "right", "left")],
        7: [(6, "left", "right"), (4, "top", "bottom"), (8, "right", "left")],
        8: [(7, "left", "right"), (5, "top", "bottom")],
    }
    flipped = []
    for adj_idx, my_edge, their_edge in adjacents[placed_idx]:
        adj_card = board[adj_idx]
        if adj_card is None:
            continue
        if owners[adj_idx] == placed_owner:
            continue
        if placed_card[my_edge] > adj_card[their_edge]:
            owners[adj_idx] = placed_owner
            flipped.append(adj_card["name"])
    return flipped

# ── Shared delete helper ─────────────────────────────────────────────────────
async def _delete_msg(message, delay=2):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass

# ── Cog ───────────────────────────────────────────────────────────────────────
class TTCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── !ttregister ───────────────────────────────────────────────────────────
    @commands.command(name="ttregister")
    async def ttregister(self, ctx: commands.Context):
        if tt_is_registered(ctx.author.id):
            await ctx.send("❌ You are already registered for Triple Triad!")
            return

        starters = random.sample(LEVEL1_CARDS, min(6, len(LEVEL1_CARDS)))
        tt_register(ctx.author.id, ctx.author.display_name, starters)

        embed = discord.Embed(
            title="🃏 Welcome to Triple Triad!",
            description="You have been given 6 starter cards! Use `!ttgacha` to pull more (500 gil per 3 pulls).",
            color=0x7c3aed
        )
        cards = [CARD_BY_NAME[n] for n in starters if n in CARD_BY_NAME]
        card_list = "\n".join(
            f"`{c['name']}` — {c['top']}/{c['right']}/{c['bottom']}/{c['left']}"
            for c in cards
        )
        embed.add_field(name="Your Starter Cards", value=card_list, inline=False)
        embed.set_footer(text="Starting gil: 200")
        await ctx.send(embed=embed)

    # ── !ttgacha ──────────────────────────────────────────────────────────────
    @commands.command(name="ttgacha")
    async def ttgacha(self, ctx: commands.Context):
        player = tt_get(ctx.author.id)
        if not player:
            await ctx.send("❌ Register with `!ttregister` first!")
            return
        if player.get("tt_cards") is None:
            await ctx.send("❌ Register for Triple Triad with `!ttregister` first!")
            return

        gil = player.get("gil", 0)
        if gil < GACHA_COST:
            await ctx.send(f"❌ Not enough gil! You need **{GACHA_COST} gil** for a 3-pull. You have **{gil} gil**.")
            return

        # Deduct gil
        tt_update(ctx.author.id, gil=gil - GACHA_COST)

        # Pull 3 cards
        pulled = [_weighted_pull() for _ in range(3)]

        # Add to collection — skip duplicates
        owned      = player.get("tt_cards", [])
        owned_set  = set(owned)
        added      = []
        duplicates = []

        for card in pulled:
            if card["name"] in owned_set:
                duplicates.append(card["name"])
            else:
                owned.append(card["name"])
                owned_set.add(card["name"])
                added.append(card["name"])

        tt_update(ctx.author.id, tt_cards=owned)

        # Render pull sheet
        sheet_path = _render_pull_sheet(pulled)

        embed = discord.Embed(
            title="🎰 Triple Triad — 3 Pull!",
            color=0xf0c040
        )
        embed.set_image(url="attachment://gacha_pull.png")

        results = []
        for card in pulled:
            lv   = card.get("level", 1)
            elem = ELEMENT_EMOJI.get(card.get("element", "none"), "")
            dup  = " *(duplicate — discarded)*" if card["name"] in duplicates else " ✅ **NEW!**"
            results.append(f"**{card['name']}** {elem} — LV{lv} `{card['top']}/{card['right']}/{card['bottom']}/{card['left']}`{dup}")

        embed.add_field(name="Results", value="\n".join(results), inline=False)
        new_gil = gil - GACHA_COST
        embed.set_footer(text=f"Gil remaining: {new_gil}  ·  Collection: {len(owned)} cards")

        file = discord.File(str(sheet_path), filename="gacha_pull.png")
        await ctx.send(embed=embed, file=file)

    # ── !ttcollection ─────────────────────────────────────────────────────────
    @commands.command(name="ttcollection", aliases=["ttcol"])
    async def ttcollection(self, ctx: commands.Context, page: int = 1):
        player = tt_get(ctx.author.id)
        if not player or player.get("tt_cards") is None:
            await ctx.send("❌ Register with `!ttregister` first!")
            return

        cards    = _get_player_cards(player)
        PER_PAGE = 10
        total_pages = max(1, (len(cards) + PER_PAGE - 1) // PER_PAGE)
        page = max(1, min(page, total_pages)) - 1

        sheet_path = _render_collection(cards, page)
        file = discord.File(str(sheet_path), filename="collection.png")

        embed = discord.Embed(
            title=f"🃏 {ctx.author.display_name}'s Collection",
            description=f"{len(cards)} cards total",
            color=0x7c3aed
        )
        embed.set_image(url="attachment://collection.png")
        embed.set_footer(text=f"Page {page+1}/{total_pages}  ·  Use !ttcollection <page>")
        await ctx.send(embed=embed, file=file)

    # ── !ttgil ────────────────────────────────────────────────────────────────
    @commands.command(name="ttgil", aliases=["gil"])
    async def ttgil(self, ctx: commands.Context):
        player = tt_get(ctx.author.id)
        if not player:
            await ctx.send("❌ Register with `!ttregister` first!")
            return
        gil = player.get("gil", 0)
        cards = len(player.get("tt_cards") or [])
        embed = discord.Embed(title=f"💰 {ctx.author.display_name}'s Wallet", color=0xf0c040)
        embed.add_field(name="Gil",       value=f"💰 {gil}", inline=True)
        embed.add_field(name="TT Cards",  value=f"🃏 {cards}", inline=True)
        embed.add_field(name="Gacha",     value=f"3-pull costs 500 gil", inline=True)
        await ctx.send(embed=embed)

    # ── !tt ───────────────────────────────────────────────────────────────────
    @commands.command(name="tt")
    async def tt(self, ctx: commands.Context, difficulty_or_opponent: str = None, opponent: discord.Member = None):
        player = tt_get(ctx.author.id)
        if not player:
            await ctx.send("❌ Register with `!ttregister` first!")
            return
        if player.get("tt_cards") is None:
            await ctx.send("❌ Register for Triple Triad with `!ttregister` first!")
            return

        if ctx.channel.id in active_tt:
            await ctx.send("❌ A Triple Triad game is already running here!")
            return

        cards = _get_player_cards(player)
        if len(cards) < 5:
            await ctx.send("❌ You need at least 5 cards to play! Use `!ttgacha` to get more.")
            return

        # Parse difficulty/opponent
        # Supports: !tt easy/norm/hard (cpu) OR !tt @user
        difficulty = "norm"
        actual_opponent = None

        if difficulty_or_opponent:
            if difficulty_or_opponent.lower() in ("easy", "norm", "normal", "hard"):
                difficulty = difficulty_or_opponent.lower()
                if difficulty == "normal":
                    difficulty = "norm"
                actual_opponent = opponent
            else:
                # Try to parse as member mention
                try:
                    actual_opponent = await commands.MemberConverter().convert(ctx, difficulty_or_opponent)
                except:
                    await ctx.send("❌ Usage: `!tt easy/norm/hard` for CPU or `!tt @user` for PvP!")
                    return
        if opponent and actual_opponent is None:
            actual_opponent = opponent

        if actual_opponent and actual_opponent != ctx.guild.me:
            # PvP
            if not tt_is_registered(actual_opponent.id):
                await ctx.send(f"❌ **{opponent.display_name}** hasn't registered yet!")
                return
            opp_data = tt_get(actual_opponent.id)
            if opp_data.get("tt_cards") is None:
                await ctx.send(f"❌ **{opponent.display_name}** hasn't registered for Triple Triad!")
                return
            opp_cards = _get_player_cards(opp_data)
            if len(opp_cards) < 5:
                await ctx.send(f"❌ **{actual_opponent.display_name}** doesn't have enough cards!")
                return
            # Send challenge with accept/decline buttons
            class ChallengeView(discord.ui.View):
                def __init__(self, opponent_id):
                    super().__init__(timeout=30)
                    self.opponent_id = opponent_id
                    self.accepted = None

                @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
                async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != self.opponent_id:
                        await interaction.response.send_message("This challenge is not for you!", ephemeral=True)
                        return
                    self.accepted = True
                    self.stop()
                    await interaction.response.defer()

                @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
                async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
                    if interaction.user.id != self.opponent_id:
                        await interaction.response.send_message("This challenge is not for you!", ephemeral=True)
                        return
                    self.accepted = False
                    self.stop()
                    await interaction.response.defer()

            desc = (
                f"**{ctx.author.display_name}** challenges **{opponent.display_name}** to Triple Triad!\n\n"
                f"{opponent.mention} do you accept? (30 seconds to respond)"
            )
            challenge_embed = discord.Embed(
                title="🃏 Triple Triad Challenge!",
                description=desc,
                color=0x7c3aed
            )
            challenge_view = ChallengeView(opponent.id)
            challenge_msg  = await ctx.send(embed=challenge_embed, view=challenge_view)
            await challenge_view.wait()
            await challenge_msg.delete()

            if challenge_view.accepted is None:
                await ctx.send(f"⏱️ **{opponent.display_name}** did not respond in time. Challenge cancelled!")
                return
            if not challenge_view.accepted:
                await ctx.send(f"❌ **{opponent.display_name}** declined the challenge!")
                return

            # Let challenger pick their deck
            deck_view = DeckSelectView(player, ctx.author.id)
            deck_prompt = await ctx.send(
                "Which deck do you want to use for this duel?",
                view=deck_view
            )
            await deck_view.wait()
            asyncio.create_task(_delete_msg(deck_prompt))

            if deck_view.chosen is None:
                await ctx.send("Timed out! Match cancelled.")
                return

            if deck_view.chosen == "random":
                p1_hand = random.sample(cards, min(5, len(cards)))
            else:
                p1_hand = deck_view.chosen

            await self._run_tt(ctx, player, cards, actual_opponent, opp_data, opp_cards, p1_hand=p1_hand)
        else:
            # vs CPU — pick pool based on difficulty
            if difficulty == "easy":
                pool = CPU_EASY_POOL
                diff_label = "Easy"
            elif difficulty == "hard":
                pool = CPU_HARD_POOL
                diff_label = "Hard"
            else:
                pool = CPU_NORMAL_POOL
                diff_label = "Normal"

            if len(pool) < 5:
                pool = ALL_CARDS
            cpu_pool = random.sample(pool, 5)

            # Let player pick their deck
            deck_view = DeckSelectView(player, ctx.author.id)
            deck_prompt = await ctx.send(
                f"Which deck do you want to use for this {diff_label} match?",
                view=deck_view
            )
            await deck_view.wait()
            asyncio.create_task(_delete_msg(deck_prompt))

            if deck_view.chosen is None:
                await ctx.send("Timed out! Match cancelled.")
                return

            if deck_view.chosen == "random":
                p1_hand = random.sample(cards, min(5, len(cards)))
            else:
                p1_hand = deck_view.chosen

            await self._run_tt(ctx, player, cards, None, None, cpu_pool, p1_hand=p1_hand)

    # ── TT game engine ────────────────────────────────────────────────────────
    async def _run_tt(self, ctx, p1_data, p1_all_cards,
                      p2_member, p2_data, p2_all_cards, p1_hand=None):

        channel  = ctx.channel
        p1_id    = ctx.author.id
        p2_is_cpu = p2_member is None

        # Pick 5 card hands — use provided deck or random
        if p1_hand is None:
            p1_hand = random.sample(p1_all_cards, min(5, len(p1_all_cards)))
        p2_hand = random.sample(p2_all_cards, 5)

        p1_name = p1_data["username"]
        p2_name = p2_member.display_name if p2_member else "CPU"

        board  = [None] * 9   # card placed
        owners = [None] * 9   # 1 = p1, 2 = p2
        turn   = 1            # 1 = p1's turn, 2 = p2's turn

        active_tt[channel.id] = True
        msg = None

        async def send_board(log=""):
            nonlocal msg
            p1_score = owners.count(1)
            p2_score = owners.count(2)
            board_path = _render_board(board, owners, p1_name, p2_name, p1_score, p2_score)
            file  = discord.File(str(board_path), filename="tt_board.png")
            embed = discord.Embed(
                title=f"🃏 Triple Triad — {p1_name} vs {p2_name}",
                color=0x7c3aed
            )
            embed.set_image(url="attachment://tt_board.png")
            if log:
                embed.add_field(name="Last Move", value=log, inline=False)
            p1_cards_left = len(p1_hand)
            p2_cards_left = len(p2_hand)
            embed.add_field(
                name="Cards in Hand",
                value=f"🔵 {p1_name}: {p1_cards_left}  ·  🔴 {p2_name}: {p2_cards_left}",
                inline=False
            )
            turn_txt = f"{'🔵 ' + p1_name if turn == 1 else '🔴 ' + p2_name}'s turn"
            embed.set_footer(text=turn_txt)

            if msg:
                await msg.edit(embed=embed, attachments=[file], view=None)
            else:
                msg = await channel.send(embed=embed, file=file)

        await send_board()

        # ── Main game loop ────────────────────────────────────────────────────
        for move_num in range(9):
            current_hand   = p1_hand if turn == 1 else p2_hand
            current_id     = p1_id   if turn == 1 else (p2_member.id if p2_member else None)
            current_name   = p1_name if turn == 1 else p2_name

            if turn == 2 and p2_is_cpu:
                # CPU plays randomly
                await asyncio.sleep(1.5)
                card  = random.choice(current_hand)
                empty = [i for i, c in enumerate(board) if c is None]
                sq    = random.choice(empty)
            else:
                # Helper to delete a message after 2 seconds in background
                # Player picks card
                card_view = CardSelectView(current_hand, current_id)
                card_prompt = await channel.send(
                    f"{(ctx.author.mention if turn == 1 else p2_member.mention)} — pick a card!",
                    view=card_view
                )
                await card_view.wait()
                asyncio.create_task(_delete_msg(card_prompt))

                if card_view.chosen is None:
                    active_tt.pop(channel.id, None)
                    await channel.send("⏱️ Timed out! Game cancelled.")
                    return
                card = card_view.chosen

                # Player picks square
                sq_view = SquareSelectView(board, current_id)
                sq_prompt = await channel.send(
                    f"{(ctx.author.mention if turn == 1 else p2_member.mention)} — pick a square!",
                    view=sq_view
                )
                await sq_view.wait()
                asyncio.create_task(_delete_msg(sq_prompt))

                if sq_view.chosen is None:
                    active_tt.pop(channel.id, None)
                    await channel.send("⏱️ Timed out! Game cancelled.")
                    return
                sq = sq_view.chosen

            # Place card
            board[sq]  = card
            owners[sq] = turn
            current_hand.remove(card)

            # Flip adjacent cards
            flipped = _do_flips(board, owners, sq, card, turn)
            flip_txt = f"**{current_name}** played **{card['name']}** at square {sq+1}"
            if flipped:
                flip_txt += f"\n↩️ Flipped: {', '.join(flipped)}"

            await send_board(flip_txt)
            turn = 2 if turn == 1 else 1

        # ── Game over ─────────────────────────────────────────────────────────
        active_tt.pop(channel.id, None)

        p1_score = owners.count(1)
        p2_score = owners.count(2)

        if p1_score > p2_score:
            winner_id   = p1_id
            winner_name = p1_name
            loser_id    = p2_member.id if p2_member else None
            p1_won      = True
        elif p2_score > p1_score:
            winner_id   = p2_member.id if p2_member else None
            winner_name = p2_name
            loser_id    = p1_id
            p1_won      = False
        else:
            # Draw
            await channel.send("🤝 It's a **draw**! No gil exchanged.")
            return

        # ── Rewards ───────────────────────────────────────────────────────────
        p1_gil = p1_data.get("gil", 0)

        if p1_won:
            # P1 wins
            gil_gain = WIN_GIL_CPU if p2_is_cpu else WIN_GIL_PVP
            gil_lose = LOSE_GIL_CPU if p2_is_cpu else LOSE_GIL_PVP
            tt_update(p1_id, gil=p1_gil + gil_gain)

            # Win one of winner's own cards back (they keep collection)
            # Loser loses a random card to winner if PvP
            if not p2_is_cpu and p2_data:
                p2_gil   = p2_data.get("gil", 0)
                p2_owned = p2_data.get("tt_cards", [])
                tt_update(loser_id, gil=max(0, p2_gil - gil_lose))

                if p2_owned:
                    stolen = random.choice(p2_owned)
                    p2_owned.remove(stolen)
                    p1_owned = p1_data.get("tt_cards", [])
                    if stolen not in p1_owned:
                        p1_owned.append(stolen)
                        tt_update(p1_id, tt_cards=p1_owned)
                    tt_update(loser_id, tt_cards=p2_owned)
                    steal_txt = f"\n🃏 **{winner_name}** won **{stolen}** from {p2_name}!"
                else:
                    steal_txt = ""
            else:
                steal_txt = ""

            result_msg = (
                f"🏆 **{winner_name}** wins! **{p1_score} — {p2_score}**\n"
                f"💰 +{gil_gain} gil!{steal_txt}"
            )
        else:
            # P1 loses
            gil_lose = LOSE_GIL_CPU if p2_is_cpu else LOSE_GIL_PVP
            tt_update(p1_id, gil=max(0, p1_gil - gil_lose))

            if not p2_is_cpu and p2_data:
                p2_gil = p2_data.get("gil", 0)
                tt_update(winner_id, gil=p2_gil + WIN_GIL_PVP)

                p1_owned = p1_data.get("tt_cards", [])
                if p1_owned:
                    stolen = random.choice(p1_owned)
                    p1_owned.remove(stolen)
                    p2_owned = p2_data.get("tt_cards", [])
                    if stolen not in p2_owned:
                        p2_owned.append(stolen)
                        tt_update(winner_id, tt_cards=p2_owned)
                    tt_update(p1_id, tt_cards=p1_owned)
                    steal_txt = f"\n🃏 **{winner_name}** won **{stolen}** from {p1_name}!"
                else:
                    steal_txt = ""
            else:
                steal_txt = ""

            result_msg = (
                f"💀 **{winner_name}** wins! **{p2_score} — {p1_score}**\n"
                f"💸 -{gil_lose} gil{steal_txt}"
            )

        await channel.send(result_msg)

    # ── !ttdeck ───────────────────────────────────────────────────────────────
    @commands.command(name="ttdeck")
    async def ttdeck(self, ctx: commands.Context, deck_num: int = None, action: str = None):
        player = tt_get(ctx.author.id)
        if not player:
            await ctx.send("❌ Register with `!ttregister` first!")
            return

        decks = player.get("decks", [[], [], []])
        owned = player.get("tt_cards", [])

        # !ttdeck — show all decks
        if deck_num is None:
            embed = discord.Embed(title="🃏 Your Decks", color=0x7c3aed)
            for i, deck in enumerate(decks):
                valid = [c for c in deck if c in owned]
                if valid:
                    cards = [CARD_BY_NAME[n] for n in valid if n in CARD_BY_NAME]
                    val = "\n".join(f"`{c['name']}` — {c['top']}/{c['right']}/{c['bottom']}/{c['left']}" for c in cards)
                    status = "✅ Ready" if len(valid) == DECK_SIZE else f"⚠️ {len(valid)}/{DECK_SIZE} cards"
                else:
                    val = "*Empty*"
                    status = "❌ Empty"
                embed.add_field(
                    name=f"Deck {i+1} — {status}",
                    value=val,
                    inline=False
                )
            embed.set_footer(text="Use !ttdeck <1/2/3> set to build a deck  |  !ttdeck <1/2/3> clear to reset")
            await ctx.send(embed=embed)
            return

        if deck_num not in (1, 2, 3):
            await ctx.send("❌ Deck number must be 1, 2 or 3!")
            return

        deck_idx = deck_num - 1

        # !ttdeck <n> clear
        if action and action.lower() == "clear":
            decks[deck_idx] = []
            tt_update(ctx.author.id, decks=decks)
            await ctx.send(f"🗑️ Deck {deck_num} cleared!")
            return

        # !ttdeck <n> set — interactive card picker
        if action and action.lower() == "set":
            if len(owned) < DECK_SIZE:
                await ctx.send(f"❌ You need at least {DECK_SIZE} cards to build a deck! Use `!ttgacha` to get more.")
                return

            chosen_names = []
            remaining = [CARD_BY_NAME[n] for n in owned if n in CARD_BY_NAME]

            build_msg = f"Building Deck {deck_num} — pick {DECK_SIZE} cards one at a time! Type cancel at any time to stop."
            await ctx.send(build_msg, delete_after=5)

            for pick_num in range(1, DECK_SIZE + 1):
                # Show cards in pages of 20 buttons max
                available = [c for c in remaining if c["name"] not in chosen_names]

                class CardPickView(discord.ui.View):
                    def __init__(self, cards, user_id, page=0):
                        super().__init__(timeout=60)
                        self.user_id  = user_id
                        self.chosen   = None
                        self.page     = page
                        self.all_cards = cards
                        self.cancelled = False
                        self._build(page)

                    def _build(self, page):
                        self.clear_items()
                        start = page * 4
                        page_cards = self.all_cards[start:start+4]
                        for card in page_cards:
                            lbl = f"{card['name']} ({card['top']}/{card['right']}/{card['bottom']}/{card['left']})"
                            btn = discord.ui.Button(label=lbl[:80], style=discord.ButtonStyle.primary, row=0)
                            btn.callback = self._make_cb(card)
                            self.add_item(btn)
                        # Pagination
                        if page > 0:
                            prev = discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=1)
                            prev.callback = self._prev_cb
                            self.add_item(prev)
                        if start + 4 < len(self.all_cards):
                            nxt = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, row=1)
                            nxt.callback = self._next_cb
                            self.add_item(nxt)
                        cancel = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger, row=1)
                        cancel.callback = self._cancel_cb
                        self.add_item(cancel)

                    def _make_cb(self, card):
                        async def cb(interaction: discord.Interaction):
                            if interaction.user.id != self.user_id:
                                await interaction.response.send_message("Not your deck!", ephemeral=True)
                                return
                            self.chosen = card
                            self.stop()
                            await interaction.response.defer()
                        return cb

                    async def _prev_cb(self, interaction: discord.Interaction):
                        if interaction.user.id != self.user_id:
                            await interaction.response.send_message("Not your deck!", ephemeral=True)
                            return
                        self.page -= 1
                        self._build(self.page)
                        await interaction.response.edit_message(view=self)

                    async def _next_cb(self, interaction: discord.Interaction):
                        if interaction.user.id != self.user_id:
                            await interaction.response.send_message("Not your deck!", ephemeral=True)
                            return
                        self.page += 1
                        self._build(self.page)
                        await interaction.response.edit_message(view=self)

                    async def _cancel_cb(self, interaction: discord.Interaction):
                        if interaction.user.id != self.user_id:
                            await interaction.response.send_message("Not your deck!", ephemeral=True)
                            return
                        self.cancelled = True
                        self.stop()
                        await interaction.response.defer()

                so_far = ", ".join(chosen_names) if chosen_names else "none yet"
                pick_view = CardPickView(available, ctx.author.id)
                pick_msg  = await ctx.send(
                    f"Pick card **{pick_num}/{DECK_SIZE}** — chosen so far: {so_far}",
                    view=pick_view
                )
                await pick_view.wait()

                async def del_msg():
                    await asyncio.sleep(2)
                    try:
                        await pick_msg.delete()
                    except:
                        pass
                asyncio.create_task(del_msg())

                if pick_view.cancelled or pick_view.chosen is None:
                    await ctx.send("❌ Deck building cancelled!")
                    return

                chosen_names.append(pick_view.chosen["name"])

            # Save deck
            decks[deck_idx] = chosen_names
            tt_update(ctx.author.id, decks=decks)

            embed = discord.Embed(
                title=f"✅ Deck {deck_num} Saved!",
                color=0x22c55e
            )
            cards = [CARD_BY_NAME[n] for n in chosen_names if n in CARD_BY_NAME]
            val = "\n".join(f"`{c['name']}` — {c['top']}/{c['right']}/{c['bottom']}/{c['left']}" for c in cards)
            embed.add_field(name="Cards", value=val, inline=False)
            await ctx.send(embed=embed)
            return

        await ctx.send("❌ Usage: `!ttdeck` — view  |  `!ttdeck <1/2/3> set` — build  |  `!ttdeck <1/2/3> clear` — reset")

    # ── !daily ────────────────────────────────────────────────────────────────
    @commands.command(name="ttdaily")
    async def ttdaily(self, ctx: commands.Context):
        player = tt_get(ctx.author.id)
        if not player:
            await ctx.send("❌ Register with `!ttregister` first!")
            return

        now         = int(time.time())
        last_daily  = player.get("last_daily", 0)
        time_left   = DAILY_COOLDOWN - (now - last_daily)

        if time_left > 0:
            hours   = time_left // 3600
            minutes = (time_left % 3600) // 60
            await ctx.send(
                f"⏳ You already claimed your daily! Come back in "
                f"**{hours}h {minutes}m**."
            )
            return

        new_gil = player.get("gil", 0) + DAILY_GIL
        tt_update(ctx.author.id, gil=new_gil, last_daily=now)

        embed = discord.Embed(
            title="💰 Daily Gil Claimed!",
            description=f"You received **{DAILY_GIL} gil**!",
            color=0xf0c040
        )
        embed.add_field(name="New Balance", value=f"💰 {new_gil} gil", inline=True)
        embed.set_footer(text="Come back in 24 hours for more!")
        await ctx.send(embed=embed)

    # ── !tthelp ───────────────────────────────────────────────────────────────
    @commands.command(name="tthelp")
    async def tthelp(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🃏 Triple Triad — Help",
            description="FF8-style card game on Discord!",
            color=0x7c3aed
        )
        embed.add_field(name="Commands", value=(
            "`!ttregister` — Register and get 6 starter cards\n"
            "`!tt easy/norm/hard` — Play vs CPU (choose difficulty)\n"
            "`!tt @user` — Challenge a player\n"
            "`!ttgacha` — 3-card pull (500 gil)\n"
            "`!ttcollection` — View your card collection\n"
            "`!ttgil` — Check your gil balance\n"
            "`!ttdeck` — View your decks\n"
            "`!ttdeck <1/2/3> set` — Build a deck\n"
            "`!ttdeck <1/2/3> clear` — Clear a deck\n"
            "`!ttdaily` — Claim 100 gil daily reward\n"
            "`!tthelp` — This help message"
        ), inline=False)
        embed.add_field(name="⚔️ CPU Difficulty", value=(
            "🟢 `!tt easy` — Levels 1-3 cards only\n"
            "🟡 `!tt norm` — Levels 2-6 cards\n"
            "🔴 `!tt hard` — Levels 5-10 (rare + GF cards!)"
        ), inline=False)
        embed.add_field(name="How to Play", value=(
            "Each player picks 5 cards from their collection.\n"
            "Take turns placing cards on the 3×3 board.\n"
            "If your card's edge value **beats** the adjacent card's opposite edge, you flip it!\n"
            "Most cards on the board when all 9 squares are filled wins."
        ), inline=False)
        embed.add_field(name="💰 Gil Rewards", value=(
            f"Win vs CPU: +{WIN_GIL_CPU} gil\n"
            f"Lose vs CPU: -{LOSE_GIL_CPU} gil\n"
            f"Win vs Player: +{WIN_GIL_PVP} gil + steal 1 card\n"
            f"Lose vs Player: -{LOSE_GIL_PVP} gil + lose 1 card"
        ), inline=False)
        embed.add_field(name="🎰 Gacha Rates", value=(
            "LV1 Common: 40%  ·  LV2: 25%  ·  LV3: 15%\n"
            "LV4: 8%  ·  LV5: 5%  ·  LV6: 3.5%\n"
            "LV7 GF: 2%  ·  LV8: 0.9%  ·  LV9: 0.55%\n"
            "LV10 Character: 0.05%"
        ), inline=False)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(TTCog(bot))
