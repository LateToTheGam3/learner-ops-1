"""Configuration for MasteryBot."""
import os
from dotenv import load_dotenv
import pytz

load_dotenv()

# Credentials
TELEGRAM_TOKEN = os.getenv("MASTERY_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CHAT_ID = os.getenv("MASTERY_CHAT_ID")

# Models
CLAUDE_MODEL       = "claude-sonnet-4-20250514"    # generation for level 3+ concepts
CLAUDE_MODEL_FAST  = "claude-haiku-4-5-20251001"   # generation for level 1-2 concepts (cheaper)
CLAUDE_MODEL_VERIFY = "claude-haiku-4-5-20251001"  # Pass 2: verification
CLAUDE_MODEL_QA    = "claude-haiku-4-5-20251001"   # Reply Q&A + formula/spaced

# Concepts at this level or below use CLAUDE_MODEL_FAST for generation.
# Raise to 0 to always use Sonnet; set to 5 to always use Haiku.
FAST_MODEL_MAX_LEVEL = 2

MAX_TOKENS_GENERATION = 2000
MAX_TOKENS_VERIFICATION = 2000
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
# max_uses=2: each search returns ~3-5 k tokens of context that counts as input.
# 5 searches was the single biggest cost driver (~$0.10-0.15 per call in input alone).
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 2,
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
