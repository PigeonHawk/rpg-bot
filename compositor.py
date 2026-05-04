from PIL import Image, ImageDraw, ImageFont
import os
import random
import numpy as np
from pathlib import Path

BACKGROUNDS_DIR = Path("assets/backgrounds")
AVATARS_DIR     = Path("assets/avatars")
ENEMIES_DIR     = Path("assets/enemies")
TEMP_DIR        = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

CANVAS_W = 1920
CANVAS_H = 1080

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

FONT_NAME = _font(48)

# ── Remove baked-in black background from sprites ────────────────────────────
def _remove_black_bg(img: Image.Image, threshold: int = 30) -> Image.Image:
    """
    Make near-black pixels transparent.
    threshold: pixels where R,G,B are all below this value become transparent.
    """
    img = img.convert("RGBA")
    data = np.array(img, dtype=np.uint8)

    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]

    # Mask: pixels that are very dark (near black)
    black_mask = (r.astype(int) + g.astype(int) + b.astype(int)) < (threshold * 3)

    # Set those pixels fully transparent
    data[:,:,3] = np.where(black_mask, 0, a)

    return Image.fromarray(data, "RGBA")

# ── Sprite loader ─────────────────────────────────────────────────────────────
def _load_sprite(filename: str, folder: Path, flip: bool = False, size=(480, 480)) -> Image.Image:
    path = folder / filename
    if not path.exists():
        return Image.new("RGBA", size, (0, 0, 0, 0))
    img = Image.open(path).convert("RGBA")
    # Remove baked-in black background
    img = _remove_black_bg(img, threshold=25)
    img = img.resize(size, Image.NEAREST)
    if flip:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    return img

# ── Composite with proper alpha ───────────────────────────────────────────────
def _composite(canvas: Image.Image, img: Image.Image, x: int, y: int) -> Image.Image:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(img, (x, y), img)
    return Image.alpha_composite(canvas, layer)

# ── Name badge above sprite ───────────────────────────────────────────────────
def _draw_name_badge(canvas: Image.Image, name: str, x: int, y: int, width: int = 500) -> Image.Image:
    badge_h = 65
    badge = Image.new("RGBA", (width, badge_h), (8, 6, 20, 190))
    cd = ImageDraw.Draw(badge)
    cd.rectangle([0, 0, width-1, badge_h-1], outline=(140, 90, 255, 200), width=2)
    cd.text((16, 12), name.upper(), font=FONT_NAME, fill=(240, 192, 64))
    return _composite(canvas, badge, x, y)

# ── Main render ───────────────────────────────────────────────────────────────
def render_battle_frame(
    battle_id,
    left_name,  left_level,  left_hp,  left_max_hp,  left_mp,  left_max_mp,  left_sprite,
    right_name, right_level, right_hp, right_max_hp, right_mp, right_max_mp, right_sprite,
    right_is_player=False,
    background=None,
):
    bg_path = BACKGROUNDS_DIR / background if background else pick_background_for_battle(str(battle_id))

    if bg_path and Path(bg_path).exists():
        bg = Image.open(bg_path).convert("RGBA")
        bg = bg.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
        dark = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 60))
        canvas = Image.alpha_composite(bg, dark)
    else:
        canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (20, 15, 40, 255))

    SPRITE_SIZE = (480, 480)
    MARGIN      = 100
    SPRITE_Y    = CANVAS_H - SPRITE_SIZE[1] - 60
    BADGE_W     = 500

    ENEMY_X  = MARGIN
    PLAYER_X = CANVAS_W - SPRITE_SIZE[0] - MARGIN

    enemy_folder  = AVATARS_DIR if right_is_player else ENEMIES_DIR
    player_folder = AVATARS_DIR

    # Enemy LEFT — flip=True faces RIGHT toward player
    # Player RIGHT — flip=False naturally faces LEFT toward enemy
    enemy_img  = _load_sprite(right_sprite, enemy_folder,  flip=True,  size=SPRITE_SIZE)
    player_img = _load_sprite(left_sprite,  player_folder, flip=False, size=SPRITE_SIZE)

    canvas = _composite(canvas, enemy_img,  ENEMY_X,  SPRITE_Y)
    canvas = _composite(canvas, player_img, PLAYER_X, SPRITE_Y)

    # Name badges above sprites
    canvas = _draw_name_badge(canvas, right_name,
                              x=ENEMY_X, y=SPRITE_Y - 75, width=BADGE_W)
    canvas = _draw_name_badge(canvas, left_name,
                              x=PLAYER_X + SPRITE_SIZE[0] - BADGE_W, y=SPRITE_Y - 75, width=BADGE_W)

    out_path = TEMP_DIR / f"battle_{battle_id}.png"
    canvas.save(str(out_path), "PNG")
    return out_path
