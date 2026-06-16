import discord
from discord.ext import commands
import json
import os
import random
from datetime import datetime

# ── Storage ───────────────────────────────────────────────────────────────────
#
# data/quotes.json structure:
# {
#   "quotes": [
#     {
#       "text":       str,
#       "name":       str,   # display name at time of saving
#       "user_id":    int | None,  # None for plain-name manual adds
#       "added_by":   str,   # display name of who added it
#       "date":       str,   # ISO format
#     },
#     ...
#   ]
# }

QUOTES_PATH = "data/quotes.json"


def load_quotes() -> list[dict]:
    if not os.path.exists(QUOTES_PATH):
        return []
    try:
        with open(QUOTES_PATH, "r") as f:
            data = json.load(f)
        return data.get("quotes", [])
    except (json.JSONDecodeError, OSError):
        return []


def save_quotes(quotes: list[dict]) -> None:
    os.makedirs(os.path.dirname(QUOTES_PATH), exist_ok=True)
    with open(QUOTES_PATH, "w") as f:
        json.dump({"quotes": quotes}, f, indent=2)


quotes_db: list[dict] = load_quotes()


# ── Helpers ───────────────────────────────────────────────────────────────────

def find_quotes_by_name(name: str) -> list[dict]:
    """Return all quotes matching a name (case-insensitive).
    Matches against stored name OR display name if user_id is set."""
    name_lower = name.lower()
    return [q for q in quotes_db if q["name"].lower() == name_lower]


def build_quote_embed(quote: dict) -> discord.Embed:
    embed = discord.Embed(
        description=f'💬 *"{quote["text"]}"*',
        color=discord.Color.red(),
    )
    embed.set_footer(text=f"— {quote['name']} | Added by {quote['added_by']} on {quote['date'][:10]}")
    return embed


def build_list_embed(name: str, matched: list[dict]) -> discord.Embed:
    embed = discord.Embed(
        title=f"📋 Quotes from {name}",
        color=discord.Color.blurple(),
    )
    lines = []
    for i, q in enumerate(matched):
        text = q["text"]
        if len(text) > 80:
            text = text[:78] + "…"
        lines.append(f"`{i+1}.` {text}")
    embed.description = "\n".join(lines)
    embed.set_footer(text=f"{len(matched)} quote{'s' if len(matched) != 1 else ''} saved")
    return embed


# ── Cog ───────────────────────────────────────────────────────────────────────

