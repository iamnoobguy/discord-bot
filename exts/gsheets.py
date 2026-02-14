from datetime import datetime

import discord
from discord.ext import commands, tasks
import pytz

import _arch_old._config as _config  # todo: migrate to new config structure
from services.gsheets_service import GSheetService


DIFFICULTY_COLORS = {
    "Easy": 0x00FF00,
    "Medium": 0xFFBF00,
    "Hard": 0xFF0000,
}

class GSheets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sheet_service = GSheetService()
        self.daily_question.start()

    def cog_unload(self):
        self.daily_question.cancel()

    # Scheduler discord.ext.tasks
    @tasks.loop(minutes=1)
    async def daily_question(self):
        now = datetime.now(pytz.utc)

        if now.hour == _config.DAILY_HOUR and now.minute == _config.DAILY_MINUTE:
            await self.post_daily_question()

    @daily_question.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()


    async def post_daily_question(self):
        channel = self.bot.get_channel(_config.CHANNEL_ID)

        if not channel:
            self.bot.logger.error("Daily question channel not found.")
            return

        question = await self.sheet_service.fetch_today_question()
        if not question:
            self.bot.logger.warning("No question today — skipping.")
            return

        try:
            difficulty = question.get("Difficulty", "Medium").strip().title()
            color = DIFFICULTY_COLORS.get(difficulty, 0x3498DB)

            embed = discord.Embed(
                title=f"Daily Physics Question #{question.get('Number', '?')}",
                description=question.get("Problem Statement", "No statement."),
                color=color,
                timestamp=datetime.now(pytz.utc),
            )

            embed.add_field(
                name="Genre",
                value=question.get("Genre", "General"),
                inline=True,
            )

            embed.add_field(
                name="Difficulty",
                value=difficulty,
                inline=True,
            )

            curator = question.get("Curator", "Anonymous")
            embed.add_field(name="Curator", value=curator, inline=True)

            hints = "\n".join(
                question.get(f"Hint {i}", "").strip()
                for i in range(1, 4)
                if question.get(f"Hint {i}", "").strip()
            )

            if hints:
                embed.add_field(
                    name="Hints (click to reveal)",
                    value=f"||{hints}||",
                    inline=False,
                )

            embed.set_footer(text="Physics Club Daily Challenge")

            message = await channel.send(embed=embed)

            await message.create_thread(
                name=f"Discussion: Question #{question.get('Number', '?')}",
                auto_archive_duration=10080,
            )

            self.bot.logger.info(f"Posted daily question #{question.get('Number')}")

        except Exception as e:
            self.bot.logger.error(f"Daily post error: {e}")


async def setup(bot):
    await bot.add_cog(GSheets(bot))
