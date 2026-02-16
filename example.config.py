import dotenv
import os

dotenv.load_dotenv()

# ===== Discord Config =====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")  # set in .env
DEBUG_MODE = False  # set to True for dev mode
MAIN_GUILD_ID = 000000000000000000 
OWNER_IDS = [000000000000000000]  
SUPER_ADMINS = [000000000000000000] 

# ===== Database Config =====
POSTGRES_CONNSTR = os.getenv("POSTGRES_CONNSTR")  # set in .env

# ===== Google Sheets & API Config =====
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH")  # set in .env
GOOGLE_API_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly"
]  # usually not changed
GOOGLE_SHEET_ID = "your_sheet_id_here"  # Google Sheet ID
GOOGLE_SHEET_RANGE = "Sheet1!A1:O"

# ===== Daily Ques Post Config =====
DAILY_CHANNEL_ID = 000000000000000000  # channel to post daily questions
REVIEW_CHANNEL_ID = 000000000000000000  # channel for review answers
DAILY_POST_HOUR = 9
DAILY_POST_MINUTE = 0 # means 9:00 UTC 

# ===== XP & Leveling Config =====
XP_THRESHOLDS = {
    100: ("Level 1 Title", "Short 1"),
    500: ("Level 2 Title", "Short 2"),
    1000: ("Level 3 Title", "Short 3"),
}  # customize thresholds and titles
