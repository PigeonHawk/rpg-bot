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

# ── Background cache — locked per battle, cleared on new battle only ──────────
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

# ── Remove baked-in black background ─────────────────────────────────────────
def _remove_black_bg(img: Image.Image, threshold: int = 25) -> Image.Image:
    img = img.convert("RGBA")
    data = np.array(img, dtype=np.uint8)
    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
    black_mask = (r.astype(int) + g.astype(int) + b.astype(int)) < (threshold * 3)
    data[:,:,3] = np.where(black_mask, 0, a)
    return Image.fromarray(data, "RGBA")

# ── Sprite loader ─────────────────────────────────────────────────────────────
def _load_sprite(filename: str, folder: Path, flip: bool = False, size=(700, 700)) -> Image.Image:
    path = folder / filename
    if not path.exists():
        return Image.new("RGBA", size, (0, 0, 0, 0))
    img = Image.open(path).convert("RGBA")
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

# ── Main render ───────────────────────────────────────────────────────────────
def render_battle_frame(
    battle_id,
    left_name,  left_level,  left_hp,  left_max_hp,  left_mp,  left_max_mp,  left_sprite,
    right_name, right_level, right_hp, right_max_hp, right_mp, right_max_mp, right_sprite,
    right_is_player=False,
    background=None,
):
    # ── Background — locked per battle, never changes mid-fight ──────────
    bg_path = BACKGROUNDS_DIR / background if background else pick_background_for_battle(str(battle_id))

    if bg_path and Path(bg_path).exists():
        bg = Image.open(bg_path).convert("RGBA")
        bg = bg.resize((CANVAS_W, CANVAS_H), Image.LANCZOS)
        dark = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 60))
        canvas = Image.alpha_composite(bg, dark)
    else:
        canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (20, 15, 40, 255))

    # ── Layout — sprites only, no stat overlays ───────────────────────────
    SPRITE_SIZE = (700, 700)
    MARGIN      = 80
    SPRITE_Y    = CANVAS_H - SPRITE_SIZE[1] - 20

    ENEMY_X  = MARGIN
    PLAYER_X = CANVAS_W - SPRITE_SIZE[0] - MARGIN

    enemy_folder  = AVATARS_DIR if right_is_player else ENEMIES_DIR
    player_folder = AVATARS_DIR

    # Enemy LEFT  — flip=True  faces RIGHT toward player
    # Player RIGHT — flip=False naturally faces LEFT toward enemy
    enemy_img  = _load_sprite(right_sprite, enemy_folder,  flip=True,  size=SPRITE_SIZE)
    player_img = _load_sprite(left_sprite,  player_folder, flip=False, size=SPRITE_SIZE)

    canvas = _composite(canvas, enemy_img,  ENEMY_X,  SPRITE_Y)
    canvas = _composite(canvas, player_img, PLAYER_X, SPRITE_Y)

    out_path = TEMP_DIR / f"battle_{battle_id}.png"
    canvas.save(str(out_path), "PNG")
    return out_path
