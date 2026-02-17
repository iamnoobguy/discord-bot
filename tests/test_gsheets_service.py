import sys
import types
import unittest
from datetime import datetime
from unittest.mock import patch

import pytz


# Provide minimal config/google modules for import-time dependencies.
if "config" not in sys.modules:
    config = types.ModuleType("config")
    config.GOOGLE_CREDENTIALS_PATH = "/tmp/fake.json"
    config.GOOGLE_API_SCOPES = ["scope"]
    config.GOOGLE_SHEET_ID = "sheet-id"
    config.GOOGLE_SHEET_RANGE = "Sheet1!A:Z"
    config.DAILY_CHANNEL_ID = 123
    config.DAILY_POST_HOUR = 9
    config.DAILY_POST_MINUTE = 0
    sys.modules["config"] = config

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

from services.gsheets_service import GSheetService


class _FakeSheetsService:
    def __init__(self, values):
        self._values = values

    def spreadsheets(self):
        return self

    def values(self):
        return self

    def get(self, spreadsheetId, range):
        return self

    def execute(self):
        return {"values": self._values}


class _FixedDateTime:
    fixed_now = datetime(2025, 1, 2, 0, 0, tzinfo=pytz.utc)

    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return cls.fixed_now.astimezone(tz)
        return cls.fixed_now


class GSheetServiceTests(unittest.TestCase):
    def test_fetch_today_sync_matches_utc_date_at_boundary(self):
        values = [
            ["Date", "Number", "Problem Statement"],
            ["2025-01-01", "1", "old"],
            ["2025-01-02", "2", "current"],
        ]
        svc = GSheetService.__new__(GSheetService)
        svc._service = _FakeSheetsService(values)

        _FixedDateTime.fixed_now = datetime(2025, 1, 2, 0, 1, tzinfo=pytz.utc)
        with patch("services.gsheets_service.datetime", _FixedDateTime):
            row = svc._fetch_today_sync()

        self.assertIsNotNone(row)
        self.assertEqual("2025-01-02", row["Date"])
        self.assertEqual("2", row["Number"])

    def test_fetch_today_sync_returns_none_when_today_missing(self):
        values = [
            ["Date", "Number"],
            ["2025-01-01", "1"],
        ]
        svc = GSheetService.__new__(GSheetService)
        svc._service = _FakeSheetsService(values)

        _FixedDateTime.fixed_now = datetime(2025, 1, 2, 13, 0, tzinfo=pytz.utc)
        with patch("services.gsheets_service.datetime", _FixedDateTime):
            row = svc._fetch_today_sync()

        self.assertIsNone(row)


if __name__ == "__main__":
    unittest.main()
