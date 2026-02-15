import discord
from discord.ext import commands
from discord import app_commands

from bot import BaseBot


class Information(commands.GroupCog, group_name="info"):
    """ """
    def __init__(self, bot: BaseBot):
        self.bot = bot

    @app_commands.command(name="ping", description="Check bot latency")
    async def ping(self, interaction: discord.Interaction):
        """Responds with the bot's latency."""
        latency_ms = int(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong! Latency: {latency_ms} ms")


async def setup(bot: BaseBot):
    await bot.add_cog(Information(bot))
