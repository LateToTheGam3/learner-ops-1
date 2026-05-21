"""Configuration for MasteryBot."""
import os
from dotenv import load_dotenv
import pytz

load_dotenv()

# Credentials
TELEGRAM_TOKEN = os.getenv("MASTERY_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CHAT_ID = os.getenv("MASTERY_CHAT_ID")

# Model
CLAUDE_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS_GENERATION = 2000
MAX_TOKENS_VERIFICATION = 3000
MAX_TOKENS_QA = 800

# Web search tool spec
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 5,
}

# Timezone
TZ = pytz.timezone("Asia/Kolkata")

# Schedule (IST)
MORNING_HOUR, MORNING_MIN = 8, 30
EVENING_HOUR, EVENING_MIN = 19, 30
WEEKLY_ASSESS_DAY, WEEKLY_ASSESS_HOUR = "sun", 10
MONTHLY_REPORT_DAY, MONTHLY_REPORT_HOUR = 1, 10
SPACED_REPETITION_HOUR = 12  # daily noon check

# Telegram message limit
TG_MAX_MSG_LEN = 4096

# Spaced repetition intervals (days)
SR_INTERVALS = [1, 3, 7, 14, 30]

# Database
DB_PATH = os.path.join(os.path.dirname(__file__), "mastery.db")

# Retry policy
RETRY_ATTEMPTS = 2

# Difficulty levels per subject (1..5)
DEFAULT_LEVEL = 1
MAX_LEVEL = 5
