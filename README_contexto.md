# Contexto cog

A Contexto-style semantic word-guessing game for your discord.py bot. There's a
secret word; people type words into the channel and the bot ranks each by how
close its *meaning* is to the secret (rank 1 = the word itself). First to rank 1 wins.

## What you need to do (setup checklist)

1. **Copy the files into your repo**
   - `cogs/contexto.py`
   - `cogs/data/contexto_vectors.npy`, `contexto_vocab.txt`, `contexto_targets.txt`
2. **Load the cog** in `bot.py`, inside `main()` before `await bot.start(TOKEN)`:
   ```python
   await bot.load_extension("cogs.contexto")
   ```
3. **Add numpy** to `requirements.txt` (discord.py is already there):
   ```
   numpy
   ```
4. **Enable the Message Content intent** — the game reads plain messages as guesses,
   so this is required or nothing will register:
   - in code: `intents.message_content = True` on your `commands.Bot(...)`
   - in the Discord Developer Portal → your app → Bot → enable **Message Content Intent**
5. **Give the bot these channel permissions**: Send Messages, Embed Links, Add Reactions,
   and **Manage Messages** (needed to auto-delete players' guesses).
6. **Railway persistence**: set `CONTEXTO_STATE_PATH` to a path on your mounted volume,
   e.g. `/data/contexto_state.json`, and add `cogs/data/contexto_state.json` to `.gitignore`.
7. **Commit & deploy.** The 63 MB `.npy` is fine on GitHub (under the 100 MB limit).

## Files

```
cogs/contexto.py          the cog
cogs/data/                ships with the repo (static)
  contexto_vectors.npy    word vectors, one row per vocab word (~63 MB)
  contexto_vocab.txt      316,435 guessable words (frequency-sorted)
  contexto_targets.txt    148 curated secret words
build_data.py             regenerate the data (see below)
```

Drop `contexto.py` in `cogs/` and the `data/` folder next to it. Only **numpy** is
needed at runtime. The 63 MB `.npy` is under GitHub's 100 MB limit — plain `git add`,
no LFS. There are **316,435 guessable words**.

## The board (live, single message)

The bot keeps ONE board message per game and **edits it in place** as guesses arrive —
no spam of new messages. It shows every guess sorted by rank with a proportional
hot/warm/cold bar, and pins the most recent guess at the top (like contexto.me). If an
edit ever fails (e.g. the message was deleted), it re-posts the board and removes the
old one automatically.

To keep the focus on that board:
- each player's raw guess message is **auto-deleted after ~3s**
- a tiny confirm / ❌ line is posted per guess and **auto-deleted after ~3s**

**Inactivity timeout:** the clock resets on every guess. After **2 minutes** of silence the bot warns that **60 seconds** remain; if still no one guesses, it ends the game and frees the channel for a new one. Tune with `IDLE_WARN` / `IDLE_GRACE` near the top of the cog.

> **Permission:** the bot needs **Manage Messages** in the channel to delete players'
> guesses. Without it, the board and feedback still work, but guesses won't be cleaned up.

## Playing

- `!contexto start` — new game, random secret word (your command message is removed)
- `!contexto start <word>` — set your own secret (best in DM; message is removed)
- just **type a word** — it drops into the live board
- `!contexto board` — re-post the board if it scrolled away
- `!contexto hint` — a word closer than the current best guess
- `!contexto giveup` — end and reveal
- `!contexto leaderboard` — wins per player

`!ctx` is shorthand for `!contexto`.

## Guessing: what gets accepted

The 316k vocab means almost anything real lands. On a miss the bot tries to rescue it:

1. **Morphology** — plurals/tenses map to a base form (`hamsters` → `hamster`). Most
   inflected forms are already in the vocab, so they just rank directly.
2. **Fuzzy match** — near typos (`dargon` → `dragon`, `guitr` → `guitar`), preferring the
   most *common* close word so typos don't resolve to obscure junk.

Corrections are shown in the confirm line, never silent. Genuine misses get ❌.

A few common misspellings (`freind`, `wolrd`) appear in the source corpus often enough to
be real tokens, so they rank as themselves rather than auto-correcting — harmless, since
their vectors sit near the intended word.

## Railway persistence

Board message IDs, active games, and the leaderboard are written to JSON. Point it at your
mounted volume so a redeploy resumes the same live board:

```
CONTEXTO_STATE_PATH=/data/contexto_state.json
```

Add `cogs/data/contexto_state.json` to `.gitignore` (runtime file). The static data files
do get committed.

## Tuning

Constants near the top of `contexto.py`:
- `GREEN` / `ORANGE` — rank thresholds for the 🟩/🟧/🟥 bands
- `BAR_WIDTH`, `BOARD_ROWS` — bar length and how many guesses the board lists
- `GUESS_TTL`, `FEEDBACK_TTL` — seconds before guesses / feedback are deleted
- `SHOW_FEEDBACK` — set `False` to rely on the board alone (no per-guess confirm line)
- `FUZZY_CUTOFF`, `FUZZY_MIN_LEN` — how aggressive typo correction is

Regenerate data with `build_data.py`: `VOCAB_SIZE = None` uses all 316k words; set an
integer for a smaller file. `MODEL` can go from `-50` up to `-300` for sharper meaning at
a bigger file size. Edit `candidate_targets` to change the secret-word pool.

## Note on rate limits

Editing the board on every guess is fine at normal pace; if many people guess in the same
second, Discord may briefly throttle edits and the board will lag a moment (discord.py waits
it out — it won't crash). If your server is very active, raise `GUESS_TTL` slightly or set
`SHOW_FEEDBACK = False` to cut per-guess message volume.
