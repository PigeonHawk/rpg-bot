"""
jumpscare.py — a jumpscare cog using Giphy API for horror GIFs.

Pull random GIFs from Giphy's horror/jumpscare collection and post them with
optional user mentions. Safelist certain members to auto-spoiler their jumpscares.

Commands:
    !jumpscare               post a random horror GIF
    !jumpscare @user         post a GIF and ping that user
    !jumpscare username      post a GIF and ping that user by name
    !jumpscare safelist add @user      (admin) always spoiler jumpscares for this user
    !jumpscare safelist remove @user   (admin) stop spoilering for this user
    !jumpscare safelist                show who's on the safelist

Setup:
  Get a free Giphy API key at https://developers.giphy.com/dashboard
  Sign up -> Create an App -> grab your API key
  Set GIPHY_API_KEY env var in Railway (or locally)
  
Persistence (point at Railway volume to survive redeploys):
  JUMPSCARE_STATE_PATH   default: data/jumpscare.json
  JUMPSCARE_DATA_DIR     default: ./data next to this cog
"""

import os
import json
import random
import logging
import re

import requests
import discord
from discord.ext import commands

log = logging.getLogger(__name__)

GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")
GIPHY_SEARCH = "https://api.giphy.com/v1/gifs/search"

DATA_DIR = os.getenv("JUMPSCARE_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
STATE_PATH = os.getenv("JUMPSCARE_STATE_PATH", os.path.join(DATA_DIR, "jumpscare.json"))

# search queries to rotate through for variety (friendly to actual scares)
SEARCH_QUERIES = [
    "horror jumpscare",
    "ghost jumpscare",
    "scary movie",
    "horror movie",
    "creepy",
    "jason",
    "exorcist",
    "the ring",
    "insidious",
    "haunted",
]


class Jumpscare(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = {"guilds": {}}
        self._load()
        if not GIPHY_API_KEY:
            log.warning("Jumpscare: GIPHY_API_KEY not set — cog will not work")

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

    def _safelist(self, guild_id):
        g = self.data["guilds"].setdefault(str(guild_id), {})
        return set(map(int, g.get("safelist", [])))

    def _is_safelisted(self, guild_id, user_id):
        return user_id in self._safelist(guild_id)

    def _add_safelist(self, guild_id, user_id):
        g = self.data["guilds"].setdefault(str(guild_id), {})
        sl = g.setdefault("safelist", [])
        if user_id not in map(int, sl):
            sl.append(str(user_id))
        self._save()

    def _remove_safelist(self, guild_id, user_id):
        g = self.data["guilds"].get(str(guild_id), {})
        sl = g.get("safelist", [])
        g["safelist"] = [x for x in sl if int(x) != user_id]
        self._save()

    def _resolve_member(self, ctx, token):
        """Resolve a mention or name to a member."""
        mo = re.fullmatch(r"<@!?(\d+)>", token)
        if mo:
            return ctx.guild.get_member(int(mo.group(1)))
        return ctx.guild.get_member_named(token)

    async def _fetch_gif(self):
        """Fetch a random horror GIF from Giphy API."""
        if not GIPHY_API_KEY:
            log.warning("Jumpscare: GIPHY_API_KEY not set")
            return None
        try:
            query = random.choice(SEARCH_QUERIES)
            log.info("Jumpscare: fetching with query '%s'", query)
            resp = requests.get(
                GIPHY_SEARCH,
                params={
                    "q": query,
                    "api_key": GIPHY_API_KEY,
                    "limit": 20,
                    "rating": "pg-13",
                },
                timeout=5,
            )
            log.info("Jumpscare: got response status %s", resp.status_code)
            resp.raise_for_status()
            data = resp.json()
            log.info("Jumpscare: response has %d results", len(data.get("data", [])))
            if data.get("data"):
                result = random.choice(data["data"])
                url = result["images"]["original"]["url"]
                log.info("Jumpscare: returning URL")
                return url
            else:
                log.warning("Jumpscare: no data in response")
                return None
        except Exception as e:
            log.error("Jumpscare: Giphy API error: %s", e)
        return None

    @commands.group(name="jumpscare", aliases=["scare", "horror"], invoke_without_command=True)
    async def jumpscare(self, ctx, target=None):
        """Post a random horror GIF. Optionally ping a user: !jumpscare @user or !jumpscare username"""
        if not GIPHY_API_KEY:
            return await ctx.send("⚠️ Giphy API key not configured.")

        async with ctx.typing():
            gif_url = await self._fetch_gif()
        if not gif_url:
            return await ctx.send("😅 Couldn't fetch a GIF right now. Try again?")

        member = None
        if target:
            member = self._resolve_member(ctx, target)

        content = None
        if member:
            content = f"**{member.mention}** got spooked! 👻"
        else:
            content = "Here's a spook for you 👻"

        # check safelist and spoiler if needed
        spoiler = member and self._is_safelisted(ctx.guild.id, member.id)
        url = f"||{gif_url}||" if spoiler else gif_url

        try:
            await ctx.send(content=content, embed=discord.Embed(image={"url": url}))
        except discord.HTTPException as e:
            log.error("Jumpscare: send failed: %s", e)
            await ctx.send(f"Got a GIF but couldn't post it: {gif_url}")

    @jumpscare.group(name="safelist", invoke_without_command=True)
    async def safelist(self, ctx):
        """Show the jumpscare safelist for this server."""
        sl = self._safelist(ctx.guild.id)
        if not sl:
            return await ctx.send("No one's on the safelist yet.")
        members = []
        for uid in sorted(sl):
            m = ctx.guild.get_member(uid)
            members.append(m.mention if m else f"<@{uid}>")
        emb = discord.Embed(title="🛡️ Jumpscare Safelist",
                            description="\n".join(members),
                            color=0x3498db)
        await ctx.send(embed=emb)

    @safelist.command(name="add")
    @commands.has_guild_permissions(manage_guild=True)
    async def safelist_add(self, ctx, member: discord.Member):
        """(Admin) Always spoiler jumpscares for this user."""
        if self._is_safelisted(ctx.guild.id, member.id):
            return await ctx.send(f"{member.mention} is already on the safelist.")
        self._add_safelist(ctx.guild.id, member.id)
        await ctx.send(f"✅ Added {member.mention} to the safelist. Their jumpscares will be spoilered.")

    @safelist.command(name="remove")
    @commands.has_guild_permissions(manage_guild=True)
    async def safelist_remove(self, ctx, member: discord.Member):
        """(Admin) Stop spoilering jumpscares for this user."""
        if not self._is_safelisted(ctx.guild.id, member.id):
            return await ctx.send(f"{member.mention} is not on the safelist.")
        self._remove_safelist(ctx.guild.id, member.id)
        await ctx.send(f"✅ Removed {member.mention} from the safelist.")


async def setup(bot):
    await bot.add_cog(Jumpscare(bot))
