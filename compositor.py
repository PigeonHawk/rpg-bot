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

# ── Canvas ────────────────────────────────────────────────────────────────────
CANVAS_W = 1200
CANVAS_H = 600

# ── Background cache — locked per battle ──────────────────────────────────────
_bg_cache: dict = {}

def pick_background_for_battle(battle_id: str):
    if battle_id in _bg_cache:
        return _bg_cache[battle_id]
    bgs = list(BACKGROUNDS_DIR.glob("*.jpg")) + list(BACKGROUNDS_DIR.glob("*.png"))
    if not bgs:
        return None
    chosen = random.choice(bgs)
    _bg_cache[battle_id] = chosen
    return chosen

def clear_background_for_battle(battle_id: str):
    _bg_cache.pop(battle_id, None)

# ── Fonts ─────────────────────────────────────────────────────────────────────
def _font(size: int):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

FONT_LG  = _font(20)   # names
FONT_MD  = _font(16)   # labels + values
FONT_SM  = _font(13)   # small text

# ── Colours ───────────────────────────────────────────────────────────────────
GOLD       = (240, 192,  64)
WHITE      = (220, 220, 230)
PURPLE     = (167, 139, 250)
HP_GREEN   = ( 34, 197,  94)
HP_RED     = (239,  68,  68)
MP_BLUE    = ( 59, 130, 246)
TRACK      = ( 30,  30,  50, 200)
CARD_BG    = (  8,   6,  18, 230)
CARD_BDR   = (140,  90, 255, 200)

# ── Sprite loader — clean transparency ───────────────────────────────────────
def _load_sprite(filename: str, folder: Path, flip: bool = False, size=(200, 200)) -> Image.Image:
    path = folder / filename
    if not path.exists():
        placeholder = Image.new("RGBA", size, (80, 60, 120, 180))
        return placeholder
    img = Image.open(path).convert("RGBA")
    img = img.resize(size, Image.NEAREST)
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    return img

# ── Composite sprite onto canvas with no black box ────────────────────────────
def _paste_sprite(canvas: Image.Image, sprite: Image.Image, x: int, y: int):
    """Paste an RGBA sprite onto an RGBA canvas using alpha compositing."""
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(sprite, (x, y))
    return Image.alpha_composite(canvas, layer)

# ── Stat card ─────────────────────────────────────────────────────────────────
def _draw_stat_card(canvas: Image.Image, x: int, y: int,
                    name: str, level: int,
                    hp: int, max_hp: int,
                    mp: int, max_mp: int,
                    width: int = 260) -> Image.Image:
    """Draw a stat card and return the updated canvas."""
    PAD      = 12
    NAME_H   = 28    # name row height
    GAP      = 10    # gap between name and first bar
    BAR_H    = 16    # bar height
    LABEL_H  = 18    # label text height below bar
    ROW_GAP  = 14    # gap between HP row and MP row
    card_h   = PAD + NAME_H + GAP + BAR_H + LABEL_H + ROW_GAP + BAR_H + LABEL_H + PAD

    card = Image.new("RGBA", (width, card_h), CARD_BG)
    cd   = ImageDraw.Draw(card)

    # Border
    cd.rectangle([0, 0, width-1, card_h-1], outline=CARD_BDR, width=2)

    # Name
    cd.text((PAD, PAD), name.upper(), font=FONT_LG, fill=GOLD)
    lv = f"LV{level}"
    lv_w = int(cd.textlength(lv, font=FONT_MD))
    cd.text((width - lv_w - PAD, PAD + 2), lv, font=FONT_MD, fill=PURPLE)

    # ── HP row ────────────────────────────────────────────────────────────
    hp_bar_y = PAD + NAME_H + GAP
    bar_x    = PAD
    bar_w    = width - PAD * 2

    # Track
    cd.rectangle([bar_x, hp_bar_y, bar_x + bar_w, hp_bar_y + BAR_H], fill=TRACK)
    # Fill
    hp_pct = max(0.0, hp / max_hp)
    hp_col = HP_GREEN if hp_pct > 0.3 else HP_RED
    fill_w = int(bar_w * hp_pct)
    if fill_w > 0:
        cd.rectangle([bar_x, hp_bar_y, bar_x + fill_w, hp_bar_y + BAR_H], fill=hp_col)
    # Label BELOW the bar
    cd.text((bar_x, hp_bar_y + BAR_H + 2), f"HP  {hp} / {max_hp}", font=FONT_SM, fill=WHITE)

    # ── MP row ────────────────────────────────────────────────────────────
    mp_bar_y = hp_bar_y + BAR_H + LABEL_H + ROW_GAP
    cd.rectangle([bar_x, mp_bar_y, bar_x + bar_w, mp_bar_y + BAR_H], fill=TRACK)
    mp_pct = max(0.0, mp / max_mp)
    fill_w = int(bar_w * mp_pct)
    if fill_w > 0:
        cd.rectangle([bar_x, mp_bar_y, bar_x + fill_w, mp_bar_y + BAR_H], fill=MP_BLUE)
    cd.text((bar_x, mp_bar_y + BAR_H + 2), f"MP  {mp} / {max_mp}", font=FONT_SM, fill=WHITE)

    # Paste card onto canvas cleanly
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(card, (x, y))
    return Image.alpha_composite(canvas, layer)

