from datetime import datetime

import discord
from discord.ext import commands, tasks
import pytz

from config import DAILY_CHANNEL_ID, DAILY_POST_HOUR, DAILY_POST_MINUTE
from services.gsheets_service import GSheetService


DIFFICULTY_COLORS = {
    "Easy": 0x00FF00,
    "Medium": 0xFFBF00,
    "Hard": 0xFF0000,
}


class DailyQuestions(commands.Cog):
    """ """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sheet_service = GSheetService()
        self.daily_question.start()

    def cog_unload(self):
        """ """
        self.daily_question.cancel()

    # Scheduler discord.ext.tasks
    @tasks.loop(minutes=1)
    async def daily_question(self):
        await self.post_daily_question_if_due()

    @daily_question.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()

    async def post_daily_question_if_due(self):
        now = datetime.now(pytz.utc)
        post_time = now.replace(
            hour=DAILY_POST_HOUR,
            minute=DAILY_POST_MINUTE,
            second=0,
            microsecond=0,
        )

        if now < post_time:
            return

        today_key = now.date()

        async with self.bot.pool.acquire() as conn:
            already_posted = await conn.fetchval(
                "SELECT 1 FROM daily_question_posts WHERE date = $1",
                today_key,
            )

        if already_posted:
            return

        await self.post_daily_question(today_key=today_key, posted_at=now)

    async def post_daily_question(self, today_key=None, posted_at=None):
        today_key = today_key or datetime.now(pytz.utc).date()
        posted_at = posted_at or datetime.now(pytz.utc)
        channel = self.bot.get_channel(DAILY_CHANNEL_ID)

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
                timestamp=posted_at,
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

            async with self.bot.pool.acquire() as conn:
                claimed_today = await conn.fetchval(
                    """
                    INSERT INTO daily_question_posts (date, posted_at)
                    VALUES ($1, $2)
                    ON CONFLICT (date) DO NOTHING
                    RETURNING 1
                    """,
                    today_key,
                    posted_at,
                )

            if not claimed_today:
                self.bot.logger.info(
                    f"Daily question for {today_key} already posted. Skipping."
                )
                return

            try:
                message = await channel.send(embed=embed)
            except Exception:
                async with self.bot.pool.acquire() as conn:
                    await conn.execute(
                        "DELETE FROM daily_question_posts WHERE date = $1 AND message_id IS NULL",
                        today_key,
                    )
                raise

            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE daily_question_posts
                    SET message_id = $1, channel_id = $2
                    WHERE date = $3
                    """,
                    message.id,
                    channel.id,
                    today_key,
                )

            await message.create_thread(
                name=f"Discussion: Question #{question.get('Number', '?')}",
                auto_archive_duration=10080,
            )

            self.bot.logger.info(f"Posted daily question #{question.get('Number')}")

        except Exception as e:
            self.bot.logger.error(f"Daily post error: {e}")


async def setup(bot):
    await bot.add_cog(DailyQuestions(bot))
