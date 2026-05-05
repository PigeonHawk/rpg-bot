import discord
from discord.ext import commands
import random
from pathlib import Path

HAM = Path("assets/hamtaro")

# ── Response pools ─────────────────────────────────────────────────────────────
# Each entry: (text, sprite_filename)

HAMTARO_SUMMON = [
    ("Hamtaro scurries in! His little legs are going very fast.", "ham_walk1"),
    ("Hamtaro arrives! He stops, looks around, then wiggles his nose.", "ham_walk2"),
    ("Hamtaro trots in from somewhere sunny. He seems very pleased.", "ham_walk3"),
    ("Hamtaro waves! He is very happy to see you. Very happy.", "ham_wave1"),
    ("Hamtaro waves both paws enthusiastically. He has been waiting.", "ham_wave2"),
    ("Hamtaro appears! He does a little spin just because he can.", "ham_spin1"),
    ("Hamtaro is here! He lets out a tiny excited squeak.", "ham_happy1"),
    ("Hamtaro trots over with his cheeks puffed out proudly.", "ham_happy2"),
]

HAMTARO_SEED = [
    ("Hamtaro finds a sunflower seed. His cheeks inflate immediately.", "ham_chubby1"),
    ("Hamtaro stuffs both cheeks full. He looks like a small golden balloon.", "ham_chubby2"),
    ("Hamtaro discovers seeds. He stores seventeen of them in his cheeks. He is full.", "ham_chubby3"),
    ("Hamtaro eats a seed. His eyes go wide. He wants more seeds.", "ham_eat1"),
    ("Hamtaro chomps away happily. Nom nom nom. He does not share.", "ham_eat2"),
    ("Hamtaro receives a seed offering. He accepts it with both paws. Very polite.", "ham_chubby1"),
    ("Hamtaro spots the seeds from across the room. He was already running.", "ham_happy3"),
]

HAMTARO_SPIN = [
    ("Hamtaro starts spinning. He has somewhere to be. Probably.", "ham_spin1"),
    ("Hamtaro spins in a circle three times. He does not know why. He is happy.", "ham_spin2"),
    ("Hamtaro runs in a full lap then skids to a stop. Excellent run.", "ham_spin3"),
    ("Hamtaro dashes off at full speed! His tiny legs are a blur.", "ham_run1"),
    ("Hamtaro zooms past. He waves without slowing down.", "ham_run2"),
    ("Hamtaro does a victory spin. He earned it. We are not sure what he did.", "ham_spin1"),
    ("Hamtaro runs in a happy circle. This is exercise but also fun.", "ham_spin2"),
]

HAMTARO_SLEEP = [
    ("Hamtaro curls into a tiny ball. He is asleep before he finishes curling.", "ham_sleep1"),
    ("Hamtaro yawns so wide his whole face disappears. Then he sleeps.", "ham_sleep2"),
    ("Hamtaro finds a cozy corner and becomes a small round loaf. He is dreaming.", "ham_sleep3"),
    ("Hamtaro falls asleep mid-step. He is fine. He is just resting his eyes.", "ham_sleep4"),
    ("Hamtaro dozes off. His little nose twitches. He is probably dreaming of seeds.", "ham_sleep1"),
    ("Hamtaro makes a tiny bed out of nothing and curls up immediately.", "ham_sleep2"),
    ("Hamtaro sleeps soundly. Do not disturb Hamtaro. He worked hard today.", "ham_sleep3"),
]

HAMTARO_CRY = [
    ("Hamtaro looks sad. His ears droop. A single tiny tear.", "ham_sad1"),
    ("Hamtaro is upset about something. He will not say what. He sniffles.", "ham_sad2"),
    ("Hamtaro cries! Big round tears. Someone please help Hamtaro.", "ham_cry1"),
    ("Hamtaro weeps openly. He is not ashamed. Feelings are valid.", "ham_cry2"),
    ("Hamtaro's lower lip wobbles. Something has gone very wrong.", "ham_sad1"),
    ("Hamtaro droops sadly. He needed more seeds. There were not enough seeds.", "ham_sad2"),
    ("Hamtaro is having a hard day. He cries a little. He will be okay.", "ham_cry1"),
]

HAMTARO_LOVE = [
    ("Hamtaro spots someone special. His eyes turn into hearts immediately.", "ham_love1"),
    ("Hamtaro blushes so hard his cheeks glow. He hides his face.", "ham_blush1"),
    ("Hamtaro is in love. He spins around. He runs into a wall. He is okay.", "ham_love2"),
    ("Hamtaro sees you and his heart does a little jump. He squeaks softly.", "ham_love3"),
    ("Hamtaro blushes and covers his face with both tiny paws.", "ham_blush2"),
    ("Hamtaro holds out a sunflower seed as a gift. This is his love language.", "ham_love1"),
    ("Hamtaro's cheeks are very pink. He refuses to make eye contact. He is thriving.", "ham_blush1"),
]

