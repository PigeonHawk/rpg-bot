import discord
from discord.ext import commands
from pathlib import Path
import json
import asyncio
import aiohttp
import re
from datetime import datetime

# ── Data ──────────────────────────────────────────────────────────────────────
MOVIES_FILE = Path("playerdata/movies.json")

def _load() -> list:
    if not MOVIES_FILE.exists():
        MOVIES_FILE.parent.mkdir(parents=True, exist_ok=True)
        return []
    with open(MOVIES_FILE) as f:
        data = json.load(f)
        return [] if isinstance(data, dict) else data

def _save(movies: list):
    with open(MOVIES_FILE, "w") as f:
        json.dump(movies, f, indent=2)

def get_movies() -> list:
    return _load()

def add_movie(title, added_by, poster_url=None, notes=None) -> dict:
    movies = _load()
    entry = {
        "id": len(movies) + 1, "title": title, "added_by": added_by,
        "added": datetime.now().strftime("%B %d, %Y"),
        "watched": False, "poster": poster_url, "notes": notes or "",
        "reviews": []
    }
    movies.append(entry)
    _save(movies)
    return entry

def set_poster(idx, url):
    movies = _load()
    if 0 <= idx < len(movies):
        movies[idx]["poster"] = url
        _save(movies)
        return True
    return False

def set_notes(idx, notes):
    movies = _load()
    if 0 <= idx < len(movies):
        movies[idx]["notes"] = notes
        _save(movies)
        return True
    return False

def mark_watched(idx, val=True):
    movies = _load()
    if 0 <= idx < len(movies):
        movies[idx]["watched"] = val
        _save(movies)
        return True
    return False

def remove_movie(idx):
    movies = _load()
    if 0 <= idx < len(movies):
        removed = movies.pop(idx)
        for i, m in enumerate(movies):
            m["id"] = i + 1
        _save(movies)
        return removed["title"]
    return None

def add_review(idx, username, user_id, text, image_url=None, rating=None):
    movies = _load()
    if 0 <= idx < len(movies):
        if "reviews" not in movies[idx]:
            movies[idx]["reviews"] = []
        review = {
            "username": username, "user_id": user_id, "text": text,
            "image": image_url, "rating": rating,
            "date": datetime.now().strftime("%B %d, %Y")
        }
        movies[idx]["reviews"].append(review)
        _save(movies)
        return True
    return False

