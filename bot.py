import discord
from discord.ext import commands
import json
import os
import asyncio
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN = "MTUwMDY2NTk0NDk0NTU5NDQ2OQ.GdNHqZ.KYVgHfFAJUtAzxYKrpLtPeQsJvmJV0vBUH0K5U"   # Replace with your bot token
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
        await bot.load_extension("cogs.rpg")
        await bot.start(TOKEN)

@bot.event
async def on_ready():
    print(f"✅ {bot.user} is online and ready!")

if __name__ == "__main__":
    asyncio.run(main())
