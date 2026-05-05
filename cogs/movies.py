import discord
from discord.ext import commands
from pathlib import Path
import json
import asyncio
from datetime import datetime

# ── Data file ─────────────────────────────────────────────────────────────────
MOVIES_FILE = Path("playerdata/movies.json")

def _load() -> dict:
    if not MOVIES_FILE.exists():
        MOVIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        return {}
    with open(MOVIES_FILE) as f:
        return json.load(f)

def _save(data: dict):
    with open(MOVIES_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_user_movies(user_id: int) -> list:
    data = _load()
    return data.get(str(user_id), [])

def add_movie(user_id: int, title: str):
    data = _load()
    key  = str(user_id)
    if key not in data:
        data[key] = []
    entry = {
        "title":  title,
        "added":  datetime.now().strftime("%B %d, %Y"),
        "watched": False
    }
    data[key].append(entry)
    _save(data)

def mark_watched(user_id: int, index: int) -> bool:
    data  = _load()
    key   = str(user_id)
    movies = data.get(key, [])
    if 0 <= index < len(movies):
        movies[index]["watched"] = True
        data[key] = movies
        _save(data)
        return True
    return False

def remove_movie(user_id: int, index: int) -> str | None:
    data   = _load()
    key    = str(user_id)
    movies = data.get(key, [])
    if 0 <= index < len(movies):
        removed = movies.pop(index)
        data[key] = movies
        _save(data)
        return removed["title"]
    return None

# ── Cog ───────────────────────────────────────────────────────────────────────
class MoviesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── !movie ────────────────────────────────────────────────────────────────
    @commands.command(name="movie")
    async def movie(self, ctx: commands.Context, *, title: str = None):
        # If title provided directly (!movie Inception) skip the prompt
        if title:
            add_movie(ctx.author.id, title)
            embed = discord.Embed(
                title="🎬 Added to your Watchlist!",
                description=f"**{title}** has been saved to your movie list.\nUse `!movielog` to see your full watchlist.",
                color=0xe50914
            )
            embed.set_footer(text="Lights, camera, action! 🍿")
            await ctx.send(embed=embed)
            return

        # No title — send a fancy prompt and wait for reply
        embed = discord.Embed(
            title="🎬 Lights, Camera, Action!",
            description=(
                f"Hey **{ctx.author.display_name}**! 🍿\n\n"
                "What movie would you like to add to your watchlist?\n"
                "Just type the title and I'll save it for you!"
            ),
            color=0xe50914
        )
        embed.set_footer(text="You have 30 seconds to respond...")
        prompt = await ctx.send(embed=embed)

        def check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

        try:
            reply = await self.bot.wait_for("message", check=check, timeout=30)
            title = reply.content.strip()

            # Clean up messages
            try:
                await prompt.delete()
                await reply.delete()
            except:
                pass

            add_movie(ctx.author.id, title)

            confirm = discord.Embed(
                title="🎬 Added to your Watchlist!",
                description=(
                    f"**{title}** has been saved! 🎞️\n"
                    "Use `!movielog` to see your full watchlist."
                ),
                color=0xe50914
            )
            confirm.set_footer(text="Grab the popcorn! 🍿")
            await ctx.send(embed=confirm)

        except asyncio.TimeoutError:
            try:
                await prompt.delete()
            except:
                pass
            await ctx.send("⏱️ No movie title received. Type `!movie` again when you're ready!", delete_after=8)

    # ── !movielog ─────────────────────────────────────────────────────────────
    @commands.command(name="movielog")
    async def movielog(self, ctx: commands.Context):
        movies = get_user_movies(ctx.author.id)

        if not movies:
            embed = discord.Embed(
                title="🎬 Your Watchlist",
                description=(
                    "Your watchlist is empty! 📭\n\n"
                    "Use `!movie <title>` to add your first movie!"
                ),
                color=0xe50914
            )
            await ctx.send(embed=embed)
            return

        unwatched = [m for m in movies if not m.get("watched")]
        watched   = [m for m in movies if m.get("watched")]

        embed = discord.Embed(
            title=f"🎬 {ctx.author.display_name}'s Watchlist",
            color=0xe50914
        )

        if unwatched:
            lines = []
            for i, m in enumerate(movies):
                if not m.get("watched"):
                    lines.append(f"`{i+1}.` 🎞️ **{m['title']}** — *added {m['added']}*")
            embed.add_field(
                name=f"📋 To Watch ({len(unwatched)})",
                value="\n".join(lines) if lines else "*None*",
                inline=False
            )

        if watched:
            lines = []
            for i, m in enumerate(movies):
                if m.get("watched"):
                    lines.append(f"`{i+1}.` ✅ ~~{m['title']}~~")
            embed.add_field(
                name=f"✅ Watched ({len(watched)})",
                value="\n".join(lines) if lines else "*None*",
                inline=False
            )

        embed.set_footer(text=f"{len(movies)} total · !moviedone <#> to mark watched · !movieremove <#> to remove")
        await ctx.send(embed=embed)

    # ── !moviedone ────────────────────────────────────────────────────────────
    @commands.command(name="moviedone")
    async def moviedone(self, ctx: commands.Context, number: int):
        movies = get_user_movies(ctx.author.id)
        idx    = number - 1

        if idx < 0 or idx >= len(movies):
            await ctx.send(f"❌ No movie at number **{number}**. Check `!movielog` for your list!")
            return

        if movies[idx].get("watched"):
            await ctx.send(f"✅ **{movies[idx]['title']}** is already marked as watched!")
            return

        mark_watched(ctx.author.id, idx)
        embed = discord.Embed(
            title="✅ Marked as Watched!",
            description=f"Nice! **{movies[idx]['title']}** has been checked off your list! 🎉",
            color=0x22c55e
        )
        embed.set_footer(text="What's next on the list? 🍿")
        await ctx.send(embed=embed)

    # ── !movieremove ──────────────────────────────────────────────────────────
    @commands.command(name="movieremove")
    async def movieremove(self, ctx: commands.Context, number: int):
        removed = remove_movie(ctx.author.id, number - 1)
        if removed:
            embed = discord.Embed(
                title="🗑️ Removed from Watchlist",
                description=f"**{removed}** has been removed from your list.",
                color=0x6b7280
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ No movie at number **{number}**. Check `!movielog` for your list!")

    # ── !moviehelp ────────────────────────────────────────────────────────────
    @commands.command(name="moviehelp")
    async def moviehelp(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🎬 Movie Watchlist — Help",
            description="Never forget a movie you want to watch again!",
            color=0xe50914
        )
        embed.add_field(name="Commands", value=(
            "`!movie` — Add a movie (bot will ask for the title)\n"
            "`!movie <title>` — Add a movie directly\n"
            "`!movielog` — View your full watchlist\n"
            "`!moviedone <#>` — Mark a movie as watched\n"
            "`!movieremove <#>` — Remove a movie from the list\n"
            "`!moviehelp` — This help message"
        ), inline=False)
        embed.set_footer(text="Lights, camera, action! 🍿")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(MoviesCog(bot))
