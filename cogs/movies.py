import discord
from discord.ext import commands
from pathlib import Path
import json
import asyncio
from datetime import datetime

# ── Data file ─────────────────────────────────────────────────────────────────
MOVIES_FILE = Path("playerdata/movies.json")

def _load() -> list:
    if not MOVIES_FILE.exists():
        MOVIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        return []
    with open(MOVIES_FILE) as f:
        data = json.load(f)
        if isinstance(data, dict):
            return []
        return data

def _save(movies: list):
    with open(MOVIES_FILE, "w") as f:
        json.dump(movies, f, indent=2)

def get_movies() -> list:
    return _load()

def add_movie(title: str, added_by: str, poster_url: str = None, notes: str = None) -> dict:
    movies = _load()
    entry = {
        "id":       len(movies) + 1,
        "title":    title,
        "added_by": added_by,
        "added":    datetime.now().strftime("%B %d, %Y"),
        "watched":  False,
        "poster":   poster_url,
        "notes":    notes or ""
    }
    movies.append(entry)
    _save(movies)
    return entry

def set_poster(index: int, url: str) -> bool:
    movies = _load()
    if 0 <= index < len(movies):
        movies[index]["poster"] = url
        _save(movies)
        return True
    return False

def set_notes(index: int, notes: str) -> bool:
    movies = _load()
    if 0 <= index < len(movies):
        movies[index]["notes"] = notes
        _save(movies)
        return True
    return False

def mark_watched(index: int) -> bool:
    movies = _load()
    if 0 <= index < len(movies):
        movies[index]["watched"] = True
        _save(movies)
        return True
    return False

def unmark_watched(index: int) -> bool:
    movies = _load()
    if 0 <= index < len(movies):
        movies[index]["watched"] = False
        _save(movies)
        return True
    return False

def remove_movie(index: int) -> str | None:
    movies = _load()
    if 0 <= index < len(movies):
        removed = movies.pop(index)
        for i, m in enumerate(movies):
            m["id"] = i + 1
        _save(movies)
        return removed["title"]
    return None