HAMTARO_ANGRY = [
    ("Hamtaro is upset! He puffs up as big as he can. It is a little big.", "ham_angry1"),
    ("Hamtaro stamps his tiny foot. He means business.", "ham_angry2"),
    ("Hamtaro glares. His cheeks puff with fury. He is very small and very serious.", "ham_angry3"),
    ("Hamtaro is fuming. Someone took his seed. This is unacceptable.", "ham_angry4"),
    ("Hamtaro crosses his little arms. He will not be moved on this.", "ham_angry1"),
    ("Hamtaro is angry but he is also very round so the effect is mixed.", "ham_angry2"),
    ("Hamtaro has had enough. He makes a tiny fist. He shakes it.", "ham_angry3"),
]

HAMTARO_HAPPY = [
    ("Hamtaro is SO happy! He bounces in place three times!", "ham_happy1"),
    ("Hamtaro grins with his whole face. His cheeks nearly pop off.", "ham_happy2"),
    ("Hamtaro does his happiest face. It is a very good face.", "ham_happy3"),
    ("Hamtaro celebrates! He does not know what he is celebrating. He does not need to.", "ham_happy1"),
    ("Hamtaro beams with joy. The sun shines a little brighter. Probably because of Hamtaro.", "ham_happy2"),
    ("Hamtaro grins so hard his eyes close. This is peak Hamtaro.", "ham_happy3"),
    ("Hamtaro is simply very happy today and wanted you to know.", "ham_happy1"),
]

# ── Helper ────────────────────────────────────────────────────────────────────
async def send_ham(ctx: commands.Context, pool: list, title: str = ""):
    text, sprite = random.choice(pool)
    img_path = HAM / f"{sprite}.png"

    embed = discord.Embed(description=f"*{text}*", color=0xf5a623)
    if title:
        embed.set_author(name=title)
    embed.set_image(url="attachment://ham.png")

    if img_path.exists():
        file = discord.File(str(img_path), filename="ham.png")
        await ctx.send(embed=embed, file=file)
    else:
        await ctx.send(embed=embed)

# ── Cog ───────────────────────────────────────────────────────────────────────
class HamtaroCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="hamtaro")
    async def hamtaro(self, ctx: commands.Context):
        await send_ham(ctx, HAMTARO_SUMMON, "Hamtaro!")

    @commands.command(name="hamtaroseed")
    async def hamtaroseed(self, ctx: commands.Context):
        await send_ham(ctx, HAMTARO_SEED, "Seed time!")

    @commands.command(name="hamtarospin")
    async def hamtarospin(self, ctx: commands.Context):
        await send_ham(ctx, HAMTARO_SPIN, "Hamtaro is spinning!")

    @commands.command(name="hamtarosleep")
    async def hamtarosleep(self, ctx: commands.Context):
        await send_ham(ctx, HAMTARO_SLEEP, "Hamtaro is sleepy...")

    @commands.command(name="hamtarocry")
    async def hamtarocry(self, ctx: commands.Context):
        await send_ham(ctx, HAMTARO_CRY, "Hamtaro is sad...")

    @commands.command(name="hamtarolove")
    async def hamtarolove(self, ctx: commands.Context):
        await send_ham(ctx, HAMTARO_LOVE, "Hamtaro is in love!")

    @commands.command(name="hamtaroangry")
    async def hamtaroangry(self, ctx: commands.Context):
        await send_ham(ctx, HAMTARO_ANGRY, "Hamtaro is angry!")

    @commands.command(name="hamtarohappy")
    async def hamtarohappy(self, ctx: commands.Context):
        await send_ham(ctx, HAMTARO_HAPPY, "Hamtaro is happy!")

    @commands.command(name="hamtarohelp")
    async def hamtarohelp(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🐹 Hamtaro Commands",
            description="Hamstur! Hamtaro is here to help!",
            color=0xf5a623
        )
        embed.add_field(name="Commands", value=(
            "`!hamtaro` — Summon Hamtaro\n"
            "`!hamtaroseed` — Give Hamtaro a seed\n"
            "`!hamtarospin` — Make Hamtaro spin\n"
            "`!hamtarosleep` — Hamtaro needs a nap\n"
            "`!hamtarocry` — Hamtaro is sad\n"
            "`!hamtarolove` — Hamtaro is in love\n"
            "`!hamtaroangry` — Hamtaro is upset\n"
            "`!hamtarohappy` — Hamtaro is very happy\n"
            "`!hamtarohelp` — This help message"
        ), inline=False)
        embed.set_footer(text="Hamstur!")
        img_path = HAM / "ham_wave1.png"
        if img_path.exists():
            file = discord.File(str(img_path), filename="ham.png")
            embed.set_thumbnail(url="attachment://ham.png")
            await ctx.send(embed=embed, file=file)
        else:
            await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(HamtaroCog(bot))
