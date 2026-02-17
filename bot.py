import sys
import os
import asyncio
import logging
import datetime
from typing import Optional
from logging.handlers import RotatingFileHandler

import dotenv
import discord
import asyncpg
import jishaku
import pytz
from termcolor import colored
from discord.ext import commands

from utils.text_format import spaced_padding, CustomFormatter
from services.xp_service import XPService
import config as bot_config


DEBUG_MODE = bot_config.DEBUG_MODE
POSTGRES_CONNSTR = bot_config.POSTGRES_CONNSTR
DISCORD_TOKEN = bot_config.DISCORD_TOKEN
OWNER_IDS = bot_config.OWNER_IDS

GOOGLE_CREDENTIALS_PATH = getattr(bot_config, "GOOGLE_CREDENTIALS_PATH", "")
GOOGLE_SHEET_ID = getattr(bot_config, "GOOGLE_SHEET_ID", "")
GOOGLE_SHEET_RANGE = getattr(bot_config, "GOOGLE_SHEET_RANGE", "")
DAILY_CHANNEL_ID = getattr(bot_config, "DAILY_CHANNEL_ID", 0)
DAILY_POST_HOUR = getattr(bot_config, "DAILY_POST_HOUR", None)
DAILY_POST_MINUTE = getattr(bot_config, "DAILY_POST_MINUTE", None)
DAILY_POST_TIMEZONE = getattr(bot_config, "DAILY_POST_TIMEZONE", "UTC")


INITIAL_EXTENSIONS = [
    "jishaku",
    #
    "exts.dev",
    "exts.info",
    "exts.levels",
    "exts.latex",
    #
    "exts.daily_questions",
]


class CustomCache:
    """ """
    pass


