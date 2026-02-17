import sys
import types
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytz


# Minimal config for import-time constants.
if "config" not in sys.modules:
    config = types.ModuleType("config")
    config.DAILY_CHANNEL_ID = 12345
    config.DAILY_POST_HOUR = 9
    config.DAILY_POST_MINUTE = 0
    config.DAILY_POST_TIMEZONE = "UTC"
    config.GOOGLE_CREDENTIALS_PATH = "/tmp/fake.json"
    config.GOOGLE_API_SCOPES = ["scope"]
    config.GOOGLE_SHEET_ID = "sheet-id"
    config.GOOGLE_SHEET_RANGE = "Sheet1!A:Z"
    sys.modules["config"] = config

# Minimal google stubs because exts.daily_questions imports GSheetService.
if "googleapiclient.discovery" not in sys.modules:
    discovery = types.ModuleType("googleapiclient.discovery")
    discovery.build = lambda *args, **kwargs: object()
    googleapiclient = types.ModuleType("googleapiclient")
    googleapiclient.discovery = discovery
    sys.modules["googleapiclient"] = googleapiclient
    sys.modules["googleapiclient.discovery"] = discovery

if "google.oauth2.service_account" not in sys.modules:
    service_account = types.ModuleType("google.oauth2.service_account")

    class _Credentials:
        @staticmethod
        def from_service_account_file(*args, **kwargs):
            return object()

    service_account.Credentials = _Credentials
    oauth2 = types.ModuleType("google.oauth2")
    oauth2.service_account = service_account
    google = types.ModuleType("google")
    google.oauth2 = oauth2
    sys.modules["google"] = google
    sys.modules["google.oauth2"] = oauth2
    sys.modules["google.oauth2.service_account"] = service_account

# Minimal discord stubs.
if "discord" not in sys.modules:
    discord = types.ModuleType("discord")

    class Embed:
        def __init__(self, title=None, description=None, color=None, timestamp=None):
            self.title = title
            self.description = description
            self.color = color
            self.timestamp = timestamp
            self.fields = []
            self.footer = None

        def add_field(self, name, value, inline=True):
            self.fields.append((name, value, inline))

        def set_footer(self, text):
            self.footer = text

    discord.Embed = Embed
    class Interaction:
        def __init__(self):
            self.user = None
            self.response = None
            self.followup = None
    discord.Interaction = Interaction

    app_commands = types.ModuleType("discord.app_commands")
    app_commands.command = lambda *a, **k: (lambda f: f)
    discord.app_commands = app_commands

    ext = types.ModuleType("discord.ext")
    commands = types.ModuleType("discord.ext.commands")
    tasks = types.ModuleType("discord.ext.tasks")

    class Bot:
        pass

    class Cog:
        pass

    def loop(*args, **kwargs):
        def deco(fn):
            fn.start = lambda *a, **k: None
            fn.cancel = lambda *a, **k: None
            fn.before_loop = lambda inner: inner
            return fn

        return deco

    commands.Bot = Bot
    commands.Cog = Cog
    tasks.loop = loop
    ext.commands = commands
    ext.tasks = tasks
    discord.ext = ext

    sys.modules["discord"] = discord
    sys.modules["discord.ext"] = ext
    sys.modules["discord.ext.commands"] = commands
    sys.modules["discord.ext.tasks"] = tasks

from exts.daily_questions import DailyQuestions


class _AcquireCtx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Pool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _AcquireCtx(self._conn)


class _FixedDateTime:
    fixed_now = datetime(2025, 1, 1, 9, 5, tzinfo=pytz.utc)

    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return cls.fixed_now.astimezone(tz)
        return cls.fixed_now


