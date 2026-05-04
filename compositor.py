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

# Canvas size — bigger for Discord
CANVAS_W = 800
CANVAS_H = 340

# ── Background cache — locked per battle_id ───────────────────────────────────
_bg_cache: dict = {}

def pick_background_for_battle(battle_id: str):
    """Return the same background for the same battle every time."""
    if battle_id in _bg_cache:
        return _bg_cache[battle_id]
    bgs = list(BACKGROUNDS_DIR.glob("*.jpg")) + list(BACKGROUNDS_DIR.glob("*.png"))
    if not bgs:
        return None
    chosen = random.choice(bgs)
    _bg_cache[battle_id] = chosen
    return chosen

def clear_background_for_battle(battle_id: str):
    """Call when a battle ends to free the cache."""
    _bg_cache.pop(battle_id, None)

# ── Font helpers ──────────────────────────────────────────────────────────────
def _font(size: int):
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

FONT_NAME  = _font(15)
FONT_SMALL = _font(12)

# ── Colours ───────────────────────────────────────────────────────────────────
COL_GOLD      = (240, 192, 64)
COL_WHITE     = (220, 220, 230)
COL_HP_GREEN  = (34,  197,  94)
COL_HP_RED    = (239, 68,   68)
COL_MP_BLUE   = (59,  130, 246)
COL_CARD_BG   = (8,   6,   18, 220)
COL_CARD_BDR  = (140, 90,  255, 180)
COL_BAR_TRACK = (30,  30,  50,  200)

# ── Sprite loader ─────────────────────────────────────────────────────────────
def _load_sprite(filename, folder, flip=False, size=(120, 120)):
    path = folder / filename
    if not path.exists():
        img = Image.new("RGBA", size, (100, 80, 160, 200))
        return img
    img = Image.open(path).convert("RGBA")
    img = img.resize(size, Image.NEAREST)
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    return img

# ── Stat card ─────────────────────────────────────────────────────────────────
def _draw_stat_card(canvas, x, y, name, level, hp, max_hp, mp, max_mp, width=180):
    card_h = 64
    card = Image.new("RGBA", (width, card_h), COL_CARD_BG)
    cd = ImageDraw.Draw(card)
    cd.rectangle([0, 0, width-1, card_h-1], outline=COL_CARD_BDR, width=1)

    cd.text((8, 5), name.upper(), font=FONT_NAME, fill=COL_GOLD)
    lv_text = f"LV{level}"
    lv_w = cd.textlength(lv_text, font=FONT_SMALL)
    cd.text((width - lv_w - 6, 7), lv_text, font=FONT_SMALL, fill=(167, 139, 250))

    bar_x, bar_y, bar_w, bar_h = 8, 26, width - 16, 9
    cd.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], fill=COL_BAR_TRACK)
    hp_pct = max(0, hp / max_hp)
    hp_col = COL_HP_GREEN if hp_pct > 0.3 else COL_HP_RED
    cd.rectangle([bar_x, bar_y, bar_x + int(bar_w * hp_pct), bar_y + bar_h], fill=hp_col)
    cd.text((8, 37), f"HP {hp}/{max_hp}", font=FONT_SMALL, fill=COL_WHITE)

    mp_bar_y = bar_y + 16
    cd.rectangle([bar_x, mp_bar_y, bar_x + bar_w, mp_bar_y + bar_h], fill=COL_BAR_TRACK)
    mp_pct = max(0, mp / max_mp)
    cd.rectangle([bar_x, mp_bar_y, bar_x + int(bar_w * mp_pct), mp_bar_y + bar_h], fill=COL_MP_BLUE)
    cd.text((8, mp_bar_y + 11), f"MP {mp}/{max_mp}", font=FONT_SMALL, fill=COL_WHITE)

    canvas.paste(card, (x, y), card)

# ── Main compositor ───────────────────────────────────────────────────────────
def render_battle_frame(
    battle_id,
    left_name, left_level, left_hp, left_max_hp, left_mp, left_max_mp, left_sprite,
    right_name, right_level, right_hp, right_max_hp, right_mp, right_max_mp, right_sprite,
    right_is_player=False,
    background=None,
):
    # ── Background locked per battle ─────────────────────────────────────
    if background:
        bg_path = BACKGROUNDS_DIR / background
    else:
        bg_path = pick_background_for_battle(str(battle_id))

    if bg_path and bg_path.exists():
        bg = Image.open(bg_path).convert("RGBA")
        bg = bg.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
        darkener = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 80))
        canvas = Image.alpha_composite(bg, darkener)
    else:
        canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (20, 15, 40, 255))

    # ── Sprites ───────────────────────────────────────────────────────────
    sprite_size = (120, 120)
    sprite_y    = CANVAS_H - sprite_size[1] - 20

    enemy_folder  = AVATARS_DIR if right_is_player else ENEMIES_DIR
    player_folder = AVATARS_DIR

    # Enemy on LEFT  → flip=True  so it faces RIGHT toward player
    # Player on RIGHT → flip=False so it naturally faces LEFT toward enemy
    enemy_img  = _load_sprite(right_sprite, enemy_folder,  flip=True,  size=sprite_size)
    player_img = _load_sprite(left_sprite,  player_folder, flip=False, size=sprite_size)

    enemy_sprite_x  = 60
    player_sprite_x = CANVAS_W - sprite_size[0] - 60

    canvas.paste(enemy_img,  (enemy_sprite_x,  sprite_y), enemy_img)
    canvas.paste(player_img, (player_sprite_x, sprite_y), player_img)

    # ── Stat cards ────────────────────────────────────────────────────────
    card_w = 180
    card_y = sprite_y - 74

    _draw_stat_card(canvas,
                    x=enemy_sprite_x - 20, y=card_y,
                    name=right_name, level=right_level,
                    hp=right_hp, max_hp=right_max_hp,
                    mp=right_mp, max_mp=right_max_mp,
                    width=card_w)

    _draw_stat_card(canvas,
                    x=player_sprite_x - (card_w - sprite_size[0]) + 20, y=card_y,
                    name=left_name, level=left_level,
                    hp=left_hp, max_hp=left_max_hp,
                    mp=left_mp, max_mp=left_max_mp,
                    width=card_w)

    # ── VS badge ──────────────────────────────────────────────────────────
    vs_x = CANVAS_W // 2 - 18
    vs_y = sprite_y + 40
    badge = Image.new("RGBA", (36, 36), (10, 8, 20, 220))
    bd = ImageDraw.Draw(badge)
    bd.ellipse([0, 0, 35, 35], outline=(140, 90, 255, 200), width=2)
    bd.text((6, 8), "VS", font=FONT_SMALL, fill=(167, 139, 250))
    canvas.paste(badge, (vs_x, vs_y), badge)

    # ── Save ──────────────────────────────────────────────────────────────
    out_path = TEMP_DIR / f"battle_{battle_id}.png"
    canvas.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path