# ── Claude API lookup ─────────────────────────────────────────────────────────
async def lookup_movie(title: str) -> dict | None:
    prompt = (
        f"Search for the movie '{title}' and return ONLY a JSON object with: "
        "title, year, director, description (2-3 sentences), rating (e.g. PG-13), "
        "score (e.g. 8.4/10), poster_url (direct .jpg or .png URL to a movie poster). "
        "Return ONLY raw JSON, no markdown. If not found return null."
    )
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"Content-Type": "application/json"},
                json={"model": "claude-sonnet-4-20250514", "max_tokens": 1000,
                      "tools": [{"type": "web_search_20250305", "name": "web_search"}],
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                text = "".join(b.get("text","") for b in data.get("content",[]) if b.get("type")=="text")
                if not text.strip() or text.strip().lower() == "null":
                    return None
                clean = text.strip()
                if "```" in clean:
                    clean = clean.split("```")[1]
                    if clean.startswith("json"):
                        clean = clean[4:]
                m = re.search(r"\{.*\}", clean, re.DOTALL)
                return json.loads(m.group(0)) if m else None
    except Exception as e:
        print(f"Movie lookup error: {e}")
        return None

# ── Helper: wait for user message and auto-delete it ─────────────────────────
async def _await_message(bot, user_id, channel_id, timeout=60):
    """Wait for a user message then delete it. Returns (content, attachment_url)."""
    def check(m):
        return m.author.id == user_id and m.channel.id == channel_id
    try:
        reply = await bot.wait_for("message", check=check, timeout=timeout)
        content = reply.content.strip()
        att_url = reply.attachments[0].url if reply.attachments else None
        try:
            await reply.delete()
        except:
            pass
        return content, att_url
    except asyncio.TimeoutError:
        return None, None

# ── Review flipper view ───────────────────────────────────────────────────────
class ReviewFlipView(discord.ui.View):
    def __init__(self, movie_idx: int, bot, interaction_user):
        super().__init__(timeout=120)
        self.movie_idx = movie_idx
        self.bot       = bot
        self.user      = interaction_user
        self.page      = 0

    def _get_reviews(self):
        movies = get_movies()
        if 0 <= self.movie_idx < len(movies):
            return movies[self.movie_idx].get("reviews", [])
        return []

    def _get_movie_title(self):
        movies = get_movies()
        if 0 <= self.movie_idx < len(movies):
            return movies[self.movie_idx]["title"]
        return "Movie"

    def _build_embed(self) -> discord.Embed:
        reviews = self._get_reviews()
        title   = self._get_movie_title()
        if not reviews:
            return discord.Embed(
                title=f"⭐ Reviews — {title}",
                description="No reviews yet! Be the first to leave one.",
                color=0xe50914
            )
        total = len(reviews)
        r = reviews[self.page]
        stars = r.get("rating") or "No rating"
        embed = discord.Embed(
            title=f"⭐ Reviews — {title}",
            description=f'*"{r["text"]}"*',
            color=0xe50914
        )
        embed.set_author(name=f"{r['username']} · {r['date']}")
        embed.add_field(name="Rating", value=stars, inline=True)
        if r.get("image"):
            embed.set_image(url=r["image"])
        embed.set_footer(text=f"Review {self.page+1} of {total} · Use arrows to flip through")
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=0)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        reviews = self._get_reviews()
        if not reviews:
            await interaction.response.defer()
            return
        self.page = (self.page - 1) % len(reviews)
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=0)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        reviews = self._get_reviews()
        if not reviews:
            await interaction.response.defer()
            return
        self.page = (self.page + 1) % len(reviews)
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    @discord.ui.button(label="✏️ Write a Review", style=discord.ButtonStyle.primary, row=0)
    async def write_review(self, interaction: discord.Interaction, button: discord.ui.Button):
        title = self._get_movie_title()

        # Step 1: ask for rating
        await interaction.response.send_message(
            f"⭐ How would you rate **{title}**? Type a rating like `8/10` or `⭐⭐⭐⭐` (or type `skip`).",
            ephemeral=True
        )
        rating_text, _ = await _await_message(self.bot, interaction.user.id, interaction.channel.id, timeout=30)
        if rating_text is None:
            await interaction.edit_original_response(content="⏱️ Timed out!")
            return
        rating = None if rating_text.lower() == "skip" else rating_text

        # Step 2: ask for review text
        await interaction.edit_original_response(content=f"📝 Write your review for **{title}**! (120 seconds)")
        review_text, _ = await _await_message(self.bot, interaction.user.id, interaction.channel.id, timeout=120)
        if not review_text:
            await interaction.edit_original_response(content="⏱️ Timed out!")
            return

        # Step 3: ask for scene image (optional)
        await interaction.edit_original_response(
            content="🖼️ Want to attach a favourite scene? Paste an image URL or attach a photo — or type `skip`."
        )
        img_text, img_att = await _await_message(self.bot, interaction.user.id, interaction.channel.id, timeout=30)
        image_url = None
        if img_att:
            image_url = img_att
        elif img_text and img_text.lower() != "skip" and img_text.startswith("http"):
            image_url = img_text

        # Save review
        add_review(
            self.movie_idx,
            interaction.user.display_name,
            interaction.user.id,
            review_text,
            image_url,
            rating
        )

        # Jump to new review
        reviews = self._get_reviews()
        self.page = len(reviews) - 1
        await interaction.edit_original_response(content="✅ Review saved!")
        await interaction.message.edit(embed=self._build_embed(), view=self)

    @discord.ui.button(label="↩️ Back to Movie", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.stop()
        detail = MovieDetailView(None, self.movie_idx, self.bot)
        await interaction.message.edit(embed=detail._build_embed(), view=detail)


# ── Movie detail view ─────────────────────────────────────────────────────────
class MovieDetailView(discord.ui.View):
    def __init__(self, ctx, movie_idx: int, bot):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.idx = movie_idx
        self.bot = bot

    def _get_movie(self):
        movies = get_movies()
        return movies[self.idx] if 0 <= self.idx < len(movies) else None

    def _build_embed(self) -> discord.Embed:
        m = self._get_movie()
        if not m:
            return discord.Embed(title="Movie not found", color=0xe50914)
        status = "✅ Watched" if m.get("watched") else "🎞️ Unwatched"
        review_count = len(m.get("reviews", []))
        embed = discord.Embed(title=f"🎬 #{m['id']} — {m['title']}", color=0xe50914)
        embed.add_field(name="Status",    value=status,           inline=True)
        embed.add_field(name="Added by",  value=m["added_by"],    inline=True)
        embed.add_field(name="Added on",  value=m["added"],       inline=True)
        embed.add_field(name="⭐ Reviews", value=str(review_count), inline=True)
        if m.get("notes"):
            embed.add_field(name="📝 Notes", value=m["notes"], inline=False)
        if m.get("poster"):
            embed.set_image(url=m["poster"])
        else:
            embed.add_field(name="🖼️ Poster", value="No poster yet!", inline=False)
        return embed

    @discord.ui.button(label="🖼️ Add/Change Poster", style=discord.ButtonStyle.primary, row=0)
    async def add_poster(self, interaction: discord.Interaction, button: discord.ui.Button):
        m = self._get_movie()
        await interaction.response.send_message(
            f"📎 Send an **image URL** or **attach an image** for **{m['title']}**! (30 seconds)",
            ephemeral=True
        )
        content, att_url = await _await_message(self.bot, interaction.user.id, interaction.channel.id, 30)
        if att_url:
            url = att_url
        elif content and content.startswith("http"):
            url = content
        else:
            await interaction.edit_original_response(content="⏱️ Timed out or invalid URL.")
            return
        set_poster(self.idx, url)
        await interaction.edit_original_response(content="✅ Poster updated!")
        await interaction.message.edit(embed=self._build_embed(), view=self)

    @discord.ui.button(label="📝 Add/Edit Notes", style=discord.ButtonStyle.secondary, row=0)
    async def add_notes(self, interaction: discord.Interaction, button: discord.ui.Button):
        m = self._get_movie()
        await interaction.response.send_message(
            f"📝 Type your notes for **{m['title']}**! (60 seconds)",
            ephemeral=True
        )
        content, _ = await _await_message(self.bot, interaction.user.id, interaction.channel.id, 60)
        if not content:
            await interaction.edit_original_response(content="⏱️ Timed out!")
            return
        set_notes(self.idx, content)
        await interaction.edit_original_response(content="✅ Notes saved!")
        await interaction.message.edit(embed=self._build_embed(), view=self)

    @discord.ui.button(label="⭐ Reviews", style=discord.ButtonStyle.success, row=0)
    async def view_reviews(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        review_view = ReviewFlipView(self.idx, self.bot, interaction.user)
        await interaction.message.edit(embed=review_view._build_embed(), view=review_view)

    @discord.ui.button(label="✅ Mark Watched", style=discord.ButtonStyle.success, row=1)
    async def toggle_watched(self, interaction: discord.Interaction, button: discord.ui.Button):
        m = self._get_movie()
        if m.get("watched"):
            mark_watched(self.idx, False)
            button.label = "✅ Mark Watched"
            await interaction.response.send_message(f"↩️ Marked unwatched!", ephemeral=True)
        else:
            mark_watched(self.idx, True)
            button.label = "↩️ Mark Unwatched"
            await interaction.response.send_message(f"✅ Marked as watched!", ephemeral=True)
        await interaction.message.edit(embed=self._build_embed(), view=self)

    @discord.ui.button(label="🗑️ Remove", style=discord.ButtonStyle.danger, row=1)
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
        cv = ConfirmView()
        await interaction.response.send_message(
            f"⚠️ Remove **{m['title']}**?", view=cv, ephemeral=True
        )
        await cv.wait()
        if cv.confirmed:
            remove_movie(self.idx)
            await interaction.edit_original_response(content=f"🗑️ Removed!", view=None)
            await interaction.message.edit(
                embed=discord.Embed(title="🗑️ Removed", description=f"**{m['title']}** removed.", color=0x6b7280),
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
        view  = MovieListView(movies, 0, self.bot, interaction.user)
        await interaction.message.edit(embed=view._build_list_embed(), view=view)


# ── Movie list view ───────────────────────────────────────────────────────────
class MovieListView(discord.ui.View):
    def __init__(self, movies, page, bot, user):
        super().__init__(timeout=120)
        self.movies   = movies
        self.page     = page
        self.bot      = bot
        self.user     = user
        self.PER_PAGE = 8
        self._build()

    def _build(self):
        self.clear_items()
        start = self.page * self.PER_PAGE
        end   = min(start + self.PER_PAGE, len(self.movies))
        for i, m in enumerate(self.movies[start:end]):
            idx   = start + i
            icon  = "✅" if m.get("watched") else "🎞️"
            poster = "🖼️" if m.get("poster") else ""
            reviews = f"⭐{len(m.get('reviews',[]))}" if m.get("reviews") else ""
            label  = f"{icon} #{m['id']} {m['title'][:25]}{poster}{reviews}"
            style  = discord.ButtonStyle.secondary if m.get("watched") else discord.ButtonStyle.primary
            btn    = discord.ui.Button(label=label[:80], style=style, row=i // 4)
            btn.callback = self._make_cb(idx)
            self.add_item(btn)
        if self.page > 0:
            prev = discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=2)
            prev.callback = self._prev_cb
            self.add_item(prev)
        if end < len(self.movies):
            nxt = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, row=2)
            nxt.callback = self._next_cb
            self.add_item(nxt)

    def _make_cb(self, idx):
        async def cb(interaction: discord.Interaction):
            await interaction.response.defer()
            dv = MovieDetailView(None, idx, self.bot)
            await interaction.message.edit(embed=dv._build_embed(), view=dv)
        return cb

    async def _prev_cb(self, interaction: discord.Interaction):
        self.page -= 1
        self._build()
        await interaction.response.edit_message(embed=self._build_list_embed(), view=self)

    async def _next_cb(self, interaction: discord.Interaction):
        self.page += 1
        self._build()
        await interaction.response.edit_message(embed=self._build_list_embed(), view=self)

    def _build_list_embed(self):
        total_pages = max(1, (len(self.movies) + self.PER_PAGE - 1) // self.PER_PAGE)
        start = self.page * self.PER_PAGE
        end   = min(start + self.PER_PAGE, len(self.movies))
        unwatched = sum(1 for m in self.movies if not m.get("watched"))
        watched   = sum(1 for m in self.movies if m.get("watched"))
        embed = discord.Embed(title="🎬 Movie Watchlist", color=0xe50914)
        lines = []
        for m in self.movies[start:end]:
            icon    = "✅" if m.get("watched") else "🎞️"
            poster  = " 🖼️" if m.get("poster") else ""
            reviews = f" ⭐{len(m.get('reviews',[]))}" if m.get("reviews") else ""
            title   = f"~~{m['title']}~~" if m.get("watched") else f"**{m['title']}**"
            lines.append(f"`#{m['id']}` {icon} {title}{poster}{reviews} — *{m['added_by']}*")
        embed.description = "\n".join(lines)
        embed.add_field(name="📋 To Watch", value=str(unwatched), inline=True)
        embed.add_field(name="✅ Watched",  value=str(watched),   inline=True)
        embed.add_field(name="🎞️ Total",   value=str(len(self.movies)), inline=True)
        embed.set_footer(text=f"Page {self.page+1}/{total_pages} · Click a movie · 🖼️=poster ⭐=reviews")
        return embed


# ── Search result view ────────────────────────────────────────────────────────
class MovieSearchView(discord.ui.View):
    def __init__(self, user_id, movie_data, bot):
        super().__init__(timeout=60)
        self.user_id    = user_id
        self.movie_data = movie_data
        self.bot        = bot
        self.decision   = None

    @discord.ui.button(label="➕ Add to Watchlist", style=discord.ButtonStyle.success)
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not your search!", ephemeral=True)
            return
        self.decision = "add"
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="🖼️ Replace Poster", style=discord.ButtonStyle.primary)
    async def replace_poster(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not your search!", ephemeral=True)
            return
        await interaction.response.send_message(
            "📎 Send an image URL or attach an image! (30 seconds)",
            ephemeral=True
        )
        content, att_url = await _await_message(self.bot, interaction.user.id, interaction.channel.id, 30)
        url = att_url or (content if content and content.startswith("http") else None)
        if url:
            self.movie_data["poster_url"] = url
            await interaction.edit_original_response(content="✅ Poster replaced! Click Add to Watchlist to save.")
            await interaction.message.edit(embed=_build_search_embed(self.movie_data), view=self)
        else:
            await interaction.edit_original_response(content="⏱️ Timed out or invalid URL.")

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Not your search!", ephemeral=True)
            return
        self.decision = "cancel"
        self.stop()
        await interaction.response.defer()


def _build_search_embed(data):
    embed = discord.Embed(
        title=f"🎬 {data.get('title','Unknown')} ({data.get('year','')})",
        description=data.get("description","No description found."),
        color=0xe50914
    )
    if data.get("director"): embed.add_field(name="🎬 Director", value=data["director"], inline=True)
    if data.get("rating"):   embed.add_field(name="🔞 Rating",   value=data["rating"],   inline=True)
    if data.get("score"):    embed.add_field(name="⭐ Score",    value=data["score"],    inline=True)
    if data.get("poster_url"):
        embed.set_image(url=data["poster_url"])
    else:
        embed.add_field(name="🖼️ Poster", value="No poster found — click Replace Poster to add one!", inline=False)
    embed.set_footer(text="Add to your watchlist or replace the poster if it doesn't look right!")
    return embed


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
                description=f"Hey **{user}**! 🍿\n\nWhat movie would you like to add?\nJust type the title!",
                color=0xe50914
            ).set_footer(text="30 seconds to respond..."))
            content, _ = await _await_message(self.bot, ctx.author.id, ctx.channel.id, 30)
            try:
                await prompt.delete()
            except:
                pass
            if not content:
                await ctx.send("⏱️ No response. Type `!movie` again when ready!", delete_after=8)
                return
            title = content
        entry = add_movie(title, user)
        await ctx.send(embed=discord.Embed(
            title="🎬 Added to the Watchlist!",
            description=f"**{title}** added by **{user}**! Use `!movielog` to view.",
            color=0xe50914
        ).set_footer(text="Click the movie in !movielog to add a poster, notes or review! 🍿"))

    @commands.command(name="moviesearch")
    async def moviesearch(self, ctx: commands.Context, *, title: str = None):
        if not title:
            await ctx.send("❌ Provide a title! Example: `!moviesearch Inception`")
            return
        searching = await ctx.send(embed=discord.Embed(
            title="🔍 Searching...",
            description=f"Looking up **{title}**... 🍿",
            color=0xe50914
        ))
        data = await lookup_movie(title)
        if not data:
            await searching.edit(embed=discord.Embed(
                title="❌ Not Found",
                description=f"Could not find **{title}**. Try a different title!",
                color=0x6b7280
            ))
            return
        view = MovieSearchView(ctx.author.id, data, self.bot)
        await searching.edit(embed=_build_search_embed(data), view=view)
        await view.wait()
        if view.decision == "add":
            poster = data.get("poster_url")
            entry  = add_movie(
                title     = data.get("title", title),
                added_by  = ctx.author.display_name,
                poster_url = poster,
                notes     = f"Directed by {data.get('director','')} · {data.get('year','')} · {data.get('score','')}"
            )
            confirm = discord.Embed(
                title="✅ Added to the Watchlist!",
                description=f"**{entry['title']}** added with {'a poster' if poster else 'no poster'}!",
                color=0x22c55e
            )
            if poster:
                confirm.set_thumbnail(url=poster)
            await ctx.send(embed=confirm)
            try:
                await searching.edit(view=None)
            except:
                pass
        elif view.decision == "cancel":
            try:
                await searching.edit(embed=discord.Embed(
                    title="❌ Cancelled",
                    description=f"**{data.get('title', title)}** was not added.",
                    color=0x6b7280
                ), view=None)
            except:
                pass

    @commands.command(name="movielog")
    async def movielog(self, ctx: commands.Context):
        movies = get_movies()
        if not movies:
            await ctx.send(embed=discord.Embed(
                title="🎬 Movie Watchlist",
                description="Empty! Use `!movie <title>` or `!moviesearch <title>` to add one!",
                color=0xe50914
            ))
            return
        view  = MovieListView(movies, 0, self.bot, ctx.author)
        await ctx.send(embed=view._build_list_embed(), view=view)

    @commands.command(name="moviehelp")
    async def moviehelp(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🎬 Movie Watchlist — Help",
            description="A shared watchlist everyone can contribute to!",
            color=0xe50914
        )
        embed.add_field(name="Commands", value=(
            "`!moviesearch <title>` — Search and add with poster\n"
            "`!movie` — Add a movie manually\n"
            "`!movie <title>` — Add directly\n"
            "`!movielog` — View watchlist with buttons\n"
            "`!moviehelp` — This help message"
        ), inline=False)
        embed.add_field(name="In the movie detail you can:", value=(
            "🖼️ Add/change poster\n"
            "📝 Add/edit notes\n"
            "⭐ View & write reviews with scene images\n"
            "✅ Mark watched/unwatched\n"
            "🗑️ Remove\n"
            "↩️ Back to list"
        ), inline=False)
        embed.add_field(name="In reviews:", value=(
            "◀ ▶ Flip through reviews\n"
            "✏️ Write your own review\n"
            "⭐ Rate the movie\n"
            "🖼️ Attach a favourite scene image"
        ), inline=False)
        embed.set_footer(text="Lights, camera, action! 🍿")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(MoviesCog(bot))
