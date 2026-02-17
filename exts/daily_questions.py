from datetime import datetime

import discord
from discord.ext import commands, tasks
import pytz

from config import (
    DAILY_CHANNEL_ID,
    DAILY_POST_HOUR,
    DAILY_POST_MINUTE,
    DAILY_POST_TIMEZONE,
)
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
        timezone = pytz.timezone(DAILY_POST_TIMEZONE)
        now = datetime.now(pytz.utc)
        now_local = now.astimezone(timezone)
        post_time_local = now_local.replace(
            hour=DAILY_POST_HOUR,
            minute=DAILY_POST_MINUTE,
            second=0,
            microsecond=0,
        )
        post_time = post_time_local.astimezone(pytz.utc)

        if now < post_time:
            return

        today_key = now_local.date()

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
        channel_id = getattr(channel, "id", DAILY_CHANNEL_ID)

        if not channel:
            self.bot.logger.error("Daily question channel not found.")
            return

        try:
            question = await self.sheet_service.fetch_question_for_date(today_key)
        except Exception:
            self.bot.logger.exception(
                "Daily question fetch stage failed "
                "(date=%s, channel_id=%s)",
                today_key,
                channel_id,
            )
            return

        if not question:
            self.bot.logger.warning(
                "No daily question found; skipping "
                "(date=%s, channel_id=%s)",
                today_key,
                channel_id,
            )
            return

        question_number = str(question.get("Number", "?")).strip() or "?"

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

        except Exception:
            self.bot.logger.exception(
                "Daily question embed stage failed "
                "(question_number=%s, date=%s, channel_id=%s)",
                question_number,
                today_key,
                channel_id,
            )
            return

        try:
            async with self.bot.pool.acquire() as conn:
                claimed_today = await conn.fetchval(
                    """
                    INSERT INTO daily_question_posts (date, posted_at, channel_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (date) DO NOTHING
                    RETURNING 1
                    """,
                    today_key,
                    posted_at,
                    channel_id,
                )

            if not claimed_today:
                self.bot.logger.info(
                    "Daily question already claimed for posting "
                    "(question_number=%s, date=%s, channel_id=%s)",
                    question_number,
                    today_key,
                    channel_id,
                )
                return

            message = await channel.send(embed=embed)

        except Exception:
            self.bot.logger.exception(
                "Daily question send stage failed "
                "(question_number=%s, date=%s, channel_id=%s)",
                question_number,
                today_key,
                channel_id,
            )

            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    (
                        "DELETE FROM daily_question_posts "
                        "WHERE date = $1 AND message_id IS NULL AND channel_id = $2"
                    ),
                    today_key,
                    channel_id,
                )
            return

        thread_id = None
        try:
            thread = await message.create_thread(
                name=f"Discussion: Question #{question_number}",
                auto_archive_duration=10080,
            )
            thread_id = thread.id
        except Exception:
            self.bot.logger.warning(
                "Daily question thread stage failed; message kept "
                "(question_number=%s, date=%s, channel_id=%s, message_id=%s)",
                question_number,
                today_key,
                channel_id,
                message.id,
                exc_info=True,
            )

        try:
            async with self.bot.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE daily_question_posts
                    SET message_id = $1, thread_id = $2, channel_id = $3, posted_at = $4
                    WHERE date = $5
                    """,
                    message.id,
                    thread_id,
                    channel_id,
                    posted_at,
                    today_key,
                )
        except Exception:
            self.bot.logger.exception(
                "Daily question record stage failed "
                "(question_number=%s, date=%s, channel_id=%s, message_id=%s, thread_id=%s)",
                question_number,
                today_key,
                channel_id,
                message.id,
                thread_id,
            )
            return

        self.bot.logger.info(
            "Posted daily question (question_number=%s, date=%s, channel_id=%s, message_id=%s, thread_id=%s)",
            question_number,
            today_key,
            channel_id,
            message.id,
            thread_id,
        )


async def setup(bot):
    await bot.add_cog(DailyQuestions(bot))