# ── VS badge ──────────────────────────────────────────────────────────────────
def _draw_vs(canvas: Image.Image) -> Image.Image:
    size   = 52
    cx, cy = CANVAS_W // 2 - size // 2, CANVAS_H // 2 - size // 2 + 40
    badge  = Image.new("RGBA", (size, size), (10, 8, 20, 230))
    bd     = ImageDraw.Draw(badge)
    bd.ellipse([0, 0, size-1, size-1], outline=(140, 90, 255, 220), width=2)
    vs_w = int(bd.textlength("VS", font=FONT_MD))
    bd.text(((size - vs_w) // 2, 14), "VS", font=FONT_MD, fill=PURPLE)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(badge, (cx, cy))
    return Image.alpha_composite(canvas, layer)

# ── Main render ───────────────────────────────────────────────────────────────
def render_battle_frame(
    battle_id,
    left_name,  left_level,  left_hp,  left_max_hp,  left_mp,  left_max_mp,  left_sprite,
    right_name, right_level, right_hp, right_max_hp, right_mp, right_max_mp, right_sprite,
    right_is_player=False,
    background=None,
):
    # ── Background ────────────────────────────────────────────────────────
    bg_path = BACKGROUNDS_DIR / background if background else pick_background_for_battle(str(battle_id))

    if bg_path and Path(bg_path).exists():
        bg = Image.open(bg_path).convert("RGBA")
        bg = bg.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
        dark = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 85))
        canvas = Image.alpha_composite(bg, dark)
    else:
        canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (20, 15, 40, 255))

    # ── Layout constants ──────────────────────────────────────────────────
    SPRITE_W, SPRITE_H = 220, 220
    SPRITE_Y  = CANVAS_H - SPRITE_H - 30       # sprites near bottom
    CARD_W    = 280
    CARD_Y    = 30                              # stat cards near top
    MARGIN    = 60

    ENEMY_X  = MARGIN                           # enemy on LEFT
    PLAYER_X = CANVAS_W - SPRITE_W - MARGIN    # player on RIGHT

    # ── Sprites ───────────────────────────────────────────────────────────
    enemy_folder  = AVATARS_DIR if right_is_player else ENEMIES_DIR
    player_folder = AVATARS_DIR

    # Enemy LEFT  → flip=True  (faces RIGHT toward player)
    # Player RIGHT → flip=False (naturally faces LEFT toward enemy)
    enemy_img  = _load_sprite(right_sprite, enemy_folder,  flip=True,  size=(SPRITE_W, SPRITE_H))
    player_img = _load_sprite(left_sprite,  player_folder, flip=False, size=(SPRITE_W, SPRITE_H))

    canvas = _paste_sprite(canvas, enemy_img,  ENEMY_X,  SPRITE_Y)
    canvas = _paste_sprite(canvas, player_img, PLAYER_X, SPRITE_Y)

    # ── Stat cards ────────────────────────────────────────────────────────
    # Enemy card top-left
    canvas = _draw_stat_card(canvas,
                             x=ENEMY_X, y=CARD_Y,
                             name=right_name, level=right_level,
                             hp=right_hp,   max_hp=right_max_hp,
                             mp=right_mp,   max_mp=right_max_mp,
                             width=CARD_W)

    # Player card top-right
    canvas = _draw_stat_card(canvas,
                             x=PLAYER_X + SPRITE_W - CARD_W, y=CARD_Y,
                             name=left_name,  level=left_level,
                             hp=left_hp,    max_hp=left_max_hp,
                             mp=left_mp,    max_mp=left_max_mp,
                             width=CARD_W)

    # ── VS badge ──────────────────────────────────────────────────────────
    canvas = _draw_vs(canvas)

    # ── Save as PNG keeping full RGBA — no RGB conversion ─────────────────
    out_path = TEMP_DIR / f"battle_{battle_id}.png"
    canvas.save(str(out_path), "PNG")
    return out_path
