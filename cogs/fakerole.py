"""
fakerole.py — a joke cog with a running tally.

When someone uses a trigger command followed by a member (an @mention or their exact
name), the bot claims it gave that person the matching "role" — but assigns nothing.
Every grant is counted, so the gag builds up over time, and `!fake` shows the tally.

Triggers require the ! prefix and must start the message:
    !latinx @Vivi        /  !latinx vivi
    !asian @Josh         /  !black josh   /  !chud @someone

Tally command:
    !fake [@user]        show how many of each fake role a person has been "given"

Persistence (point at your Railway volume to survive redeploys):
    FAKEROLE_STATE_PATH   default: data/fakeroles.json
    FAKEROLE_DATA_DIR     default: ./data next to this cog
"""

import os
import json
import logging

import discord
from discord.ext import commands

log = logging.getLogger(__name__)

DATA_DIR = os.getenv("FAKEROLE_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
STATE_PATH = os.getenv("FAKEROLE_STATE_PATH", os.path.join(DATA_DIR, "fakeroles.json"))

# trigger command (lowercase, used after the ! prefix)  ->  display label
TRIGGERS = {
    "latinx": "Latinx",
    "filipinx": "Filipinx",
    "asian": "Asian",
    "hispanic": "Hispanic",
    "white": "White",
    "black": "Black",
    "european": "European",
    "chud": "Chud",
    "botfrag": "Botfrag",
}


class FakeRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = {"guilds": {}}
        self._load()
        self._register_commands()

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

    # ---------- one command per trigger, registered dynamically ----------

    def _register_commands(self):
        for word, label in TRIGGERS.items():
            self.bot.add_command(self._make_command(word, label))

    def cog_unload(self):
        for word in TRIGGERS:
            self.bot.remove_command(word)

    def _make_command(self, word, label):
        cog = self

        @commands.command(name=word)
        async def _cmd(ctx, member: discord.Member = None):
            target = member or (ctx.message.mentions[0] if ctx.message.mentions else None)
            if target is None:
                return  # no valid user given — stay quiet
            count = cog._increment(ctx.guild.id, target.id, label)
            try:
                await ctx.send(embed=discord.Embed(
                    description=f"✅ Gave {target.mention} the **{label}** role!  (×{count})",
                    color=0x2ecc71,
                ))
            except discord.HTTPException:
                pass

        _cmd.help = f"(fun) fake-assign the {label} role"
        return _cmd

    # ---------- tally command ----------

    @commands.command(name="fake")
    async def fake(self, ctx, member: discord.Member = None):
        """Show how many of each fake role a person has been given."""
        target = member or ctx.author
        counts = self._counts(ctx.guild.id, target.id)
        if not counts:
            return await ctx.send(f"{target.mention} hasn't been given any fake roles yet.")
        lines = [f"**{label}** ×{n}" for label, n in sorted(counts.items(), key=lambda kv: -kv[1])]
        emb = discord.Embed(title=f"🎭 {target.display_name}'s fake roles",
                            description="\n".join(lines), color=0x9b59b6)
        emb.set_footer(text=f"{sum(counts.values())} total")
        await ctx.send(embed=emb)


async def setup(bot):
    await bot.add_cog(FakeRole(bot))
