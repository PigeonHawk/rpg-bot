import json
import os
from pathlib import Path

DATA_FILE = Path("data/players.json")

def _load() -> dict:
    if not DATA_FILE.exists():
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def _save(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_player(user_id: int) -> dict | None:
    """Return player data or None if not registered."""
    data = _load()
    return data.get(str(user_id))

def register_player(user_id: int, username: str, avatar: str) -> dict:
    """Create a new player record."""
    data = _load()
    player = {
        "id": user_id,
        "username": username,
        "avatar": avatar,          # filename of chosen avatar sprite
        "hp": 50,
        "max_hp": 50,
        "gil": 200,
        "wins": 0,
        "losses": 0,
        "paused_battle": None      # stores battle state if paused mid-pve
    }
    data[str(user_id)] = player
    _save(data)
    return player

def update_player(user_id: int, **kwargs):
    """Update specific fields on a player record."""
    data = _load()
    key = str(user_id)
    if key not in data:
        return
    data[key].update(kwargs)
    _save(data)

def reset_hp(user_id: int):
    """Restore player to full HP."""
    data = _load()
    key = str(user_id)
    if key in data:
        data[key]["hp"] = data[key]["max_hp"]
        _save(data)

def add_gil(user_id: int, amount: int):
    data = _load()
    key = str(user_id)
    if key in data:
        data[key]["gil"] = data[key].get("gil", 0) + amount
        _save(data)

def is_registered(user_id: int) -> bool:
    return get_player(user_id) is not None
