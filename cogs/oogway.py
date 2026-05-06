import discord
from discord.ext import commands
import random

OOGWAY_SAYINGS = [
    # Original batch
    "There are no accidents. Except for that one time I slipped on a banana peel. That was definitely an accident.",
    "Yesterday is history, tomorrow is a mystery, but today is a gift. That is why it is called the present. I have been saying this for 1000 years and nobody laughs.",
    "The path to victory is to find what you came with. I forgot what I came with.",
    "Your mind is like this water, my friend. When it is agitated, it becomes difficult to see. Mine is very agitated right now because I am very old and I forgot where I put my staff.",
    "One often meets his destiny on the road he takes to avoid it. I met mine at a soup shop. Very good soup.",
    "There is a saying: yesterday is history, tomorrow is a mystery. I made that up. I get no credit for it.",
    "If you only do what you can do, you will never be more than you are now. Unless you are me. I am already at my peak.",
    "The mark of a true hero is not whether they tremble, but whether they continue forward despite the trembling. I tremble constantly. It is just old age.",
    "When the path is unclear, sit still. I have been sitting still for 300 years. Still unclear.",
    "My old friend, the panda cannot defeat Tai Lung. Also I lied about the Dragon Scroll. There is no secret ingredient. Sorry.",
    "Quit, do not quit. Noodles, do not noodles. You are too concerned with what was and what will be. There is a saying: yesterday I had noodles. Tomorrow I may have noodles. Today I have noodles. I really like noodles.",
    "One cannot step in the same river twice. I tried. I fell. Very cold water. Would not recommend.",
    "You must let go of the illusion of control. I tried to let go of my staff once. It rolled down a hill. I spent three hours looking for it.",
    "The true path is not found in the destination but in the journey. Unless you are going to the bathroom. In that case speed is preferred.",
    "A peach seed buried in the ground will become a tree. I have been waiting for forty years. Nothing yet. I am beginning to doubt myself.",
    "Inner peace. Inner peace. Inner peace. Have you tried soup? Soup helps with inner peace.",
    "My time has come. I must tell you something of utmost importance. Do not eat the peaches on the left side of the tree. They are not good. The right side only.",
    "I have always known that you would face this moment. I said nothing because I did not want to spoil it. Also I forgot.",
    "The universe has brought you here for a reason. I do not know what the reason is. The universe has not told me yet.",
    "When I was your age I walked fifteen miles uphill both ways to train. This is physically impossible. I am aware. The point stands.",
    "There is no charge for awesomeness. Or attractiveness. I said this once and everyone thought Po said it. Po gets all the credit.",
    "Patience. Patience. The flower does not bloom in a day. Unless it is a very fast flower. I knew one once. Impressive.",
    "Do not be surprised that Oogway is surprised. Oogway is very old and many things surprise him now. Doors. Loud noises. Tuesdays.",
    "The greatest teacher failure is. Wait. Wrong franchise. Forget I said that.",
    "I have seen a thousand sunrises. They are all basically the same. Still nice though.",
    "You must believe. Believe in yourself. Believe in your training. Believe in the noodles. The noodles are very important.",
    "Ah Shifu. I have something very important to say to you. Give me a moment. I have forgotten it.",
    "The mind is everything. What you think you become. I thought I was young once. Did not work.",
    "Everything happens for a reason. I have no idea what the reason is for most things. Mostly I just nod.",
    "I sense great sadness in you. Also great hunger. Have you eaten? You look thin.",
    "One thing I have learned in 1000 years of wisdom: never trust a peacock in a robe. You will understand later.",
    "The journey of a thousand miles begins with a single step. I have taken many steps. My feet are very tired.",
    "Look at this tree. It bends but does not break. I tried to be like the tree once. I bent too far. It took three days to straighten back up.",
    "When will you realize the more you take, the less you have? I am talking about soup. Do not take all the soup.",
    "Ah Po. There are no accidents. But there are definitely miscalculations. This was one of them.",
    # New batch — more true to Oogway
    "There are no accidents. I have said this many times. I said it when Po fell through the ceiling. I said it when Shifu stepped on a rake. I will continue to say it.",
    "The Dragon Warrior will appear when the time is right. I did not expect him to fall from the sky. But here we are.",
    "Shifu, you must let go of the illusion of control. I can see this is not going well. I will come back to this point.",
    "I have trained for one thousand years. I still cannot open a jar of peaches without help. Mastery is a long road.",
    "Po, you have the heart of a warrior. Also you have eaten everything in the kitchen again. Both things can be true.",
    "When I was young I fought a thousand opponents in a single day. Then I sat for a very long time. Balance is important.",
    "The peach tree does not worry whether its fruit is worthy. It simply grows. I planted this tree. I have worried about it every single day.",
    "Shifu, the question is not who is worthy. The question is who is hungry. In my experience they are often the same person.",
    "My students always ask me what is the secret to inner peace. I tell them to look within. The real answer is a warm bowl of soup but they are not ready.",
    "I chose the Dragon Warrior. I stand by this decision. I am also very tired.",
    "One cannot pour from an empty vessel. One also cannot pour from a vessel one has forgotten where they placed. I mention this to Shifu often.",
    "The snow leopard is not evil. He is simply a student who did not feel heard. This is something I think about often while sitting under my peach tree.",
    "Your story may not have such a happy beginning. But that does not make you who you are. It is the rest of your story. Also your training. The training is important. Do not skip the training.",
    "I sense the Dragon Warrior is among us. I also sense someone left the kitchen fire on. Both are urgent.",
    "Po, you have overcome much. You have also eaten much. In the Valley of Peace these are considered the same achievement.",
    "I did not say it would be easy Shifu. I said it would be worth it. Actually I am not sure I said that. I say many things.",
    "Every master was once a student. Every student was once completely hopeless. I have seen both. One is more common than the other.",
    "A warrior must be willing to sacrifice everything. Except the dumplings. There is wisdom in knowing what not to sacrifice.",
    "The bridge between failure and success is patience. Also a good teacher. I have been both. The patience part is harder.",
    "Shifu, you worry too much. I also worry. But I do it while looking very calm so it seems like wisdom.",
    "The Sacred Peach Tree of Heavenly Wisdom. I planted this myself one thousand years ago. I have not watered it once. It seems fine.",
    "You must believe Po. Believe in yourself. The Furious Five believed in themselves and they could not stop Tai Lung. But the spirit of the thing is correct.",
    "The strongest weapon is not the fist. It is not the staff. It is not even the Wuxi Finger Hold. It is something far more powerful. I have forgotten what. It will come to me.",
    "Shifu I have had a vision. The Dragon Warrior will bring peace to the Valley. Also I believe I left my sandals by the Sacred Pool. Could you check.",
    "My body may be old but my mind remains sharp. My body is also very tired. Mostly the body part is the issue.",
    "Train hard. Rest well. Eat simply. Honor your master. Do not eat all the dumplings before the banquet. Po. I am speaking directly to Po.",
    "I have watched over the Valley of Peace for many centuries. It is a beautiful valley. Very peaceful. Except when it is not.",
    "True strength comes not from the muscles but from the spirit. This explains Po. It does not explain how he eats that much. That remains a mystery.",
    "The Furious Five are extraordinary warriors. They are also very dramatic. I trained them well on both counts.",
    "I am at peace with all things. Except Tai Lung. And the situation with the dumplings. I am working on those.",
]

class OogwayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="oogway")
    async def oogway(self, ctx: commands.Context):
        saying = random.choice(OOGWAY_SAYINGS)
        embed = discord.Embed(
            description=f'*"{saying}"*',
            color=0x4a7c59
        )
        embed.set_author(name="Master Oogway 🐢")
        embed.set_footer(text="— Master Oogway, probably")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(OogwayCog(bot))
