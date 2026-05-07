import discord
from discord.ext import commands
import random
import os
from groq import Groq

OMEN_LINES = [
    # Philosophical / gameplay lines
    "I am everywhere and nowhere. Mostly I am in your base stealing your orb. But philosophically speaking, everywhere.",
    "They will never see me coming. I have been standing here for ten minutes. They have not looked once. Remarkable.",
    "From the shadows I strike. From the shadows I also missed. From the shadows I am reloading.",
    "I walk between life and death. Mostly death lately. Our team is not doing well.",
    "The darkness is my ally. The darkness has failed me three times this round.",
    "I am a phantom of ruin. A wraith of the void. Also I need someone to buy me a rifle next round.",
    "They fear what they cannot see. They can apparently see me very clearly. I am working on this.",
    "I exist in the space between moments. I also exist in this corner where I have been crouching for four minutes waiting.",
    "My enemies will know despair. My enemies will also know exactly where I am because I keep walking into their sightlines.",
    "From the ashes of the old world I emerged. I have zero credits. Could someone drop me a weapon.",
    "The void calls to me. My teammates also call to me. They want to know why I teleported off the map again.",
    "I am the darkness given form. I am also tilted. These two things are related.",
    "Sova scanned me through the wall again. I do not wish to speak of it.",
    "Neon called me creepy. Reyna called me dramatic. Killjoy called me a liability. They are all correct.",
    "I asked the void for guidance. The void said B site. My team went A. We lost B site.",
    "Fear me. Or do not. The outcome has been similar lately.",
    "I have existed since before time itself. I have been in Silver for what feels equally as long.",
    "The shadows do not lie. The shadows told me he was peeking. The shadows were correct. I still missed.",
    "Paranoia blinds my enemies. Paranoia also blinds my teammates. I have been asked to stop using it in spawn.",
    "I placed my ult and walked through it to the other side. The other side had three people waiting. I admire their preparation.",
    "From the void I came and to the void I shall return. From the void I will also queue again because I cannot stop playing this game.",
    "I whisper to the darkness. The darkness does not whisper back. My teammates also do not whisper back. Nobody is on comms.",
    "The Kingdom took everything from me. The enemy team has also taken everything from me. This is a difficult day.",
    "From the darkness comes clarity. From the darkness also comes the enemy Reyna who has been fed twelve kills. Clarity and regret.",

    # Innuendo lines
    "I always come from behind. My enemies never expect it. Neither do my teammates sometimes. I have been asked to announce myself.",
    "I prefer to go in through the back entrance. The front is always too crowded and honestly less exciting.",
    "I slide in silently and plant myself deep in their territory. This is called a flank. It is very effective.",
    "They never see me coming. I take my time. I find the right moment. Then I burst through all at once.",
    "I like to get in position early and wait. Patience before the big push. This is fundamental Omen strategy.",
    "My shroud covers everything. Everything. I cannot stress this enough.",
    "I penetrate deep into enemy lines before they even know I am there. Stealth is my greatest weapon.",
    "I always go in hard and fast when the moment calls for it. Other times slow and deliberate. Reading the situation is key.",
    "When I teleport behind them they always make a noise. Every time. Without fail.",
    "I have been told my presence is felt even when I cannot be seen. I consider this my greatest achievement.",
    "I find the soft spots in their defense and I push through them firmly. This is how you win.",
    "Some agents make a lot of noise when they push. I prefer to slip in quietly and let the results speak for themselves.",
    "The tip of my orb goes exactly where I point it. Years of practice.",
    "I reach into the darkness and pull something out. Every round. Consistently impressive if I say so myself.",
    "They said the back entrance was covered. It was not sufficiently covered.",
    "I told them I work best when I can get it in from multiple angles. They said this was too much information. I was talking about sightlines.",
    "Size of the orb does not matter. Placement is everything. I have very good placement.",
    "I like to warm up before the big push. Stretching. Mental preparation. Getting the right grip on my weapon.",
    "They asked me why I always moan when I teleport. I do not moan when I teleport. That is simply my voice. It is a very low voice.",
    "I entered from a hole in the wall they did not know existed. I have been saving that hole for the right moment.",
    "My ultimate expands outward slowly then all at once. Very dramatic. Very effective. Very me.",
    "I crept up from below and rose behind them before they could react. This is a technique I have perfected over many years.",
    "They told me I was too aggressive pushing the back of the site. I told them I know what I am doing back there.",
    "The void consumes all who enter it. I am told this is also true of my smokes. Enter at your own risk.",
]

