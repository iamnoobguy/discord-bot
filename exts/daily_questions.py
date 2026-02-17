from datetime import date, datetime, timedelta

import discord
from discord import app_commands
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
    """Automated daily question posting and moderation utilities."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sheet_service = GSheetService()
        self.daily_question.start()

    def cog_unload(self):
        self.daily_question.cancel()

    def _schedule_context(self, now_utc: datetime | None = None) -> tuple[datetime, date, datetime]:
        """Return schedule context as (now_utc, local_day_key, today's scheduled post time in UTC)."""
        now_utc = now_utc or datetime.now(pytz.utc)
        timezone = pytz.timezone(DAILY_POST_TIMEZONE)
        now_local = now_utc.astimezone(timezone)
        post_time_local = now_local.replace(
            hour=DAILY_POST_HOUR,
            minute=DAILY_POST_MINUTE,
            second=0,
            microsecond=0,
        )
        return now_utc, now_local.date(), post_time_local.astimezone(pytz.utc)

    def _next_scheduled_post_utc(self, now_utc: datetime | None = None) -> datetime:
        now_utc, local_day, today_post_utc = self._schedule_context(now_utc)
        if now_utc <= today_post_utc:
            return today_post_utc

        timezone = pytz.timezone(DAILY_POST_TIMEZONE)
        tomorrow_local = datetime.combine(local_day + timedelta(days=1), datetime.min.time())
        tomorrow_local = timezone.localize(tomorrow_local).replace(
            hour=DAILY_POST_HOUR,
            minute=DAILY_POST_MINUTE,
        )
        return tomorrow_local.astimezone(pytz.utc)

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

    async def post_daily_question(self, today_key: date | None = None, posted_at: datetime | None = None):
        now, schedule_day, _ = self._schedule_context()
        today_key = today_key or schedule_day
        posted_at = posted_at or now

        channel = self.bot.get_channel(DAILY_CHANNEL_ID)
        channel_id = getattr(channel, "id", DAILY_CHANNEL_ID)

        if not channel:
            self.bot.logger.error("Daily question channel not found.")
            return False

        try:
            question = await self.sheet_service.fetch_question_for_date(today_key)
        except Exception:
            self.bot.logger.exception(
                "Daily question fetch stage failed "
                "(date=%s, channel_id=%s)",
                today_key,
                channel_id,
            )
            return False

        if not question:
            self.bot.logger.warning(
                "No daily question found; skipping "
                "(date=%s, channel_id=%s)",
                today_key,
                channel_id,
            )
            return False

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
            embed.add_field(name="Genre", value=question.get("Genre", "General"), inline=True)
            embed.add_field(name="Difficulty", value=difficulty, inline=True)
            embed.add_field(name="Curator", value=question.get("Curator", "Anonymous"), inline=True)

            hints = "\n".join(
                question.get(f"Hint {i}", "").strip()
                for i in range(1, 4)
                if question.get(f"Hint {i}", "").strip()
            )
            if hints:
                embed.add_field(name="Hints (click to reveal)", value=f"||{hints}||", inline=False)

            embed.set_footer(text="Physics Club Daily Challenge")

        except Exception:
            self.bot.logger.exception(
                "Daily question embed stage failed "
                "(question_number=%s, date=%s, channel_id=%s)",
                question_number,
                today_key,
                channel_id,
            )
            return False

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
                return False

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
            return False

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
            return False

        self.bot.logger.info(
            "Posted daily question (question_number=%s, date=%s, channel_id=%s, message_id=%s, thread_id=%s)",
            question_number,
            today_key,
            channel_id,
            message.id,
            thread_id,
        )
        return True

    @app_commands.command(name="qotd_status", description="Show QOTD posting status and next schedule")
    async def qotd_status(self, interaction: discord.Interaction):
        if interaction.user.id not in getattr(self.bot, "owner_ids", []):
            await interaction.response.send_message("Not authorized.", ephemeral=True)
            return

        now_utc, local_day, post_time_utc = self._schedule_context()
        next_post_utc = self._next_scheduled_post_utc(now_utc)

        async with self.bot.pool.acquire() as conn:
            latest = await conn.fetchrow(
                """
                SELECT date, posted_at, message_id, thread_id, channel_id
                FROM daily_question_posts
                ORDER BY date DESC
                LIMIT 1
                """
            )

        embed = discord.Embed(title="QOTD Scheduler Status", color=0x5865F2, timestamp=now_utc)
        embed.add_field(name="Timezone", value=DAILY_POST_TIMEZONE, inline=True)
        embed.add_field(name="Local Day Key", value=str(local_day), inline=True)
        embed.add_field(name="Today's Scheduled UTC", value=post_time_utc.strftime("%Y-%m-%d %H:%M UTC"), inline=False)
        embed.add_field(name="Next Scheduled UTC", value=next_post_utc.strftime("%Y-%m-%d %H:%M UTC"), inline=False)

        if latest:
            embed.add_field(
                name="Last Posted",
                value=(
                    f"Date: `{latest['date']}`\n"
                    f"Posted At: `{latest['posted_at']}`\n"
                    f"Message ID: `{latest['message_id']}`\n"
                    f"Thread ID: `{latest['thread_id']}`\n"
                    f"Channel ID: `{latest['channel_id']}`"
                ),
                inline=False,
            )
        else:
            embed.add_field(name="Last Posted", value="No QOTD has been recorded yet.", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="qotd_post_now", description="Manually post QOTD for the schedule day")
    async def qotd_post_now(self, interaction: discord.Interaction):
        if interaction.user.id not in getattr(self.bot, "owner_ids", []):
            await interaction.response.send_message("Not authorized.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        _, day_key, _ = self._schedule_context()

        async with self.bot.pool.acquire() as conn:
            already_posted = await conn.fetchval(
                "SELECT 1 FROM daily_question_posts WHERE date = $1",
                day_key,
            )

        if already_posted:
            await interaction.followup.send(f"QOTD for `{day_key}` is already posted.", ephemeral=True)
            return

        ok = await self.post_daily_question(today_key=day_key)
        if ok:
            await interaction.followup.send(f"Posted QOTD for `{day_key}`.", ephemeral=True)
        else:
            await interaction.followup.send(
                f"Failed to post QOTD for `{day_key}`. Check logs for details.", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(DailyQuestions(bot))