class Quotes(commands.Cog):
    """Save and retrieve quotes from your server members."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── !quote add ────────────────────────────────────────────────────────────

    @commands.group(name="quote", invoke_without_command=True)
    async def quote(self, ctx: commands.Context, *, name: str = None):
        """Pull a random quote. Usage: !quote <name> or !quote random"""
        if name is None:
            await ctx.send(
                "Usage:\n"
                "`!quote <name>` — random quote from that person\n"
                "`!quote random` — random quote from anyone\n"
                "`!quote list <name>` — all quotes from that person\n"
                "`!quote add <message_id>` — save a quote by message ID\n"
                "`!quote add @User <text>` — save a quote by pinging\n"
                "`!quote add <name> <text>` — save a quote by name\n"
            )
            return

        if name.lower() == "random":
            if not quotes_db:
                await ctx.send("❌ No quotes saved yet! Use `!quote add` to save one.")
                return
            q = random.choice(quotes_db)
            await ctx.send(embed=build_quote_embed(q))
            return

        matched = find_quotes_by_name(name)
        if not matched:
            await ctx.send(f"❌ No quotes found for **{name}**.")
            return

        q = random.choice(matched)
        await ctx.send(embed=build_quote_embed(q))

    @quote.command(name="add")
    async def quote_add(self, ctx: commands.Context, *, args: str = None):
        """Add a quote. Three ways:
        !quote add <message_id>
        !quote add @User <text>
        !quote add <name> <text>
        """
        if not args:
            await ctx.send(
                "Usage:\n"
                "`!quote add <message_id>` — auto-grab text and sender\n"
                "`!quote add @User <text>` — ping the user and add quote\n"
                "`!quote add <name> <text>` — manually type name and quote\n"
            )
            return

        added_by = ctx.author.display_name
        date = datetime.now().isoformat()

        # ── Method 1: Message ID (pure digits) ───────────────────────────────
        parts = args.strip().split(None, 1)
        if parts[0].isdigit() and len(parts) == 1:
            message_id = int(parts[0])
            try:
                msg = await ctx.channel.fetch_message(message_id)
            except discord.NotFound:
                # Try searching other channels in the guild
                msg = None
                for channel in ctx.guild.text_channels:
                    try:
                        msg = await channel.fetch_message(message_id)
                        break
                    except (discord.NotFound, discord.Forbidden):
                        continue

            if msg is None:
                await ctx.send("❌ Couldn't find that message. Make sure the ID is correct.")
                return
            if not msg.content:
                await ctx.send("❌ That message has no text content to quote.")
                return

            quote_entry = {
                "text": msg.content,
                "name": msg.author.display_name,
                "user_id": msg.author.id,
                "added_by": added_by,
                "date": date,
            }
            quotes_db.append(quote_entry)
            save_quotes(quotes_db)

            embed = build_quote_embed(quote_entry)
            await ctx.send(f"✅ Quote saved from **{msg.author.display_name}**!", embed=embed)
            return

        # ── Method 2: @ping + text ────────────────────────────────────────────
        if ctx.message.mentions and len(parts) >= 2:
            user = ctx.message.mentions[0]
            # Strip the mention from the text
            text = args
            for mention in [f"<@{user.id}>", f"<@!{user.id}>"]:
                text = text.replace(mention, "").strip()

            if not text:
                await ctx.send("❌ Please include the quote text after the @mention.")
                return

            quote_entry = {
                "text": text,
                "name": user.display_name,
                "user_id": user.id,
                "added_by": added_by,
                "date": date,
            }
            quotes_db.append(quote_entry)
            save_quotes(quotes_db)

            embed = build_quote_embed(quote_entry)
            await ctx.send(f"✅ Quote saved from **{user.display_name}**!", embed=embed)
            return

        # ── Method 3: Plain name + text ───────────────────────────────────────
        if len(parts) >= 2:
            name = parts[0]
            text = parts[1]

            quote_entry = {
                "text": text,
                "name": name,
                "user_id": None,
                "added_by": added_by,
                "date": date,
            }
            quotes_db.append(quote_entry)
            save_quotes(quotes_db)

            embed = build_quote_embed(quote_entry)
            await ctx.send(f"✅ Quote saved from **{name}**!", embed=embed)
            return

        await ctx.send(
            "❌ Couldn't parse that. Usage:\n"
            "`!quote add <message_id>`\n"
            "`!quote add @User <text>`\n"
            "`!quote add <name> <text>`"
        )

    # ── !quote list ───────────────────────────────────────────────────────────

    @quote.command(name="list")
    async def quote_list(self, ctx: commands.Context, *, name: str = None):
        """List all quotes from a person. Usage: !quote list <name>"""
        if not name:
            await ctx.send("Usage: `!quote list <name>`")
            return

        matched = find_quotes_by_name(name)
        if not matched:
            await ctx.send(f"❌ No quotes found for **{name}**.")
            return

        await ctx.send(embed=build_list_embed(name, matched))

    # ── !quote random (also handled in base command) ──────────────────────────

    @quote.command(name="random")
    async def quote_random(self, ctx: commands.Context):
        """Pull a random quote from anyone."""
        if not quotes_db:
            await ctx.send("❌ No quotes saved yet! Use `!quote add` to save one.")
            return
        q = random.choice(quotes_db)
        await ctx.send(embed=build_quote_embed(q))

    # ── !quote count ──────────────────────────────────────────────────────────

    @quote.command(name="count")
    async def quote_count(self, ctx: commands.Context, *, name: str = None):
        """Show how many quotes are saved. Optionally filter by name."""
        if name:
            matched = find_quotes_by_name(name)
            await ctx.send(f"📊 **{name}** has **{len(matched)}** quote{'s' if len(matched) != 1 else ''} saved.")
        else:
            await ctx.send(f"📊 **{len(quotes_db)}** total quote{'s' if len(quotes_db) != 1 else ''} saved across all members.")

    # ── !qlist, !qadd shortcuts ───────────────────────────────────────────────

    @commands.command(name="qadd")
    async def qadd(self, ctx: commands.Context, *, args: str = None):
        """Shortcut for !quote add"""
        await ctx.invoke(self.quote_add, args=args)

    @commands.command(name="qlist")
    async def qlist(self, ctx: commands.Context, *, name: str = None):
        """Shortcut for !quote list <name>"""
        await ctx.invoke(self.quote_list, name=name)

    @commands.command(name="qrandom")
    async def qrandom(self, ctx: commands.Context):
        """Shortcut for !quote random"""
        await ctx.invoke(self.quote_random)


# ── Setup hook ────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot):
    await bot.add_cog(Quotes(bot))
