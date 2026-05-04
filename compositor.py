from PIL import Image, ImageDraw, ImageFont
import os
import random
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BACKGROUNDS_DIR = Path("assets/backgrounds")
AVATARS_DIR     = Path("assets/avatars")
ENEMIES_DIR     = Path("assets/enemies")
TEMP_DIR        = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

# Canvas size — matches a nice Discord embed image ratio
CANVAS_W = 600
CANVAS_H = 220

# ── Font helpers ──────────────────────────────────────────────────────────────
def _font(size: int):
    """Try to load a pixel/mono font, fall back to default."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "C:/Windows/Fonts/consola.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

FONT_NAME  = _font(13)
FONT_SMALL = _font(10)
FONT_VS    = _font(16)

# ── Colours ───────────────────────────────────────────────────────────────────
COL_GOLD      = (240, 192, 64)
COL_WHITE     = (220, 220, 230)
COL_MUTED     = (148, 155, 164)
COL_HP_GREEN  = (34,  197,  94)
COL_HP_RED    = (239, 68,   68)
COL_MP_BLUE   = (59,  130, 246)
COL_CARD_BG   = (8,   6,   18, 210)   # RGBA — semi-transparent dark
COL_CARD_BDR  = (140, 90,  255, 160)
COL_BAR_TRACK = (30,  30,  50,  180)

# ── Helpers ───────────────────────────────────────────────────────────────────
def _pick_background() -> Path:
    """Return a random background image path."""
    bgs = list(BACKGROUNDS_DIR.glob("*.jpg")) + list(BACKGROUNDS_DIR.glob("*.png"))
    if not bgs:
        return None
    return random.choice(bgs)

def _load_sprite(filename: str, folder: Path, flip: bool = False, size=(80, 80)) -> Image.Image:
    path = folder / filename
    if not path.exists():
        # Return a coloured placeholder if sprite missing
        img = Image.new("RGBA", size, (100, 80, 160, 200))
        return img
    img = Image.open(path).convert("RGBA")
    img = img.resize(size, Image.NEAREST)   # NEAREST keeps pixel-art crisp
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    return img

def _draw_stat_card(draw: ImageDraw, canvas: Image.Image, x: int, y: int,
                    name: str, level: int,
                    hp: int, max_hp: int,
                    mp: int, max_mp: int,
                    width: int = 130):
    """Draw a semi-transparent stat card at (x, y)."""
    card_h = 52
    # Background card
    card = Image.new("RGBA", (width, card_h), COL_CARD_BG)
    # Thin purple border — draw on the card itself
    cd = ImageDraw.Draw(card)
    cd.rectangle([0, 0, width-1, card_h-1], outline=COL_CARD_BDR, width=1)

    # Name row
    cd.text((6, 4), name.upper(), font=FONT_NAME, fill=COL_GOLD)
    lv_text = f"LV{level}"
    lv_w = cd.textlength(lv_text, font=FONT_SMALL)
    cd.text((width - lv_w - 5, 6), lv_text, font=FONT_SMALL, fill=(167, 139, 250))

    # HP bar
    bar_x, bar_y, bar_w, bar_h = 6, 22, width - 12, 7
    cd.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], fill=COL_BAR_TRACK)
    hp_pct = max(0, hp / max_hp)
    hp_col = COL_HP_GREEN if hp_pct > 0.3 else COL_HP_RED
    cd.rectangle([bar_x, bar_y, bar_x + int(bar_w * hp_pct), bar_y + bar_h], fill=hp_col)
    cd.text((6, 32), f"HP {hp}/{max_hp}", font=FONT_SMALL, fill=COL_WHITE)

    # MP bar
    mp_bar_y = bar_y + 13
    cd.rectangle([bar_x, mp_bar_y, bar_x + bar_w, mp_bar_y + bar_h], fill=COL_BAR_TRACK)
    mp_pct = max(0, mp / max_mp)
    cd.rectangle([bar_x, mp_bar_y, bar_x + int(bar_w * mp_pct), mp_bar_y + bar_h], fill=COL_MP_BLUE)
    cd.text((6, mp_bar_y + 10), f"MP {mp}/{max_mp}", font=FONT_SMALL, fill=COL_WHITE)

    canvas.paste(card, (x, y), card)

# ── Main compositor ───────────────────────────────────────────────────────────
def render_battle_frame(
    battle_id: str,
    # Left fighter (player)
    left_name: str, left_level: int,
    left_hp: int, left_max_hp: int,
    left_mp: int, left_max_mp: int,
    left_sprite: str,                # filename in assets/avatars/
    # Right fighter (enemy or player 2)
    right_name: str, right_level: int,
    right_hp: int, right_max_hp: int,
    right_mp: int, right_max_mp: int,
    right_sprite: str,               # filename in assets/enemies/ or assets/avatars/
    right_is_player: bool = False,   # True for PvP (use avatars folder)
    background: str | None = None,   # force a specific bg, or None for random
) -> Path:
    """
    Composite all assets into one battle frame PNG.
    Returns the path to the generated temp file.
    """

    # ── Background ──────────────────────────────────────────────────────
    if background:
        bg_path = BACKGROUNDS_DIR / background
    else:
        bg_path = _pick_background()

    if bg_path and bg_path.exists():
        bg = Image.open(bg_path).convert("RGBA")
        bg = bg.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
        # Darken slightly for readability
        darkener = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 90))
        canvas = Image.alpha_composite(bg, darkener)
    else:
        # Fallback gradient-ish dark bg
        canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (20, 15, 40, 255))

    draw = ImageDraw.Draw(canvas)

    # ── Sprites ─────────────────────────────────────────────────────────
    sprite_size = (80, 80)
    sprite_y    = CANVAS_H - sprite_size[1] - 18   # sit near bottom

    # Left sprite (player) — flipped to face right
    # Classic FF layout: Enemy LEFT facing right, Player RIGHT facing left
    enemy_folder  = AVATARS_DIR if right_is_player else ENEMIES_DIR
    player_folder = AVATARS_DIR

    enemy_img  = _load_sprite(right_sprite, enemy_folder,  flip=True,  size=sprite_size)  # enemy on LEFT flipped to face right toward player
    player_img = _load_sprite(left_sprite,  player_folder, flip=False, size=sprite_size)  # player on RIGHT naturally faces left toward enemy

    enemy_sprite_x  = 40
    player_sprite_x = CANVAS_W - sprite_size[0] - 40

    canvas.paste(enemy_img,  (enemy_sprite_x,  sprite_y), enemy_img)
    canvas.paste(player_img, (player_sprite_x, sprite_y), player_img)

    # ── Stat cards — above sprites ───────────────────────────────────────
    card_w = 138
    card_y = sprite_y - 60

    # Enemy card on the left
    _draw_stat_card(draw, canvas,
                    x=enemy_sprite_x - 30, y=card_y,
                    name=right_name, level=right_level,
                    hp=right_hp, max_hp=right_max_hp,
                    mp=right_mp, max_mp=right_max_mp,
                    width=card_w)

    # Player card on the right
    _draw_stat_card(draw, canvas,
                    x=player_sprite_x - (card_w - sprite_size[0]) + 30, y=card_y,
                    name=left_name, level=left_level,
                    hp=left_hp, max_hp=left_max_hp,
                    mp=left_mp, max_mp=left_max_mp,
                    width=card_w)

    # ── VS badge ─────────────────────────────────────────────────────────
    vs_x = CANVAS_W // 2 - 14
    vs_y = sprite_y + 20
    badge = Image.new("RGBA", (28, 28), (10, 8, 20, 210))
    bd = ImageDraw.Draw(badge)
    bd.ellipse([0, 0, 27, 27], outline=(140, 90, 255, 180), width=1)
    bd.text((4, 6), "VS", font=FONT_SMALL, fill=(167, 139, 250))
    canvas.paste(badge, (vs_x, vs_y), badge)

    # ── Save ─────────────────────────────────────────────────────────────
    out_path = TEMP_DIR / f"battle_{battle_id}.png"
    canvas.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path
