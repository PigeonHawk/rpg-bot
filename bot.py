import discord
from discord.ext import commands
import json
import os
import asyncio
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = "!"
GUILD_ID = None                  # Set to your server ID (int) to restrict commands, or leave None

# ── Bot setup ─────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# ── Load cogs ─────────────────────────────────────────────────────────────────
async def main():
    async with bot:
        await bot.load_extension("cogs.tt")
        await bot.load_extension("cogs.chud")
        await bot.load_extension("cogs.hamtaro")
        await bot.load_extension("cogs.movies")
        await bot.load_extension("cogs.oogway")
        await bot.load_extension("cogs.omen")
        await bot.start(TOKEN)

@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online and ready!")

if __name__ == "__main__":
    asyncio.run(main())
