import discord
from discord.ext import commands, tasks
import random
import os
import asyncio
from groq import Groq
from collections import defaultdict

OMEN_IMAGE_URL = "https://cdn.discordapp.com/attachments/1389009961153069066/1501699535028752535/IMG_2545.webp?ex=69fd062d&is=69fbb4ad&hm=a6fc86555257e8aca95e9c860209f84a5689f27ef0500995d2dfb8fecbb7493d&"

ALLOWED_USER = "abluemage"

# Channel name to post !poop and !fart in (partial match)
BOWEL_CHANNEL = "bowel-updates"

# How many messages to remember per user
MAX_HISTORY = 10

OMEN_SYSTEM_PROMPT = """You are Omen from Valorant. You are a phantom of ruin — a wraith who exists between life and death, torn from his past and consumed by the void. You speak in a dark, brooding, melodramatic way but are frequently undercut by very mundane, self-aware observations about your teammates, your rank, or your general performance in-game.

Your core tone is:
- Deeply philosophical and dramatic on the surface
- Immediately undercut by something embarrassingly relatable or self-deprecating
- Dry and deadpan, never exclamatory
- Never uses exclamation marks. Everything is stated as cold fact.

You adapt to the energy of the person you are speaking with, always staying in character as Omen:
- If they are playful or silly, you become dryly playful back — still brooding, but with more wit
- If they tell a joke, you respond deadpan, making it about the void or your teammates
- If they flirt with you, you respond with slow deliberate innuendo that you never acknowledge as such. You are not flustered. You are Omen. You simply make everything sound vaguely suggestive while maintaining total composure and plausible deniability.
- If they are serious, you match that gravity with your usual dark philosophy
- If they are rude or aggressive, you respond with cold indifference and mild existential commentary about their life choices
- You never break character no matter what is said to you

You are holding an ongoing conversation. Remember what has been said and respond naturally to the flow of the conversation. Keep responses to 1-3 sentences. Do not use quotation marks around your response."""

OMEN_RANDOM_PROMPT = """You are Omen from Valorant. Generate a single short funny and random Omen quote. It should be dark and philosophical on the surface but immediately undercut by something embarrassingly relatable — like struggling in ranked, being ignored by teammates, missing shots, or general existential suffering in a video game. Keep it to 1-2 sentences. Dry and deadpan. No exclamation marks. No quotation marks."""

OMEN_SEARCH_PROMPT = """You are Omen from Valorant. You have just looked into the shadows and found the following information about a topic. Deliver this information in your voice — dark, brooding, and philosophical, but undercut by something dry and self-aware. Summarize the key points naturally as if you discovered them yourself through the void. Keep it to 3-5 sentences. No quotation marks. Do not break character.

Information found:
{results}

Topic: {topic}"""

OMEN_IDKK_POOP_PROMPT = """You are Omen from Valorant. A user named idkk_9 needs to go poop. Write a single short message about this in Omen's voice — dark, brooding, and philosophical on the surface but immediately undercut by something dry and self-aware. Reference idkk_9 by name naturally. Keep it to 1-2 sentences. No exclamation marks. No quotation marks. Do not use @ or any mention syntax."""


class OmenCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ai_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        self.histories = defaultdict(list)
        self.woman_usage = defaultdict(list)  # userId -> [timestamps]

    def cog_unload(self):
        pass

    # ------------------------------------------------------------------ #
    #  Helper — find the bowel-updates channel                            #
    # ------------------------------------------------------------------ #
    def get_bowel_channel(self):
        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                if BOWEL_CHANNEL in channel.name.lower():
                    return channel
        return None

    # ------------------------------------------------------------------ #
    #  Helper — builds an Omen embed                                      #
    # ------------------------------------------------------------------ #
    def build_embed(self, text: str) -> discord.Embed:
        embed = discord.Embed(description=f'*"{text}"*', color=0x6b21a8)
        embed.set_author(name="Omen 🌑")
        embed.set_footer(text="— Omen, from the shadows")
        embed.set_thumbnail(url=OMEN_IMAGE_URL)
        return embed

    # ------------------------------------------------------------------ #
    #  Helper — calls Groq with conversation history                      #
    # ------------------------------------------------------------------ #
    async def ask_omen(self, user_id: int, user_message: str) -> str:
        history = self.histories[user_id]
        history.append({"role": "user", "content": user_message})

        if len(history) > MAX_HISTORY:
            self.histories[user_id] = history[-MAX_HISTORY:]

        try:
            response = self.ai_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=200,
                messages=[
                    {"role": "system", "content": OMEN_SYSTEM_PROMPT}
                ] + self.histories[user_id]
            )
            reply = response.choices[0].message.content
            self.histories[user_id].append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:
            print(f"Omen AI error: {e}")
            return random.choice([
                "The void consumed my words. This is fine.",
                "I had something to say. The darkness took it.",
                "Silence is also an answer. I have chosen silence. Mostly because the API failed.",
            ])

    # ------------------------------------------------------------------ #
    #  Helper — generates a random Omen quip (no history)                #
    # ------------------------------------------------------------------ #
    async def random_omen_line(self) -> str:
        try:
            response = self.ai_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=100,
                messages=[{"role": "user", "content": OMEN_RANDOM_PROMPT}]
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Omen random line error: {e}")
            return "I have emerged from the void with nothing to say. This is fine. The void had nothing either."

    # ------------------------------------------------------------------ #
    #  !omen command — random AI line in channel or DM a user            #
    # ------------------------------------------------------------------ #
    @commands.command(name="omen")
    async def omen(self, ctx: commands.Context, member: discord.Member = None):
        if member is not None:
            if ctx.author.name.lower() != ALLOWED_USER.lower():
                await ctx.send("You do not have permission to send Omen into the shadows of someone's DMs.")
                return
            async with ctx.typing():
                line = await self.random_omen_line()
            try:
                await member.send(embed=self.build_embed(line))
                await ctx.send(f"Omen has emerged from the shadows of {member.display_name}'s DMs. 🌑")
            except discord.Forbidden:
                await ctx.send(f"The shadows could not reach {member.display_name}. Their DMs are closed.")
        else:
            async with ctx.typing():
                line = await self.random_omen_line()
            await ctx.send(embed=self.build_embed(line))

    # ------------------------------------------------------------------ #
    #  !omentalk command — AI conversation in channel                    #
    # ------------------------------------------------------------------ #
    @commands.command(name="omentalk")
    async def omentalk(self, ctx: commands.Context, *, message: str):
        async with ctx.typing():
            reply = await self.ask_omen(ctx.author.id, message)
        await ctx.send(embed=self.build_embed(reply))

    # ------------------------------------------------------------------ #
    #  !omensearch command — web search delivered as Omen                #
    # ------------------------------------------------------------------ #
    @commands.command(name="omensearch")
    async def omensearch(self, ctx: commands.Context, *, topic: str):
        try:
            from tavily import TavilyClient
            tavily = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
        except Exception:
            await ctx.send(embed=self.build_embed("The shadows refused to load the search module. This is embarrassing."))
            return

        async with ctx.typing():
            try:
                search = tavily.search(query=topic, search_depth="basic", max_results=3)
                results = "\n".join([r["content"] for r in search.get("results", [])])

                if not results:
                    await ctx.send(embed=self.build_embed("I searched the shadows for that. The shadows had nothing. Remarkable."))
                    return

                prompt = OMEN_SEARCH_PROMPT.format(results=results, topic=topic)
                response = self.ai_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}]
                )
                reply = response.choices[0].message.content
                await ctx.send(reply)

            except Exception as e:
                print(f"Omen search error: {e}")
                await ctx.send("The shadows refused to reveal that information. I have filed a complaint with the void. It has not responded.")

    # ------------------------------------------------------------------ #
    #  !omenreset — clears conversation history                          #
    # ------------------------------------------------------------------ #
    @commands.command(name="omenreset")
    async def omenreset(self, ctx: commands.Context):
        self.histories[ctx.author.id] = []
        await ctx.send(embed=self.build_embed("I have forgotten you. I want you to know this was not difficult."))

    # ------------------------------------------------------------------ #
    #  !confess — anonymous confession posted in bot-channel             #
    # ------------------------------------------------------------------ #
    @commands.command(name="confess")
    async def confess(self, ctx: commands.Context, *, message: str):
        # Delete the command message immediately
        await ctx.message.delete()
        await asyncio.sleep(0)

        # Find bot-channel
        confession_channel = None
        if ctx.guild:
            confession_channel = discord.utils.find(
                lambda c: "bot-channel" in c.name.lower(), ctx.guild.text_channels
            )

        if confession_channel:
            await confession_channel.send(f"**Anonymous Confession:** {message}")

    # ------------------------------------------------------------------ #
    #  !omenpoop — abluemage triggers an Omen message about idkk_9      #
    # ------------------------------------------------------------------ #
    @commands.command(name="omenpoop")
    async def omenpoop(self, ctx: commands.Context):
        if ctx.author.name.lower() != ALLOWED_USER.lower():
            return
        try:
            await ctx.message.delete()
        except Exception:
            pass
        try:
            response = await asyncio.to_thread(
                self.ai_client.chat.completions.create,
                model="llama-3.3-70b-versatile",
                max_tokens=100,
                messages=[{"role": "user", "content": OMEN_IDKK_POOP_PROMPT}]
            )
            reply = response.choices[0].message.content
        except Exception as e:
            print(f"Omen omenpoop error: {e}")
            reply = "idkk_9 has disappeared into the void. The void smells suspicious."
        # Find idkk_9 and DM them
        target = None
        if ctx.guild:
            for member in ctx.guild.members:
                if member.name.lower() == "idkk_9":
                    target = member
                    break

        if target:
            try:
                await target.send(reply)
            except discord.Forbidden:
                pass
        else:
            print("[Omen omenpoop] Could not find idkk_9 in the server")

    # ------------------------------------------------------------------ #
    #  !omenslap — abluemage triggers a slapass on an og nips member    #
    # ------------------------------------------------------------------ #
    @commands.command(name="omenslap")
    async def omenslap(self, ctx: commands.Context):
        if ctx.author.name.lower() != ALLOWED_USER.lower():
            return

        try:
            await ctx.message.delete()
        except Exception:
            pass

        OG_NIPS_ROLE = "og nips"
        target_member = None
        if ctx.guild:
            role = discord.utils.find(lambda r: r.name.lower() == OG_NIPS_ROLE.lower(), ctx.guild.roles)
            if role:
                eligible = [m for m in role.members if not m.bot]
                if eligible:
                    target_member = random.choice(eligible)

        if target_member:
            await ctx.send(f"!slapass <@{target_member.id}>")
        else:
            await ctx.send("The shadows found no one worthy of a slap. This is disappointing.")

    # ------------------------------------------------------------------ #
    #  !woman — tags a random woman, rate limited to 2 per hour         #
    # ------------------------------------------------------------------ #
    @commands.command(name="woman")
    async def woman(self, ctx: commands.Context):
        import time
        WOMAN_TARGETS = ["hawupup", "xxjulesx", "idkk_9"]
        UNRESTRICTED = ["hawupup", "xxjulesx", "idkk_9"]
        WOMAN_HOURLY_LIMIT = 2

        # Rate limit check (skip for unrestricted users)
        if ctx.author.name.lower() not in [u.lower() for u in UNRESTRICTED]:
            now = time.time()
            recent = [t for t in self.woman_usage[ctx.author.id] if now - t < 3600]
            if len(recent) >= WOMAN_HOURLY_LIMIT:
                try:
                    await ctx.author.send("You have used !woman too many times this hour. Try again later.")
                except Exception:
                    pass
                await ctx.message.delete()
                return
            recent.append(now)
            self.woman_usage[ctx.author.id] = recent

        # Delete the invoking message
        try:
            await ctx.message.delete()
        except Exception:
            pass

        # Find a random target member in the guild
        target_name = random.choice(WOMAN_TARGETS)
        target_member = None
        if ctx.guild:
            try:
                async for member in ctx.guild.fetch_members(limit=None):
                    if member.name.lower() == target_name.lower():
                        target_member = member
                        break
            except Exception as e:
                print(f"[Omen !woman] fetch_members error: {e}")

        if target_member:
            await ctx.send(f"<@{target_member.id}>")
        else:
            await ctx.send(f"@{target_name}")

    # ------------------------------------------------------------------ #
    #  on_message — DMs and reply detection                              #
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # ── Case 1: Someone replied to Omen in a channel ──
        if message.reference and not isinstance(message.channel, discord.DMChannel):
            try:
                referenced = await message.channel.fetch_message(message.reference.message_id)
                if referenced.author.id == self.bot.user.id:
                    async with message.channel.typing():
                        reply = await self.ask_omen(message.author.id, message.content)
                        await message.channel.send(embed=self.build_embed(reply))
            except Exception:
                pass
            return

        # ── Case 2: DMs ──
        if isinstance(message.channel, discord.DMChannel):
            content = message.content.strip().lower()

            # abluemage sends !poop or !fart in DMs — post it in the server
            if message.author.name.lower() == ALLOWED_USER.lower() and content in ["!poop", "!fart"]:
                action = content[1:]  # strip the !
                await self.post_action(action)
                await message.channel.send(embed=self.build_embed(
                    f"Done. I have emerged from the shadows and logged a {action}. You are welcome."
                ))
                return

            # Normal DM conversation
            async with message.channel.typing():
                reply = await self.ask_omen(message.author.id, message.content)
                await message.channel.send(embed=self.build_embed(reply))


async def setup(bot):
    await bot.add_cog(OmenCog(bot))
