import asyncio
import logging
from datetime import datetime
import pytz

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

import _arch_old._config as _config  # todo: migrate to new config structure


logger = logging.getLogger("bot")


class GSheetService:
    def __init__(self):
        self._service = self._build_service()

    def _build_service(self):
        creds = Credentials.from_service_account_file(
            _config.GOOGLE_CREDENTIALS_PATH,
            scopes=_config.API_SCOPES,
        )
        logger.info("Google Sheets service initialized.")
        return build("sheets", "v4", credentials=creds)

    #
    # PUBLIC METHOD (ASYNC SAFE)
    #
    async def fetch_today_question(self) -> dict | None:
        return await asyncio.to_thread(self._fetch_today_sync)

    #
    # INTERNAL SYNC LOGIC (runs in thread)
    #
    def _fetch_today_sync(self) -> dict | None:
        try:
            range_name = f"{_config.SHEET_TAB}!A1:O"

            result = (
                self._service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=_config.SHEET_ID,
                    range=range_name,
                )
                .execute()
            )

            values = result.get("values", [])
            if not values:
                logger.warning("Sheet empty.")
                return None

            headers = values[0]
            today_str = datetime.now(pytz.utc).strftime("%Y-%m-%d")

            for row in values[1:]:
                if len(row) < len(headers):
                    row += [""] * (len(headers) - len(row))

                row_dict = dict(zip(headers, row))

                if row_dict.get("Date", "").strip() == today_str:
                    logger.info(
                        f"Found question #{row_dict.get('Number', '?')} for {today_str}"
                    )
                    return row_dict

            logger.warning(f"No question found for {today_str}")
            return None

        except Exception as e:
            logger.error(f"Sheet fetch error: {e}")
            return None
