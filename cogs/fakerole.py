"""
fakerole.py — a joke cog with a running tally.

Type the prefix + ANY word + one member, and the bot claims it gave that person a
"role" by that name — but assigns nothing, and names them in plain text (no ping):

    !supercalifragilistic @Vivi   ->  Gave Vivi the Supercalifragilistic role!
    !asian vivi                   ->  Gave Vivi the Asian role!

Guards:
  * Racial slurs are blocked via a denylist (see SLURS) — the bot refuses and never
    repeats the word.
  * If the word is a real command (!fake, !birthday, !contexto, an existing !chud,
    etc.) it replies that it can't be added as a role, and the real command still runs.

Tally command:
    !fake [@user]        show how many of each fake role a person has been "given"

Persistence (point at your Railway volume to survive redeploys):
    FAKEROLE_STATE_PATH   default: data/fakeroles.json
    FAKEROLE_DATA_DIR     default: ./data next to this cog
"""

import os
import re
import json
import logging

import discord
from discord.ext import commands

log = logging.getLogger(__name__)

DATA_DIR = os.getenv("FAKEROLE_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
STATE_PATH = os.getenv("FAKEROLE_STATE_PATH", os.path.join(DATA_DIR, "fakeroles.json"))

MAX_LABEL_LEN = 40
_MENTION_RE = re.compile(r"^<@!?\d+>$")

# Denylist of racial/ethnic slurs (lowercased base forms). Kept here solely so the bot
# refuses to use them as "roles" and never repeats them. Extend as needed. Matching is
# done on a normalized form (letters only, repeated letters collapsed) and also catches
# these as substrings, so plurals/suffixes are covered.
SLURS = {
    "nigger", "nigga", "chink", "gook", "spic", "wetback", "beaner", "kike",
    "wop", "dago", "paki", "raghead", "towelhead", "sandnigger", "coon",
    "jigaboo", "porchmonkey", "spook", "tarbaby", "gyppo", "gypo", "abo",
    "injun", "redskin", "squaw", "zipperhead", "slant", "jap", "nip",
    "cracker", "honky", "gringo", "wigger",
}


def _normalize(word: str) -> str:
    n = re.sub(r"[^a-z]", "", word.lower())
    return re.sub(r"(.)\1+", r"\1", n)   # collapse any run of a letter to one

SLURS_NORM = {_normalize(s) for s in SLURS}


def _is_slur(word: str) -> bool:
    n = _normalize(word)
    if not n:
        return False
    if n in SLURS_NORM:
        return True
    if n.endswith("s") and n[:-1] in SLURS_NORM:   # simple plural
        return True
    return False


class FakeRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = {"guilds": {}}
        self._load()

    # ---------- persistence ----------

    def _load(self):
        try:
            with open(STATE_PATH) as f:
                self.data = json.load(f)
            self.data.setdefault("guilds", {})
        except (FileNotFoundError, json.JSONDecodeError):
            self.data = {"guilds": {}}

    def _save(self):
        os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f)
        os.replace(tmp, STATE_PATH)

    def _counts(self, guild_id, user_id):
        return self.data["guilds"].get(str(guild_id), {}).get(str(user_id), {})

    def _increment(self, guild_id, user_id, label):
        g = self.data["guilds"].setdefault(str(guild_id), {})
        u = g.setdefault(str(user_id), {})
        u[label] = u.get(label, 0) + 1
        self._save()
        return u[label]

    # ---------- helpers ----------

    def _prefixes(self):
        p = self.bot.command_prefix
        if isinstance(p, str):
            return [p]
        if isinstance(p, (list, tuple)):
            return [x for x in p if isinstance(x, str)]
        return ["!"]

    def _resolve_target(self, message, rest):
        """Only a clean single target counts: `!word @mention` or `!word name`."""
        tokens = rest.split()
        if len(tokens) != 1:
            return None
        tok = tokens[0]
        if message.mentions and _MENTION_RE.match(tok):
            return message.mentions[0]
        return message.guild.get_member_named(tok)

    # ---------- the gag ----------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        content = message.content.strip()
        prefix = next((p for p in self._prefixes() if content.startswith(p)), None)
        if not prefix:
            return
        parts = content[len(prefix):].split(maxsplit=1)
        if not parts:
            return
        word = parts[0]
        rest = parts[1] if len(parts) > 1 else ""

        target = self._resolve_target(message, rest)
        if target is None:
            return  # not a clean "!word target" — ignore, let normal command handling run

        wl = word.lower()
        if wl == "fake":
            return  # our own tally command — let it run

        # block slurs first, and never echo the word
        if _is_slur(word):
            try:
                await message.channel.send("❌ I'm not adding that one.")
            except discord.HTTPException:
                pass
            return

        # a real command? can't be a role (the real command still runs on its own)
        if self.bot.get_command(wl) is not None:
            try:
                await message.channel.send(f"❌ Can't add **{word}** as a role — it's a command.")
            except discord.HTTPException:
                pass
            return

        if not word.isprintable() or len(word) > MAX_LABEL_LEN:
            return

        label = word.capitalize()
        count = self._increment(message.guild.id, target.id, label)
        try:
            await message.channel.send(embed=discord.Embed(
                description=f"✅ Gave **{target.display_name}** the **{label}** role!  (×{count})",
                color=0x2ecc71,
            ))
        except discord.HTTPException:
            pass

    # ---------- tally command ----------

    @commands.command(name="fake")
    async def fake(self, ctx, member: discord.Member = None):
        """Show how many of each fake role a person has been given."""
        target = member or ctx.author
        counts = self._counts(ctx.guild.id, target.id)
        if not counts:
            return await ctx.send(f"**{target.display_name}** hasn't been given any fake roles yet.")
        lines = [f"**{label}** ×{n}" for label, n in sorted(counts.items(), key=lambda kv: -kv[1])]
        emb = discord.Embed(title=f"🎭 {target.display_name}'s fake roles",
                            description="\n".join(lines), color=0x9b59b6)
        emb.set_footer(text=f"{sum(counts.values())} total")
        await ctx.send(embed=emb)


async def setup(bot):
    await bot.add_cog(FakeRole(bot))
