# Discord Bot for Physics Club Discord Server

QOTD-focused Discord bot for daily physics challenges with automated posting, thread creation, and resilient posting records.

## What is implemented
- Automated daily question posting from Google Sheets.
- Duplicate-post prevention via `daily_question_posts` table.
- Automatic discussion thread creation for each posted question.
- Timezone-aware scheduling using `DAILY_POST_TIMEZONE`.
- Owner-only admin slash commands:
  - `/qotd_status`: inspect scheduler timing and the last posted QOTD record.
  - `/qotd_post_now`: manually trigger today’s scheduled QOTD if it hasn’t been posted.

## Setup
1. Copy `example.config.py` to `config.py` and fill out all IDs and credentials.
2. Set environment variables listed in `example.env`.
3. Install dependencies:
   - `pip install -r requirements.txt`
4. Start the bot:
   - `python bot.py`

## TODO
- [ ] refactor config handling to the new structure
- [x] implement proper time tracking for daily questions