class BaseBot(commands.AutoShardedBot):
    """Base Class for the bot"""

    def __init__(self, *args, **kwargs):
        intents = discord.Intents.default()
        intents.members = True

        super().__init__(
            command_prefix=commands.when_mentioned_or("-"),
            case_insensitive=True,
            strip_after_prefix=True,
            intents=discord.Intents.all() if DEBUG_MODE else intents,
            owner_ids=OWNER_IDS,
            activity=discord.Activity(
                type=discord.ActivityType.custom,
                state="F = ma ?",
            ),
            *args,
            **kwargs,
        )

        self._time_started = datetime.datetime.now()
        self._codeblock = "```"
        self.pool: asyncpg.Pool
        self.cache = CustomCache()

    async def dispatch_log(
        self,
        payload: Optional[tuple[discord.Embed]],
        files: Optional[tuple[discord.File]] = None,
        view: Optional[discord.ui.View] = None,
    ) -> discord.Message:
        logging_channel = getattr(self, "logging_channel", None)
        if logging_channel is None:
            raise AttributeError("LOGGING_CHANNEL not set")

        if files:
            if payload:
                msg = await logging_channel.send(
                    embeds=list(payload),
                    view=view or discord.ui.View(),
                    files=files,
                )
            else:
                msg = await logging_channel.send(files=files)
        else:
            if not payload:
                raise ValueError("No payload provided")

            msg = await logging_channel.send(
                embeds=list(payload), view=view or discord.ui.View()
            )

        return msg  # type:ignore

    async def setup_hook(self):
        """Set up logger and load extensions"""

        ## ----- Logging ----- ##

        fmt = "[{asctime}] [{levelname}] - {name}: {message}"
        date_fmt = "%H:%M:%S"

        # Setup loggers
        ## discord.py logger
        dpy_logger = logging.getLogger("discord")
        dpy_logger.setLevel(logging.INFO)

        ## bot logger
        bot_logger = logging.getLogger("bot")
        bot_logger.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)

        # Log to file
        f_formatter = logging.Formatter(fmt, date_fmt, "{")

        file_handler = RotatingFileHandler(
            "./logs/bot.log",
            mode="w",
            encoding="utf-8",
            maxBytes=5 * 1024 * 1024,
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(f_formatter)

        # Log to console
        c_formatter = CustomFormatter(fmt, date_fmt, "{")

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(c_formatter)

        # Add & Finish up
        for _logger in [dpy_logger, bot_logger]:
            _logger.propagate = False

            _logger.addHandler(console_handler)
            _logger.addHandler(file_handler)

        self.logger = bot_logger

        await self.validate_startup_config()

        ## -------- Run Schema -------- ##

        with open("./sql/schema.sql", "r", encoding="utf-8") as f:
            schema = f.read()

            await self.pool.execute(schema)
            self.logger.info("Database schema initialized.")

        self.xp_service = XPService(self.pool)

        ## ------ Load Extensions ----- ##

        loaded_exts = []
        for ext in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(ext)
            except commands.ExtensionError as exc:
                print(colored(f"Failed to load extension {ext}: {exc}", "red"))
            else:
                loaded_exts.append(ext)

        print(
            colored(
                spaced_padding("Inital Extensions", 52)
                + "\n| + "
                + "\n| + ".join(loaded_exts)
                + "\n",
                "light_blue",
                attrs=["bold"],
            )
        )

    async def validate_startup_config(self):
        """Validate required startup configuration before loading extensions."""

        errors: list[str] = []
        warnings: list[str] = []

        credentials_path = str(GOOGLE_CREDENTIALS_PATH).strip()
        if not credentials_path:
            errors.append(
                "GOOGLE_CREDENTIALS_PATH is not set. Set it in your .env/config to the service-account JSON file."
            )
        elif not os.path.isfile(credentials_path):
            errors.append(
                f"GOOGLE_CREDENTIALS_PATH points to a missing file: '{credentials_path}'."
            )
        elif not os.access(credentials_path, os.R_OK):
            errors.append(
                f"GOOGLE_CREDENTIALS_PATH is not readable: '{credentials_path}'."
            )

        sheet_id = str(GOOGLE_SHEET_ID).strip()
        if not sheet_id or sheet_id == "your_sheet_id_here":
            errors.append(
                "GOOGLE_SHEET_ID is empty or still set to placeholder 'your_sheet_id_here'."
            )

        sheet_range = str(GOOGLE_SHEET_RANGE).strip()
        if not sheet_range:
            errors.append("GOOGLE_SHEET_RANGE is empty. Example: 'Sheet1!A1:O'.")

        if not isinstance(DAILY_CHANNEL_ID, int) or DAILY_CHANNEL_ID <= 0:
            errors.append(
                "DAILY_CHANNEL_ID must be a valid Discord snowflake integer (> 0)."
            )

        if not isinstance(DAILY_POST_HOUR, int) or not (0 <= DAILY_POST_HOUR <= 23):
            errors.append("DAILY_POST_HOUR must be an integer between 0 and 23.")

        if not isinstance(DAILY_POST_MINUTE, int) or not (0 <= DAILY_POST_MINUTE <= 59):
            errors.append("DAILY_POST_MINUTE must be an integer between 0 and 59.")

        timezone_name = str(DAILY_POST_TIMEZONE).strip()
        if not timezone_name:
            errors.append("DAILY_POST_TIMEZONE is empty. Example: 'UTC' or 'Asia/Kolkata'.")
        else:
            try:
                pytz.timezone(timezone_name)
            except pytz.UnknownTimeZoneError:
                errors.append(
                    f"DAILY_POST_TIMEZONE '{timezone_name}' is invalid. Use an IANA timezone name like 'UTC' or 'America/New_York'."
                )

        if not errors and isinstance(DAILY_CHANNEL_ID, int) and DAILY_CHANNEL_ID > 0:
            try:
                channel = await self.fetch_channel(DAILY_CHANNEL_ID)
            except discord.NotFound:
                errors.append(
                    f"DAILY_CHANNEL_ID {DAILY_CHANNEL_ID} does not exist or is not accessible to the bot."
                )
            except discord.Forbidden:
                errors.append(
                    f"Bot cannot access DAILY_CHANNEL_ID {DAILY_CHANNEL_ID}. Check bot guild membership and channel visibility permissions."
                )
            except discord.HTTPException as exc:
                errors.append(
                    f"Failed to fetch DAILY_CHANNEL_ID {DAILY_CHANNEL_ID} due to Discord API error: {exc}."
                )
            else:
                guild = getattr(channel, "guild", None)
                me = getattr(guild, "me", None) if guild else None
                if guild is None or me is None:
                    warnings.append(
                        "Could not fully verify channel permissions because guild/member cache is unavailable during startup."
                    )
                else:
                    perms = channel.permissions_for(me)
                    if not perms.send_messages:
                        errors.append(
                            f"Bot lacks 'Send Messages' in channel #{channel} ({channel.id})."
                        )

                    if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                        if not perms.create_public_threads:
                            errors.append(
                                f"Bot lacks 'Create Public Threads' in channel #{channel} ({channel.id})."
                            )
                    else:
                        warnings.append(
                            f"Skipped thread permission check for unsupported channel type: {type(channel).__name__}."
                        )

        if warnings:
            for warning in warnings:
                self.logger.warning("Config validation warning: %s", warning)

        if errors:
            msg = "Startup configuration validation failed:\n- " + "\n- ".join(errors)
            self.logger.error(msg)
            raise RuntimeError(msg)

        self.logger.info("Startup configuration validation passed.")

    async def close(self):
        try:
            ...
            # await self.pool.close()
        except AttributeError:
            pass

        await super().close()

    async def on_ready(self):
        """Called when the bot is ready"""

        bot_id = self.user.id if self.user else "---"

        self.basic_info: list[str] = [
            f"{tag:<12}: {value}"
            for tag, value in {
                "User": self.user,
                "ID": bot_id,
                "Python": sys.version,
                "Discord.py": discord.__version__,
                "Jishaku": jishaku.__version__,
                "Guilds": len(self.guilds),
                "Shards": self.shard_count,
                "Debug Mode": DEBUG_MODE,
            }.items()
        ]
        print(
            colored(
                "\n"
                + spaced_padding("Logged In", 52)
                + "\n| > "
                + "\n| > ".join(self.basic_info)
                + "\n",
                "cyan",
                attrs=["bold"],
            )
        )

    async def start(self) -> None:
        await super().start(
            token=DISCORD_TOKEN,
            reconnect=True,
        )


async def main():
    dotenv.load_dotenv()

    if not os.path.exists("./logs"):
        os.mkdir("./logs")

    # check if config.py exists and .env exists, if not create it
    if not os.path.exists("./config.py"):
        with open("./config.py", "w") as f:
            f.write("")

        raise ValueError(
            "A config.py and file was created. Please edit them and restart the bot."
        )
        # exit the loop and the program

    async with (
        BaseBot() as bot,
        asyncpg.create_pool(
            dsn=POSTGRES_CONNSTR,
            command_timeout=60,
            max_inactive_connection_lifetime=0,
        ) as pool,
    ):
        bot.pool = pool

        try:
            await bot.start()
        except KeyboardInterrupt:
            await bot.close()
        finally:
            await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
