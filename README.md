# ⚔️ ArcaneRPG Discord Bot

A Final Fantasy-inspired turn-based RPG bot with elemental combat,
PvE boss fights, and PvP duels — all rendered as composited battle images.

---

## 📁 Project Structure

```
rpgbot/
├── bot.py                  ← Entry point
├── compositor.py           ← Image generation (battle frames)
├── data_manager.py         ← Player data (JSON)
├── requirements.txt
├── cogs/
│   └── rpg.py              ← All game logic & commands
├── assets/
│   ├── backgrounds/        ← Battle backgrounds (.jpg or .png)
│   │                         Drop any number in here — picked randomly each fight
│   ├── avatars/            ← Player avatar sprites (.png)
│   └── enemies/            ← Enemy sprites (.png)
├── data/
│   └── players.json        ← Auto-created on first run
└── temp/                   ← Auto-created — generated battle frames live here
```

---

## ⚙️ Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Add your bot token
Open `bot.py` and replace:
```python
TOKEN = "YOUR_BOT_TOKEN_HERE"
```

### 3. Add your assets

**Backgrounds** — drop any `.jpg` or `.png` files into `assets/backgrounds/`.
The bot picks one at random for each new battle.

**Avatars** — drop player sprite `.png` files into `assets/avatars/`.
Then register them in `cogs/rpg.py`:
```python
AVAILABLE_AVATARS = [
    {"name": "Knight", "file": "knight.png"},
    {"name": "Mage",   "file": "mage.png"},
    # add more here
]
```

**Enemies** — drop enemy sprite `.png` files into `assets/enemies/`.
Then register them in `cogs/rpg.py`:
```python
AVAILABLE_ENEMIES = [
    {"name": "Goblin", "file": "goblin.png", "level": 1},
    {"name": "Dragon", "file": "dragon.png", "level": 5},
    # add more here
]
```

### 4. Run the bot
```bash
python bot.py
```

---

## 🎮 Commands

| Command | Description |
|---|---|
| `!rpg` | Start a PvE boss fight. First time = choose your avatar. |
| `!rpg @user` | Challenge another registered player to a duel. |
| `!stats` | View your gil, wins, and losses. |
| `!help_rpg` | Show all commands and element rules. |

---

## ⚗️ Element System (Rock Paper Scissors)

```
🔥 Fire   beats  ❄️ Ice
❄️ Ice    beats  🌪️ Wind
🌪️ Wind   beats  🔥 Fire
Same element  =  Draw (no damage)
```

Each hit deals **10 HP**. Both players start at **50 HP**.
First to 0 loses.

---

## 💰 Gil

- Players start with **200 gil**
- PvE wins reward **20–80 gil** (random)
- PvP wins also reward random gil
- Store system coming soon!

---

## ⏸️ Pause System

If a player doesn't respond within **30 seconds** after a PvE win prompt,
their session is paused. Typing `!rpg` again lets them resume or abandon.

---

## 🗺️ Roadmap / What to add next

- [ ] Drop real avatar/enemy sprites into assets/
- [ ] Add more backgrounds (random pool grows automatically)
- [ ] Add a `!shop` command to spend gil
- [ ] Add XP and leveling system
- [ ] Add special moves / spells that cost MP
- [ ] Add status effects (burn, freeze, stun)
