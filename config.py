"""Configuration for MasteryBot."""
import os
from dotenv import load_dotenv
import pytz

load_dotenv()

# Credentials
TELEGRAM_TOKEN = os.getenv("MASTERY_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CHAT_ID = os.getenv("MASTERY_CHAT_ID")

# Models — Sonnet only for Pass 1 (quality matters); Haiku for cheaper passes.
CLAUDE_MODEL = "claude-sonnet-4-20250514"            # Pass 1: generation
CLAUDE_MODEL_VERIFY = "claude-haiku-4-5-20251001"    # Pass 2: verification
CLAUDE_MODEL_QA = "claude-haiku-4-5-20251001"        # Reply Q&A + formula/spaced

MAX_TOKENS_GENERATION = 1200
MAX_TOKENS_VERIFICATION = 800
MAX_TOKENS_QA = 800

# Per-million-token pricing (USD). Used by content_engine for /cost tracking.
PRICING = {
    "claude-sonnet-4-20250514":   {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001":  {"input": 1.00, "output":  5.00},
}

# Pause between Pass 1 (generate) and Pass 2 (verify) to avoid burst rate limits.
INTER_PASS_DELAY_SECONDS = 5.0

# Backoff when the API returns 429 (rate limit).
RATE_LIMIT_BACKOFF_SECONDS = 60

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
RETRY_ATTEMPTS = 3

# Difficulty levels per subject (1..5)
DEFAULT_LEVEL = 1
MAX_LEVEL = 5