class DailyQuestionTests(unittest.IsolatedAsyncioTestCase):
    def _make_cog(self, conn=None, channel=None):
        bot = Mock()
        bot.logger = Mock()
        bot.pool = _Pool(conn or Mock())
        bot.get_channel.return_value = channel

        cog = DailyQuestions.__new__(DailyQuestions)
        cog.bot = bot
        cog.sheet_service = Mock()
        cog.sheet_service.fetch_question_for_date = AsyncMock(return_value=None)
        return cog


    def test_next_scheduled_post_rolls_to_next_day_after_cutoff(self):
        cog = self._make_cog()
        with patch("exts.daily_questions.DAILY_POST_TIMEZONE", "UTC"):
            after_cutoff = datetime(2025, 1, 1, 10, 0, tzinfo=pytz.utc)
            next_post = cog._next_scheduled_post_utc(after_cutoff)

        self.assertEqual(datetime(2025, 1, 2, 9, 0, tzinfo=pytz.utc), next_post)

    def test_schedule_context_uses_configured_timezone_day_key(self):
        cog = self._make_cog()
        with patch("exts.daily_questions.DAILY_POST_TIMEZONE", "Asia/Kolkata"):
            now = datetime(2025, 1, 1, 18, 40, tzinfo=pytz.utc)
            _, local_day, _ = cog._schedule_context(now)

        self.assertEqual(datetime(2025, 1, 2, 0, 10, tzinfo=pytz.utc).date(), local_day)

    async def test_duplicate_prevention_when_already_posted(self):
        conn = Mock()
        conn.fetchval = AsyncMock(return_value=1)

        cog = self._make_cog(conn=conn)
        cog.post_daily_question = AsyncMock()

        _FixedDateTime.fixed_now = datetime(2025, 1, 1, 9, 0, tzinfo=pytz.utc)
        with patch("exts.daily_questions.datetime", _FixedDateTime):
            await cog.post_daily_question_if_due()

        cog.post_daily_question.assert_not_awaited()

    async def test_restart_after_scheduled_minute_late_post(self):
        conn = Mock()
        conn.fetchval = AsyncMock(return_value=None)

        cog = self._make_cog(conn=conn)
        cog.post_daily_question = AsyncMock()

        _FixedDateTime.fixed_now = datetime(2025, 1, 1, 9, 17, tzinfo=pytz.utc)
        with patch("exts.daily_questions.datetime", _FixedDateTime):
            await cog.post_daily_question_if_due()

        cog.post_daily_question.assert_awaited_once()
        kwargs = cog.post_daily_question.await_args.kwargs
        self.assertEqual(_FixedDateTime.fixed_now.date(), kwargs["today_key"])
        self.assertEqual(_FixedDateTime.fixed_now, kwargs["posted_at"])

    async def test_uses_local_timezone_day_key_for_fetch(self):
        conn = Mock()
        conn.fetchval = AsyncMock(return_value=None)
        conn.execute = AsyncMock()

        thread = Mock(id=456)
        message = Mock(id=123)
        message.create_thread = AsyncMock(return_value=thread)

        channel = Mock()
        channel.id = 12345
        channel.send = AsyncMock(return_value=message)

        cog = self._make_cog(conn=conn, channel=channel)
        cog.sheet_service.fetch_question_for_date = AsyncMock(
            return_value={
                "Number": "7",
                "Difficulty": "Easy",
                "Problem Statement": "Local day test",
                "Genre": "Thermo",
                "Curator": "Tester",
            }
        )

        with patch("exts.daily_questions.DAILY_POST_TIMEZONE", "Asia/Kolkata"):
            _FixedDateTime.fixed_now = datetime(2025, 1, 2, 3, 31, tzinfo=pytz.utc)
            with patch("exts.daily_questions.datetime", _FixedDateTime):
                await cog.post_daily_question_if_due()

        expected_local_day = datetime(2025, 1, 2, 9, 1, tzinfo=pytz.utc).date()
        self.assertEqual(expected_local_day, conn.fetchval.await_args.args[1])
        cog.sheet_service.fetch_question_for_date.assert_awaited_once_with(expected_local_day)

    async def test_no_question_day_skips_send(self):
        conn = Mock()
        conn.fetchval = AsyncMock()
        conn.execute = AsyncMock()

        channel = Mock()
        channel.id = 12345
        channel.send = AsyncMock()

        cog = self._make_cog(conn=conn, channel=channel)
        cog.sheet_service.fetch_question_for_date = AsyncMock(return_value=None)

        await cog.post_daily_question(
            today_key=datetime(2025, 1, 1, tzinfo=pytz.utc).date(),
            posted_at=datetime(2025, 1, 1, 9, 0, tzinfo=pytz.utc),
        )

        channel.send.assert_not_awaited()
        conn.execute.assert_not_awaited()

    async def test_thread_creation_failure_keeps_message_and_updates_record(self):
        conn = Mock()
        conn.fetchval = AsyncMock(return_value=1)
        conn.execute = AsyncMock()

        thread_error = RuntimeError("thread fail")
        message = Mock(id=888)
        message.create_thread = AsyncMock(side_effect=thread_error)

        channel = Mock()
        channel.id = 12345
        channel.send = AsyncMock(return_value=message)

        cog = self._make_cog(conn=conn, channel=channel)
        cog.sheet_service.fetch_question_for_date = AsyncMock(
            return_value={
                "Number": "42",
                "Difficulty": "Hard",
                "Problem Statement": "Test problem",
                "Genre": "Mechanics",
                "Curator": "Tester",
            }
        )

        posted_at = datetime(2025, 1, 1, 9, 5, tzinfo=pytz.utc)
        today_key = posted_at.date()
        await cog.post_daily_question(today_key=today_key, posted_at=posted_at)

        message.create_thread.assert_awaited_once()
        self.assertEqual(1, conn.execute.await_count)
        update_call = conn.execute.await_args_list[0]
        self.assertEqual(message.id, update_call.args[1])
        self.assertIsNone(update_call.args[2])


if __name__ == "__main__":
    unittest.main()
