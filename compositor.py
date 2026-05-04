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

# ── Canvas 1920x1080 ──────────────────────────────────────────────────────────
CANVAS_W = 1920
CANVAS_H = 1080

# ── Background cache ──────────────────────────────────────────────────────────
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

FONT_NAME  = _font(36)   # character name
FONT_LABEL = _font(28)   # LV / HP / MP labels
FONT_VAL   = _font(26)   # hp/mp values

# ── Colours ───────────────────────────────────────────────────────────────────
GOLD     = (240, 192,  64)
WHITE    = (230, 230, 240)
PURPLE   = (180, 150, 255)
HP_GREEN = ( 50, 210, 100)
HP_RED   = (230,  60,  60)
MP_BLUE  = ( 70, 150, 255)
TRACK_C  = ( 40,  40,  60)

# ── Sprite loader ─────────────────────────────────────────────────────────────
def _load_sprite(filename: str, folder: Path, flip: bool = False, size=(420, 420)) -> Image.Image:
    path = folder / filename
    if not path.exists():
        return Image.new("RGBA", size, (0, 0, 0, 0))
    img = Image.open(path).convert("RGBA")
    img = img.resize(size, Image.NEAREST)
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    return img

# ── Composite with proper alpha ───────────────────────────────────────────────
def _composite(canvas: Image.Image, img: Image.Image, x: int, y: int) -> Image.Image:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(img, (x, y), img)
    return Image.alpha_composite(canvas, layer)

# ── Stat card ─────────────────────────────────────────────────────────────────
def _draw_stat_card(canvas: Image.Image, x: int, y: int,
                    name: str, level: int,
                    hp: int, max_hp: int,
                    mp: int, max_mp: int,
                    width: int = 500) -> Image.Image:

    PAD     = 22
    NAME_H  = 44
    BAR_H   = 28
    LABEL_H = 34
    SPACING = 20
    card_h  = PAD + NAME_H + SPACING + BAR_H + LABEL_H + SPACING + BAR_H + LABEL_H + PAD

    card = Image.new("RGBA", (width, card_h), (8, 6, 20, 215))
    cd   = ImageDraw.Draw(card)

    # Border
    cd.rectangle([0, 0, width-1, card_h-1], outline=(140, 90, 255, 230), width=3)

    # Name + level
    cd.text((PAD, PAD), name.upper(), font=FONT_NAME, fill=GOLD)
    lv_str = f"LV{level}"
    lv_w   = int(cd.textlength(lv_str, font=FONT_LABEL))
    cd.text((width - lv_w - PAD, PAD + 4), lv_str, font=FONT_LABEL, fill=PURPLE)

    bx  = PAD
    bw  = width - PAD * 2

    # ── HP bar ────────────────────────────────────────────────────────────
    hpy = PAD + NAME_H + SPACING
    cd.rectangle([bx, hpy, bx + bw, hpy + BAR_H], fill=TRACK_C)
    hp_pct = max(0.0, min(1.0, hp / max_hp))
    hp_col = HP_GREEN if hp_pct > 0.3 else HP_RED
    fw = int(bw * hp_pct)
    if fw > 0:
        cd.rectangle([bx, hpy, bx + fw, hpy + BAR_H], fill=hp_col)
        cd.rectangle([bx, hpy, bx + fw, hpy + BAR_H // 3], fill=(255, 255, 255, 55))
    cd.text((bx, hpy + BAR_H + 5), f"HP  {hp} / {max_hp}", font=FONT_VAL, fill=WHITE)

    # ── MP bar ────────────────────────────────────────────────────────────
    mpy = hpy + BAR_H + LABEL_H + SPACING
    cd.rectangle([bx, mpy, bx + bw, mpy + BAR_H], fill=TRACK_C)
    mp_pct = max(0.0, min(1.0, mp / max_mp))
    fw = int(bw * mp_pct)
    if fw > 0:
        cd.rectangle([bx, mpy, bx + fw, mpy + BAR_H], fill=MP_BLUE)
        cd.rectangle([bx, mpy, bx + fw, mpy + BAR_H // 3], fill=(255, 255, 255, 55))
    cd.text((bx, mpy + BAR_H + 5), f"MP  {mp} / {max_mp}", font=FONT_VAL, fill=WHITE)

    return _composite(canvas, card, x, y)

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
        dark = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 60))
        canvas = Image.alpha_composite(bg, dark)
    else:
        canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (20, 15, 40, 255))

    # ── Layout ────────────────────────────────────────────────────────────
    SPRITE_SIZE = (420, 420)
    MARGIN      = 80
    SPRITE_Y    = CANVAS_H - SPRITE_SIZE[1] - 40
    CARD_W      = 500
    CARD_Y      = 30

    ENEMY_X  = MARGIN
    PLAYER_X = CANVAS_W - SPRITE_SIZE[0] - MARGIN

    # ── Sprites ───────────────────────────────────────────────────────────
    enemy_folder  = AVATARS_DIR if right_is_player else ENEMIES_DIR
    player_folder = AVATARS_DIR

    # Enemy LEFT  — flip=True  faces RIGHT toward player
    # Player RIGHT — flip=False naturally faces LEFT toward enemy
    enemy_img  = _load_sprite(right_sprite, enemy_folder,  flip=True,  size=SPRITE_SIZE)
    player_img = _load_sprite(left_sprite,  player_folder, flip=False, size=SPRITE_SIZE)

    canvas = _composite(canvas, enemy_img,  ENEMY_X,  SPRITE_Y)
    canvas = _composite(canvas, player_img, PLAYER_X, SPRITE_Y)

    # ── Stat cards ────────────────────────────────────────────────────────
    # Enemy card top-left
    canvas = _draw_stat_card(canvas,
                             x=ENEMY_X, y=CARD_Y,
                             name=right_name, level=right_level,
                             hp=right_hp,  max_hp=right_max_hp,
                             mp=right_mp,  max_mp=right_max_mp,
                             width=CARD_W)

    # Player card top-right aligned to player sprite
    canvas = _draw_stat_card(canvas,
                             x=PLAYER_X + SPRITE_SIZE[0] - CARD_W, y=CARD_Y,
                             name=left_name,  level=left_level,
                             hp=left_hp,   max_hp=left_max_hp,
                             mp=left_mp,   max_mp=left_max_mp,
                             width=CARD_W)

    # ── Save — keep RGBA, never convert to RGB ────────────────────────────
    out_path = TEMP_DIR / f"battle_{battle_id}.png"
    canvas.save(str(out_path), "PNG")
    return out_path
