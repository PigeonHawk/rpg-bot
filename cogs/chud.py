import discord
from discord.ext import commands
import random
from pathlib import Path

# ── Chud image paths ──────────────────────────────────────────────────────────
CHUD_DIR = Path("assets")

CHUD_DROOL = CHUD_DIR / "chud_drool.png"   # default summon / idle drooling
CHUD_WATER = CHUD_DIR / "chud_water.png"   # drinking / feeding / happy
CHUD_ROAM  = CHUD_DIR / "chud_roam.png"    # exploring / poking / rolling
CHUD_LOAF  = CHUD_DIR / "chud_loaf.png"    # sleeping / sad / tired

# ── Response pools ────────────────────────────────────────────────────────────

CHUD_SUMMON = [
    # roam image — entering the scene
    ("Chud roams into existence. Nobody invited him. He does not need an invitation.", CHUD_ROAM),
    ("Chud wanders in from somewhere off-screen. He has been walking for a while probably.", CHUD_ROAM),
    ("Chud roams into view. He pauses. He continues. He has arrived.", CHUD_ROAM),
    ("Chud shuffles in from the left. He looks around. Nothing concerns him.", CHUD_ROAM),
    ("Chud materializes mid-roam. He was already going somewhere. This is a detour.", CHUD_ROAM),
    ("Chud enters. He does a small lap of the area. He stops. He is here now.", CHUD_ROAM),
    ("Chud wanders in and immediately investigates the corner. Nothing is there. He stays anyway.", CHUD_ROAM),
    ("Chud ambles into existence like he always does. Unhurried. Unbothered. Present.", CHUD_ROAM),
    ("Chud roams in. He sniffs the air. He does not react to what he smells. He sits.", CHUD_ROAM),
    ("Chud arrives mid-wander. He has been walking since before you called him. He was coming anyway.", CHUD_ROAM),
    ("Chud shuffles in from an unknown direction. He pauses to look at nothing. Then continues.", CHUD_ROAM),
    ("Chud roams into the room and does a full lap before acknowledging anyone.", CHUD_ROAM),
    # drool image — settling in
    ("Chud has appeared. He is drooling slightly. He has been drooling since before he got here.", CHUD_DROOL),
    ("Chud emerges. A single drop of drool falls. He does not notice. He does not need to.", CHUD_DROOL),
    ("There is Chud. He was always here. The drool confirms it.", CHUD_DROOL),
    ("Chud is here. He looks at you. You look at him. He drools. This is the greeting.", CHUD_DROOL),
    ("Chud has arrived. He drools softly onto the floor. He seems at peace.", CHUD_DROOL),
    ("Chud appears and blinks. A small drool follows. He offers no explanation.", CHUD_DROOL),
    # loaf image — already comfortable
    ("Chud arrives and immediately becomes a loaf. He did not waste any time.", CHUD_LOAF),
    ("Chud roams in, completes one circle, and collapses into loaf position. Journey complete.", CHUD_LOAF),
    ("Chud enters and flattens himself into loaf mode within seconds. He is home now.", CHUD_LOAF),
    ("Chud shows up and immediately lies down. He has been standing long enough.", CHUD_LOAF),
    ("Chud wanders in and parks himself. He is a loaf now. He will be here a while.", CHUD_LOAF),
]

CHUD_FEED = [
    ("You offer Chud some food. He laps it up immediately without looking.", CHUD_WATER),
    ("Chud sees the bowl before you even put it down. He is already drinking.", CHUD_WATER),
    ("You feed Chud. He finishes instantly. He stares at you for more.", CHUD_WATER),
    ("Chud eats. He makes eye contact the entire time. Unsettling.", CHUD_WATER),
    ("You give Chud a snack. He inhales it. His tongue flops out happily.", CHUD_WATER),
    ("Chud receives food. This is the best moment of his life. Again.", CHUD_WATER),
    ("The bowl is placed. Chud does not wait. He has never waited.", CHUD_WATER),
    ("You feed Chud. He wiggles. This is his victory.", CHUD_WATER),
    ("Chud discovers the food. He is overjoyed. He shows it by eating faster.", CHUD_WATER),
    ("Chud accepts your offering. He is briefly satisfied. Only briefly.", CHUD_WATER),
    ("You present food to Chud. He headbutts the bowl appreciatively.", CHUD_WATER),
    ("Chud drinks from his bowl with great enthusiasm and no grace.", CHUD_WATER),
]

CHUD_PET = [
    ("You pet Chud. He leans into it and starts drooling more. Success.", CHUD_DROOL),
    ("Chud accepts the pets. He does not react outwardly. Inside he is thrilled.", CHUD_DROOL),
    ("You scratch behind Chud's head. He tilts slightly. A single drool.", CHUD_DROOL),
    ("Chud tolerates your petting. This is the highest honor he can give.", CHUD_DROOL),
    ("You pet Chud. He blinks once. This means thank you in Chud language.", CHUD_DROOL),
    ("Chud closes his eyes as you pet him. He is at peace. He is drooling.", CHUD_DROOL),
    ("You give Chud gentle pats. He sighs heavily. He is content.", CHUD_LOAF),
    ("Chud melts slightly under your hand. He becomes more loaf-shaped.", CHUD_LOAF),
    ("You pet Chud and he immediately flops over. Maximum comfort achieved.", CHUD_LOAF),
    ("Chud receives pets. He enters a trance-like state. He is still drooling.", CHUD_DROOL),
    ("You stroke Chud gently. He makes a sound like a damp sponge. Affectionate.", CHUD_DROOL),
    ("Chud feels your hand. He does not move. He approves.", CHUD_DROOL),
]

