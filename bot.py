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
from termcolor import colored
from discord.ext import commands

from utils.text_format import spaced_padding, CustomFormatter
from services.xp_service import XPService
from config import DEBUG_MODE, POSTGRES_CONNSTR, DISCORD_TOKEN, OWNER_IDS


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