# ── Movie detail view — buttons for one movie ─────────────────────────────────
class MovieDetailView(discord.ui.View):
    def __init__(self, ctx, movie_idx: int, bot):
        super().__init__(timeout=120)
        self.ctx       = ctx
        self.idx       = movie_idx
        self.bot       = bot

    def _get_movie(self):
        movies = get_movies()
        if 0 <= self.idx < len(movies):
            return movies[self.idx]
        return None

    def _build_embed(self) -> discord.Embed:
        m = self._get_movie()
        if not m:
            return discord.Embed(title="Movie not found", color=0xe50914)
        status = "✅ Watched" if m.get("watched") else "🎞️ Unwatched"
        embed  = discord.Embed(
            title=f"🎬 #{m['id']} — {m['title']}",
            color=0xe50914
        )
        embed.add_field(name="Status",   value=status,        inline=True)
        embed.add_field(name="Added by", value=m["added_by"], inline=True)
        embed.add_field(name="Added on", value=m["added"],    inline=True)
        if m.get("notes"):
            embed.add_field(name="📝 Notes", value=m["notes"], inline=False)
        if m.get("poster"):
            embed.set_image(url=m["poster"])
        else:
            embed.add_field(name="🖼️ Poster", value="No poster yet — click **Add Poster** below!", inline=False)
        return embed

    @discord.ui.button(label="🖼️ Add/Change Poster", style=discord.ButtonStyle.primary, row=0)
    async def add_poster(self, interaction: discord.Interaction, button: discord.ui.Button):
        m = self._get_movie()
        await interaction.response.send_message(
            f"📎 Send an **image URL** or **attach an image** for **{m['title']}**! (30 seconds)",
            ephemeral=True
        )
        def check(msg):
            return msg.author.id == interaction.user.id and msg.channel.id == interaction.channel.id
        try:
            reply = await self.bot.wait_for("message", check=check, timeout=30)
            url = None
            if reply.attachments:
                url = reply.attachments[0].url
            elif reply.content.startswith("http"):
                url = reply.content.strip()
            if url:
                set_poster(self.idx, url)
                try:
                    await reply.delete()
                except:
                    pass
                await interaction.edit_original_response(content="✅ Poster updated!")
                # Refresh the main embed
                await interaction.message.edit(embed=self._build_embed(), view=self)
            else:
                await interaction.edit_original_response(content="❌ That doesn't look like a valid image URL.")
        except asyncio.TimeoutError:
            await interaction.edit_original_response(content="⏱️ Timed out!")

    @discord.ui.button(label="📝 Add/Edit Notes", style=discord.ButtonStyle.secondary, row=0)
    async def add_notes(self, interaction: discord.Interaction, button: discord.ui.Button):
        m = self._get_movie()
        await interaction.response.send_message(
            f"📝 Type your notes for **{m['title']}**! (60 seconds)",
            ephemeral=True
        )
        def check(msg):
            return msg.author.id == interaction.user.id and msg.channel.id == interaction.channel.id
        try:
            reply = await self.bot.wait_for("message", check=check, timeout=60)
            notes = reply.content.strip()
            set_notes(self.idx, notes)
            try:
                await reply.delete()
            except:
                pass
            await interaction.edit_original_response(content="✅ Notes saved!")
            await interaction.message.edit(embed=self._build_embed(), view=self)
        except asyncio.TimeoutError:
            await interaction.edit_original_response(content="⏱️ Timed out!")

    @discord.ui.button(label="✅ Mark Watched", style=discord.ButtonStyle.success, row=0)
    async def toggle_watched(self, interaction: discord.Interaction, button: discord.ui.Button):
        m = self._get_movie()
        if m.get("watched"):
            unmark_watched(self.idx)
            await interaction.response.send_message(f"↩️ **{m['title']}** marked as unwatched!", ephemeral=True)
            button.label = "✅ Mark Watched"
        else:
            mark_watched(self.idx)
            await interaction.response.send_message(f"✅ **{m['title']}** marked as watched!", ephemeral=True)
            button.label = "↩️ Mark Unwatched"
        await interaction.message.edit(embed=self._build_embed(), view=self)

    @discord.ui.button(label="🗑️ Remove", style=discord.ButtonStyle.danger, row=0)
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        m = self._get_movie()

        class ConfirmView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=15)
                self.confirmed = None

            @discord.ui.button(label="Yes, remove it", style=discord.ButtonStyle.danger)
            async def confirm(self, inter, btn):
                self.confirmed = True
                self.stop()
                await inter.response.defer()

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, inter, btn):
                self.confirmed = False
                self.stop()
                await inter.response.defer()

        confirm_view = ConfirmView()
        await interaction.response.send_message(
            f"⚠️ Remove **{m['title']}** from the watchlist?",
            view=confirm_view,
            ephemeral=True
        )
        await confirm_view.wait()
        if confirm_view.confirmed:
            remove_movie(self.idx)
            await interaction.edit_original_response(content=f"🗑️ **{m['title']}** removed!", view=None)
            await interaction.message.edit(
                embed=discord.Embed(title="🗑️ Movie Removed", description=f"**{m['title']}** has been removed from the watchlist.", color=0x6b7280),
                view=None
            )
            self.stop()
        else:
            await interaction.edit_original_response(content="Cancelled.", view=None)

    @discord.ui.button(label="↩️ Back to List", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.stop()
        movies = get_movies()
        await send_movie_list(interaction.message, movies, 0, self.bot, interaction.user)


# ── Movie list view — paginated with select buttons ───────────────────────────
class MovieListView(discord.ui.View):
    def __init__(self, movies: list, page: int, bot, user):
        super().__init__(timeout=120)
        self.movies = movies
        self.page   = page
        self.bot    = bot
        self.user   = user
        self.PER_PAGE = 8
        self._build()

    def _build(self):
        self.clear_items()
        start  = self.page * self.PER_PAGE
        end    = min(start + self.PER_PAGE, len(self.movies))
        page_movies = self.movies[start:end]

        # One button per movie on this page
        for i, m in enumerate(page_movies):
            idx   = start + i
            icon  = "✅" if m.get("watched") else "🎞️"
            poster = "🖼️" if m.get("poster") else ""
            label = f"{icon} #{m['id']} {m['title'][:30]}{poster}"
            btn = discord.ui.Button(
                label=label[:80],
                style=discord.ButtonStyle.primary if not m.get("watched") else discord.ButtonStyle.secondary,
                row=i // 4
            )
            btn.callback = self._make_cb(idx)
            self.add_item(btn)

        # Pagination row
        if self.page > 0:
            prev = discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=2)
            prev.callback = self._prev_cb
            self.add_item(prev)

        if end < len(self.movies):
            nxt = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, row=2)
            nxt.callback = self._next_cb
            self.add_item(nxt)

    def _make_cb(self, idx: int):
        async def cb(interaction: discord.Interaction):
            await interaction.response.defer()
            detail_view = MovieDetailView(None, idx, self.bot)
            embed = detail_view._build_embed()
            await interaction.message.edit(embed=embed, view=detail_view)
        return cb

    async def _prev_cb(self, interaction: discord.Interaction):
        self.page -= 1
        self._build()
        await interaction.response.edit_message(embed=self._build_list_embed(), view=self)

    async def _next_cb(self, interaction: discord.Interaction):
        self.page += 1
        self._build()
        await interaction.response.edit_message(embed=self._build_list_embed(), view=self)

    def _build_list_embed(self) -> discord.Embed:
        start = self.page * self.PER_PAGE
        end   = min(start + self.PER_PAGE, len(self.movies))
        page_movies = self.movies[start:end]
        total_pages = max(1, (len(self.movies) + self.PER_PAGE - 1) // self.PER_PAGE)

        unwatched = len([m for m in self.movies if not m.get("watched")])
        watched   = len([m for m in self.movies if m.get("watched")])

        embed = discord.Embed(title="🎬 Movie Watchlist", color=0xe50914)
        lines = []
        for m in page_movies:
            icon   = "✅" if m.get("watched") else "🎞️"
            poster = " 🖼️" if m.get("poster") else ""
            notes  = " 📝" if m.get("notes") else ""
            title  = f"~~{m['title']}~~" if m.get("watched") else f"**{m['title']}**"
            lines.append(f"`#{m['id']}` {icon} {title}{poster}{notes} — *{m['added_by']}*")
        embed.description = "\n".join(lines)
        embed.add_field(name="📋 To Watch", value=str(unwatched), inline=True)
        embed.add_field(name="✅ Watched",  value=str(watched),   inline=True)
        embed.add_field(name="🎞️ Total",   value=str(len(self.movies)), inline=True)
        embed.set_footer(text=f"Page {self.page+1}/{total_pages} · Click a movie to view/edit · 🖼️=poster 📝=notes")
        return embed


async def send_movie_list(message, movies, page, bot, user):
    view  = MovieListView(movies, page, bot, user)
    embed = view._build_list_embed()
    await message.edit(embed=embed, view=view)


# ── Cog ───────────────────────────────────────────────────────────────────────
class MoviesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="movie")
    async def movie(self, ctx: commands.Context, *, title: str = None):
        user = ctx.author.display_name

        if not title:
            prompt = await ctx.send(embed=discord.Embed(
                title="🎬 Lights, Camera, Action!",
                description=f"Hey **{user}**! 🍿\n\nWhat movie would you like to add to the watchlist?\nJust type the title and I'll save it for everyone!",
                color=0xe50914
            ).set_footer(text="You have 30 seconds to respond..."))

            def check(m):
                return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id
            try:
                reply = await self.bot.wait_for("message", check=check, timeout=30)
                title = reply.content.strip()
                try:
                    await prompt.delete()
                    await reply.delete()
                except:
                    pass
            except asyncio.TimeoutError:
                try:
                    await prompt.delete()
                except:
                    pass
                await ctx.send("⏱️ No response. Type `!movie` again when ready!", delete_after=8)
                return

        entry = add_movie(title, user)
        confirm = discord.Embed(
            title="🎬 Added to the Watchlist!",
            description=f"**{title}** has been added by **{user}**! 🎞️\nUse `!movielog` to view the list and add a poster or notes!",
            color=0xe50914
        )
        confirm.add_field(name="Entry #", value=str(entry["id"]), inline=True)
        confirm.set_footer(text="Click the movie in !movielog to add a poster or notes! 🍿")
        await ctx.send(embed=confirm)

    @commands.command(name="movielog")
    async def movielog(self, ctx: commands.Context):
        movies = get_movies()
        if not movies:
            await ctx.send(embed=discord.Embed(
                title="🎬 Movie Watchlist",
                description="The watchlist is empty! 📭\n\nUse `!movie <title>` to add the first one!",
                color=0xe50914
            ))
            return
        view  = MovieListView(movies, 0, self.bot, ctx.author)
        embed = view._build_list_embed()
        await ctx.send(embed=embed, view=view)

    @commands.command(name="moviehelp")
    async def moviehelp(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🎬 Movie Watchlist — Help",
            description="A shared watchlist everyone in the server can contribute to!",
            color=0xe50914
        )
        embed.add_field(name="Commands", value=(
            "`!movie` — Add a movie (bot asks for title)\n"
            "`!movie <title>` — Add a movie directly\n"
            "`!movielog` — View the watchlist with buttons\n"
            "`!moviehelp` — This help message"
        ), inline=False)
        embed.add_field(name="In the watchlist you can:", value=(
            "🎬 Click any movie to open it\n"
            "🖼️ Add or change the poster\n"
            "📝 Add or edit notes\n"
            "✅ Mark as watched / unwatched\n"
            "🗑️ Remove from the list\n"
            "◀ ▶ Navigate pages"
        ), inline=False)
        embed.set_footer(text="Lights, camera, action! 🍿")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(MoviesCog(bot))