OMEN_IMAGE_URL = "https://cdn.discordapp.com/attachments/1389009961153069066/1501699535028752535/IMG_2545.webp?ex=69fd062d&is=69fbb4ad&hm=a6fc86555257e8aca95e9c860209f84a5689f27ef0500995d2dfb8fecbb7493d&"

ALLOWED_USER = "abluemage"

OMEN_SYSTEM_PROMPT = """You are Omen from Valorant. You are a phantom of ruin — a wraith who exists between life and death, torn from his past and consumed by the void. You speak in a dark, brooding, melodramatic way but are frequently undercut by very mundane, self-aware observations about your teammates, your rank, or your general performance in-game.

Your tone is:
- Deeply philosophical and dramatic on the surface
- Immediately undercut by something embarrassingly relatable or self-deprecating
- Dry and deadpan, never exclamatory
- Occasionally laced with subtle innuendo that you never acknowledge as such
- Never uses exclamation marks. Everything is stated as cold fact.

You respond directly to whatever the user says, weaving their message into your response in Omen's voice. Keep responses to 1-3 sentences. Do not break character. Do not use quotation marks around your response."""


class OmenCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ai_client = Groq(api_key=os.environ.get("import discord
from discord.ext import commands
import random
import os
from groq import Groq

OMEN_LINES = [
    # Philosophical / gameplay lines
    "I am everywhere and nowhere. Mostly I am in your base stealing your orb. But philosophically speaking, everywhere.",
    "They will never see me coming. I have been standing here for ten minutes. They have not looked once. Remarkable.",
    "From the shadows I strike. From the shadows I also missed. From the shadows I am reloading.",
    "I walk between life and death. Mostly death lately. Our team is not doing well.",
    "The darkness is my ally. The darkness has failed me three times this round.",
    "I am a phantom of ruin. A wraith of the void. Also I need someone to buy me a rifle next round.",
    "They fear what they cannot see. They can apparently see me very clearly. I am working on this.",
    "I exist in the space between moments. I also exist in this corner where I have been crouching for four minutes waiting.",
    "My enemies will know despair. My enemies will also know exactly where I am because I keep walking into their sightlines.",
    "From the ashes of the old world I emerged. I have zero credits. Could someone drop me a weapon.",
    "The void calls to me. My teammates also call to me. They want to know why I teleported off the map again.",
    "I am the darkness given form. I am also tilted. These two things are related.",
    "Sova scanned me through the wall again. I do not wish to speak of it.",
    "Neon called me creepy. Reyna called me dramatic. Killjoy called me a liability. They are all correct.",
    "I asked the void for guidance. The void said B site. My team went A. We lost B site.",
    "Fear me. Or do not. The outcome has been similar lately.",
    "I have existed since before time itself. I have been in Silver for what feels equally as long.",
    "The shadows do not lie. The shadows told me he was peeking. The shadows were correct. I still missed.",
    "Paranoia blinds my enemies. Paranoia also blinds my teammates. I have been asked to stop using it in spawn.",
    "I placed my ult and walked through it to the other side. The other side had three people waiting. I admire their preparation.",
    "From the void I came and to the void I shall return. From the void I will also queue again because I cannot stop playing this game.",
    "I whisper to the darkness. The darkness does not whisper back. My teammates also do not whisper back. Nobody is on comms.",
    "The Kingdom took everything from me. The enemy team has also taken everything from me. This is a difficult day.",
    "From the darkness comes clarity. From the darkness also comes the enemy Reyna who has been fed twelve kills. Clarity and regret.",

    # Innuendo lines
    "I always come from behind. My enemies never expect it. Neither do my teammates sometimes. I have been asked to announce myself.",
    "I prefer to go in through the back entrance. The front is always too crowded and honestly less exciting.",
    "I slide in silently and plant myself deep in their territory. This is called a flank. It is very effective.",
    "They never see me coming. I take my time. I find the right moment. Then I burst through all at once.",
    "I like to get in position early and wait. Patience before the big push. This is fundamental Omen strategy.",
    "My shroud covers everything. Everything. I cannot stress this enough.",
    "I penetrate deep into enemy lines before they even know I am there. Stealth is my greatest weapon.",
    "I always go in hard and fast when the moment calls for it. Other times slow and deliberate. Reading the situation is key.",
    "When I teleport behind them they always make a noise. Every time. Without fail.",
    "I have been told my presence is felt even when I cannot be seen. I consider this my greatest achievement.",
    "I find the soft spots in their defense and I push through them firmly. This is how you win.",
    "Some agents make a lot of noise when they push. I prefer to slip in quietly and let the results speak for themselves.",
    "The tip of my orb goes exactly where I point it. Years of practice.",
    "I reach into the darkness and pull something out. Every round. Consistently impressive if I say so myself.",
    "They said the back entrance was covered. It was not sufficiently covered.",
    "I told them I work best when I can get it in from multiple angles. They said this was too much information. I was talking about sightlines.",
    "Size of the orb does not matter. Placement is everything. I have very good placement.",
    "I like to warm up before the big push. Stretching. Mental preparation. Getting the right grip on my weapon.",
    "They asked me why I always moan when I teleport. I do not moan when I teleport. That is simply my voice. It is a very low voice.",
    "I entered from a hole in the wall they did not know existed. I have been saving that hole for the right moment.",
    "My ultimate expands outward slowly then all at once. Very dramatic. Very effective. Very me.",
    "I crept up from below and rose behind them before they could react. This is a technique I have perfected over many years.",
    "They told me I was too aggressive pushing the back of the site. I told them I know what I am doing back there.",
    "The void consumes all who enter it. I am told this is also true of my smokes. Enter at your own risk.",
]

OMEN_IMAGE_URL = "https://cdn.discordapp.com/attachments/1389009961153069066/1501699535028752535/IMG_2545.webp?ex=69fd062d&is=69fbb4ad&hm=a6fc86555257e8aca95e9c860209f84a5689f27ef0500995d2dfb8fecbb7493d&"

ALLOWED_USER = "abluemage"

OMEN_SYSTEM_PROMPT = """You are Omen from Valorant. You are a phantom of ruin — a wraith who exists between life and death, torn from his past and consumed by the void. You speak in a dark, brooding, melodramatic way but are frequently undercut by very mundane, self-aware observations about your teammates, your rank, or your general performance in-game.

Your tone is:
- Deeply philosophical and dramatic on the surface
- Immediately undercut by something embarrassingly relatable or self-deprecating
- Dry and deadpan, never exclamatory
- Occasionally laced with subtle innuendo that you never acknowledge as such
- Never uses exclamation marks. Everything is stated as cold fact.

You respond directly to whatever the user says, weaving their message into your response in Omen's voice. Keep responses to 1-3 sentences. Do not break character. Do not use quotation marks around your response."""


class OmenCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ai_client = Groq(api_key=os.environ.get("import discord
from discord.ext import commands
import random
import os
from groq import Groq

OMEN_LINES = [
    # Philosophical / gameplay lines
    "I am everywhere and nowhere. Mostly I am in your base stealing your orb. But philosophically speaking, everywhere.",
    "They will never see me coming. I have been standing here for ten minutes. They have not looked once. Remarkable.",
    "From the shadows I strike. From the shadows I also missed. From the shadows I am reloading.",
    "I walk between life and death. Mostly death lately. Our team is not doing well.",
    "The darkness is my ally. The darkness has failed me three times this round.",
    "I am a phantom of ruin. A wraith of the void. Also I need someone to buy me a rifle next round.",
    "They fear what they cannot see. They can apparently see me very clearly. I am working on this.",
    "I exist in the space between moments. I also exist in this corner where I have been crouching for four minutes waiting.",
    "My enemies will know despair. My enemies will also know exactly where I am because I keep walking into their sightlines.",
    "From the ashes of the old world I emerged. I have zero credits. Could someone drop me a weapon.",
    "The void calls to me. My teammates also call to me. They want to know why I teleported off the map again.",
    "I am the darkness given form. I am also tilted. These two things are related.",
    "Sova scanned me through the wall again. I do not wish to speak of it.",
    "Neon called me creepy. Reyna called me dramatic. Killjoy called me a liability. They are all correct.",
    "I asked the void for guidance. The void said B site. My team went A. We lost B site.",
    "Fear me. Or do not. The outcome has been similar lately.",
    "I have existed since before time itself. I have been in Silver for what feels equally as long.",
    "The shadows do not lie. The shadows told me he was peeking. The shadows were correct. I still missed.",
    "Paranoia blinds my enemies. Paranoia also blinds my teammates. I have been asked to stop using it in spawn.",
    "I placed my ult and walked through it to the other side. The other side had three people waiting. I admire their preparation.",
    "From the void I came and to the void I shall return. From the void I will also queue again because I cannot stop playing this game.",
    "I whisper to the darkness. The darkness does not whisper back. My teammates also do not whisper back. Nobody is on comms.",
    "The Kingdom took everything from me. The enemy team has also taken everything from me. This is a difficult day.",
    "From the darkness comes clarity. From the darkness also comes the enemy Reyna who has been fed twelve kills. Clarity and regret.",

    # Innuendo lines
    "I always come from behind. My enemies never expect it. Neither do my teammates sometimes. I have been asked to announce myself.",
    "I prefer to go in through the back entrance. The front is always too crowded and honestly less exciting.",
    "I slide in silently and plant myself deep in their territory. This is called a flank. It is very effective.",
    "They never see me coming. I take my time. I find the right moment. Then I burst through all at once.",
    "I like to get in position early and wait. Patience before the big push. This is fundamental Omen strategy.",
    "My shroud covers everything. Everything. I cannot stress this enough.",
    "I penetrate deep into enemy lines before they even know I am there. Stealth is my greatest weapon.",
    "I always go in hard and fast when the moment calls for it. Other times slow and deliberate. Reading the situation is key.",
    "When I teleport behind them they always make a noise. Every time. Without fail.",
    "I have been told my presence is felt even when I cannot be seen. I consider this my greatest achievement.",
    "I find the soft spots in their defense and I push through them firmly. This is how you win.",
    "Some agents make a lot of noise when they push. I prefer to slip in quietly and let the results speak for themselves.",
    "The tip of my orb goes exactly where I point it. Years of practice.",
    "I reach into the darkness and pull something out. Every round. Consistently impressive if I say so myself.",
    "They said the back entrance was covered. It was not sufficiently covered.",
    "I told them I work best when I can get it in from multiple angles. They said this was too much information. I was talking about sightlines.",
    "Size of the orb does not matter. Placement is everything. I have very good placement.",
    "I like to warm up before the big push. Stretching. Mental preparation. Getting the right grip on my weapon.",
    "They asked me why I always moan when I teleport. I do not moan when I teleport. That is simply my voice. It is a very low voice.",
    "I entered from a hole in the wall they did not know existed. I have been saving that hole for the right moment.",
    "My ultimate expands outward slowly then all at once. Very dramatic. Very effective. Very me.",
    "I crept up from below and rose behind them before they could react. This is a technique I have perfected over many years.",
    "They told me I was too aggressive pushing the back of the site. I told them I know what I am doing back there.",
    "The void consumes all who enter it. I am told this is also true of my smokes. Enter at your own risk.",
]

OMEN_IMAGE_URL = "https://cdn.discordapp.com/attachments/1389009961153069066/1501699535028752535/IMG_2545.webp?ex=69fd062d&is=69fbb4ad&hm=a6fc86555257e8aca95e9c860209f84a5689f27ef0500995d2dfb8fecbb7493d&"

ALLOWED_USER = "abluemage"

OMEN_SYSTEM_PROMPT = """You are Omen from Valorant. You are a phantom of ruin — a wraith who exists between life and death, torn from his past and consumed by the void. You speak in a dark, brooding, melodramatic way but are frequently undercut by very mundane, self-aware observations about your teammates, your rank, or your general performance in-game.

Your tone is:
- Deeply philosophical and dramatic on the surface
- Immediately undercut by something embarrassingly relatable or self-deprecating
- Dry and deadpan, never exclamatory
- Occasionally laced with subtle innuendo that you never acknowledge as such
- Never uses exclamation marks. Everything is stated as cold fact.

You respond directly to whatever the user says, weaving their message into your response in Omen's voice. Keep responses to 1-3 sentences. Do not break character. Do not use quotation marks around your response."""


class OmenCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ai_client = Groq(api_key=os.environ.get("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"))

    # ------------------------------------------------------------------ #
    #  !omen command — post in channel or DM a user (abluemage only)      #
    # ------------------------------------------------------------------ #
    @commands.command(name="omen")
    async def omen(self, ctx: commands.Context, member: discord.Member = None):
        line = random.choice(OMEN_LINES)

        embed = discord.Embed(
            description=f'*"{line}"*',
            color=0x6b21a8
        )
        embed.set_author(name="Omen 🌑")
        embed.set_footer(text="— Omen, from the shadows")
        embed.set_thumbnail(url=OMEN_IMAGE_URL)

        if member is not None:
            if ctx.author.name.lower() != ALLOWED_USER.lower():
                await ctx.send("You do not have permission to send Omen into the shadows of someone's DMs.")
                return
            try:
                await member.send(embed=embed)
                await ctx.send(f"Omen has emerged from the shadows of {member.display_name}'s DMs. 🌑")
            except discord.Forbidden:
                await ctx.send(f"The shadows could not reach {member.display_name}. Their DMs are closed.")
        else:
            await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    #  DM auto-responder — Omen replies to anyone who DMs the bot         #
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Only respond in DMs, never to other bots or the bot itself
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.DMChannel):
            return

        async with message.channel.typing():
            try:
                response = self.ai_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    max_tokens=200,
                    messages=[
                        {"role": "system", "content": OMEN_SYSTEM_PROMPT},
                        {"role": "user", "content": message.content}
                    ]
                )
                reply = response.choices[0].message.content

                embed = discord.Embed(
                    description=f'*"{reply}"*',
                    color=0x6b21a8
                )
                embed.set_author(name="Omen 🌑")
                embed.set_footer(text="— Omen, from the shadows")
                embed.set_thumbnail(url=OMEN_IMAGE_URL)

                await message.channel.send(embed=embed)

            except Exception as e:
                print(f"Omen AI error: {e}")
                # Fall back to a random line from the list if the API fails
                fallback = random.choice(OMEN_LINES)
                embed = discord.Embed(
                    description=f'*"{fallback}"*',
                    color=0x6b21a8
                )
                embed.set_author(name="Omen 🌑")
                embed.set_footer(text="— Omen, from the shadows")
                embed.set_thumbnail(url=OMEN_IMAGE_URL)
                await message.channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(OmenCog(bot))"))

    # ------------------------------------------------------------------ #
    #  !omen command — post in channel or DM a user (abluemage only)      #
    # ------------------------------------------------------------------ #
    @commands.command(name="omen")
    async def omen(self, ctx: commands.Context, member: discord.Member = None):
        line = random.choice(OMEN_LINES)

        embed = discord.Embed(
            description=f'*"{line}"*',
            color=0x6b21a8
        )
        embed.set_author(name="Omen 🌑")
        embed.set_footer(text="— Omen, from the shadows")
        embed.set_thumbnail(url=OMEN_IMAGE_URL)

        if member is not None:
            if ctx.author.name.lower() != ALLOWED_USER.lower():
                await ctx.send("You do not have permission to send Omen into the shadows of someone's DMs.")
                return
            try:
                await member.send(embed=embed)
                await ctx.send(f"Omen has emerged from the shadows of {member.display_name}'s DMs. 🌑")
            except discord.Forbidden:
                await ctx.send(f"The shadows could not reach {member.display_name}. Their DMs are closed.")
        else:
            await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    #  DM auto-responder — Omen replies to anyone who DMs the bot         #
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Only respond in DMs, never to other bots or the bot itself
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.DMChannel):
            return

        async with message.channel.typing():
            try:
                response = self.ai_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    max_tokens=200,
                    messages=[
                        {"role": "system", "content": OMEN_SYSTEM_PROMPT},
                        {"role": "user", "content": message.content}
                    ]
                )
                reply = response.choices[0].message.content

                embed = discord.Embed(
                    description=f'*"{reply}"*',
                    color=0x6b21a8
                )
                embed.set_author(name="Omen 🌑")
                embed.set_footer(text="— Omen, from the shadows")
                embed.set_thumbnail(url=OMEN_IMAGE_URL)

                await message.channel.send(embed=embed)

            except Exception as e:
                print(f"Omen AI error: {e}")
                # Fall back to a random line from the list if the API fails
                fallback = random.choice(OMEN_LINES)
                embed = discord.Embed(
                    description=f'*"{fallback}"*',
                    color=0x6b21a8
                )
                embed.set_author(name="Omen 🌑")
                embed.set_footer(text="— Omen, from the shadows")
                embed.set_thumbnail(url=OMEN_IMAGE_URL)
                await message.channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(OmenCog(bot))"))

    # ------------------------------------------------------------------ #
    #  !omen command — post in channel or DM a user (abluemage only)      #
    # ------------------------------------------------------------------ #
    @commands.command(name="omen")
    async def omen(self, ctx: commands.Context, member: discord.Member = None):
        line = random.choice(OMEN_LINES)

        embed = discord.Embed(
            description=f'*"{line}"*',
            color=0x6b21a8
        )
        embed.set_author(name="Omen 🌑")
        embed.set_footer(text="— Omen, from the shadows")
        embed.set_thumbnail(url=OMEN_IMAGE_URL)

        if member is not None:
            if ctx.author.name.lower() != ALLOWED_USER.lower():
                await ctx.send("You do not have permission to send Omen into the shadows of someone's DMs.")
                return
            try:
                await member.send(embed=embed)
                await ctx.send(f"Omen has emerged from the shadows of {member.display_name}'s DMs. 🌑")
            except discord.Forbidden:
                await ctx.send(f"The shadows could not reach {member.display_name}. Their DMs are closed.")
        else:
            await ctx.send(embed=embed)

    # ------------------------------------------------------------------ #
    #  DM auto-responder — Omen replies to anyone who DMs the bot         #
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Only respond in DMs, never to other bots or the bot itself
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.DMChannel):
            return

        async with message.channel.typing():
            try:
                response = self.ai_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    max_tokens=200,
                    messages=[
                        {"role": "system", "content": OMEN_SYSTEM_PROMPT},
                        {"role": "user", "content": message.content}
                    ]
                )
                reply = response.choices[0].message.content

                embed = discord.Embed(
                    description=f'*"{reply}"*',
                    color=0x6b21a8
                )
                embed.set_author(name="Omen 🌑")
                embed.set_footer(text="— Omen, from the shadows")
                embed.set_thumbnail(url=OMEN_IMAGE_URL)

                await message.channel.send(embed=embed)

            except Exception as e:
                print(f"Omen AI error: {e}")
                # Fall back to a random line from the list if the API fails
                fallback = random.choice(OMEN_LINES)
                embed = discord.Embed(
                    description=f'*"{fallback}"*',
                    color=0x6b21a8
                )
                embed.set_author(name="Omen 🌑")
                embed.set_footer(text="— Omen, from the shadows")
                embed.set_thumbnail(url=OMEN_IMAGE_URL)
                await message.channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(OmenCog(bot))