CHUD_POKE = [
    ("You poke Chud. He jiggles slightly. He looks at you.", CHUD_ROAM),
    ("You poke Chud. He pokes back. You did not expect this.", CHUD_ROAM),
    ("Chud is poked. He wanders off a few steps then forgets why.", CHUD_ROAM),
    ("You poke Chud. He squints. He is processing this.", CHUD_DROOL),
    ("Chud is poked. He drools slightly more. This is his response.", CHUD_DROOL),
    ("You poke Chud in the side. He spins around slowly. He finds nothing.", CHUD_ROAM),
    ("Chud is poked. He starts roaming. Destination unknown.", CHUD_ROAM),
    ("You poke Chud. He pokes the air in front of him. Not quite right but he tried.", CHUD_ROAM),
    ("Chud receives a poke. He looks offended for one second then forgets.", CHUD_DROOL),
    ("You poke Chud. He walks in a small circle and sits back down.", CHUD_ROAM),
    ("Chud is poked. He makes a disapproving face. Then he drools anyway.", CHUD_DROOL),
    ("You poke Chud firmly. He wobbles. He maintains eye contact throughout.", CHUD_DROOL),
    ("Chud is poked. He wanders toward you. Then past you. He is gone briefly.", CHUD_ROAM),
]

CHUD_ROLLOVER = [
    ("You ask Chud to roll over. He does. Slowly. Like a boulder.", CHUD_LOAF),
    ("Chud rolls over with surprising commitment. He stays there.", CHUD_LOAF),
    ("You say roll over. Chud considers this. He rolls. He does not get up.", CHUD_LOAF),
    ("Chud flops onto his side. This took everything he had.", CHUD_LOAF),
    ("Chud rolls over and immediately falls asleep in the new position.", CHUD_LOAF),
    ("You command Chud to roll over. He does. He is crying a little. He is fine.", CHUD_LOAF),
    ("Chud performs a full roll. He blinks upside down at you. Achievement.", CHUD_LOAF),
    ("Chud rolls over and becomes a perfect loaf. He is immovable now.", CHUD_LOAF),
    ("You ask Chud to roll over. He roams around first. Then he rolls. His way.", CHUD_ROAM),
    ("Chud attempts to roll over. He makes it halfway. Close enough.", CHUD_LOAF),
    ("Chud rolls over dramatically. A single tear falls. He is okay.", CHUD_LOAF),
    ("You tell Chud to roll over. He stares at you. Then rolls. Then drools.", CHUD_DROOL),
    ("Chud executes the rollover flawlessly. He is now a loaf. He will not move.", CHUD_LOAF),
]

# ── Helper ────────────────────────────────────────────────────────────────────
async def send_chud(ctx: commands.Context, pool: list, title: str = None):
    text, img_path = random.choice(pool)
    embed = discord.Embed(
        description=f"*{text}*",
        color=0xf5c518
    )
    if title:
        embed.set_author(name=title)
    embed.set_image(url="attachment://chud.png")
    file = discord.File(str(img_path), filename="chud.png")
    await ctx.send(embed=embed, file=file)

# ── Cog ───────────────────────────────────────────────────────────────────────
class ChudCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="chud")
    async def chud(self, ctx: commands.Context):
        await send_chud(ctx, CHUD_SUMMON, "Chud has appeared.")

    @commands.command(name="chudfeed")
    async def chudfeed(self, ctx: commands.Context):
        await send_chud(ctx, CHUD_FEED, "Feeding Chud...")

    @commands.command(name="chudpet")
    async def chudpet(self, ctx: commands.Context):
        await send_chud(ctx, CHUD_PET, "Petting Chud...")

    @commands.command(name="chudpoke")
    async def chudpoke(self, ctx: commands.Context):
        await send_chud(ctx, CHUD_POKE, "Poking Chud...")

    @commands.command(name="chudrollover")
    async def chudrollover(self, ctx: commands.Context):
        await send_chud(ctx, CHUD_ROLLOVER, "Roll over, Chud.")

    @commands.command(name="chudhelp")
    async def chudhelp(self, ctx: commands.Context):
        embed = discord.Embed(
            title="Chud Commands",
            description="A small yellow creature of unknown origin. He is always here.",
            color=0xf5c518
        )
        embed.add_field(name="Commands", value=(
            "`!chud` - Summon Chud\n"
            "`!chudfeed` - Feed Chud\n"
            "`!chudpet` - Pet Chud\n"
            "`!chudpoke` - Poke Chud\n"
            "`!chudrollover` - Tell Chud to roll over\n"
            "`!chudhelp` - This help message"
        ), inline=False)
        embed.set_footer(text="He is always watching.")
        file = discord.File(str(CHUD_DROOL), filename="chud.png")
        embed.set_thumbnail(url="attachment://chud.png")
        await ctx.send(embed=embed, file=file)


async def setup(bot):
    await bot.add_cog(ChudCog(bot))
