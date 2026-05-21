# MasteryBot

A Telegram bot that teaches finance, consulting, VC, PE, and investing from the
ground up. Atoms first (every individual line item, ratio, and formula), then
connections, then frameworks, then real-world application.

Every concept is generated with Claude (`claude-sonnet-4-20250514`) using a
**two-pass system**:

1. **Pass 1 — generate**: a structured lesson is produced with web search
   enabled so it uses real companies and real, recent numbers.
2. **Pass 2 — verify**: a second Claude call extracts every factual claim,
   re-verifies via web search, **independently re-solves every calculation in
   the lesson**, solves the quick-check question itself, flags ambiguity or
   currency-mixing, and returns the corrected final text. Only the verified
   version is sent.

## Project layout

```
mastery-bot/
├── bot.py              # Telegram bot + scheduler + command handlers
├── curriculum.py       # All subjects, modules, concepts (107 total)
├── content_engine.py   # Claude API: generation + verification + Q&A
├── spaced_repetition.py
├── assessment.py       # /review, /test, scoring, level adjustment
├── database.py         # SQLite schema + async queries
├── config.py
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env:
#   MASTERY_BOT_TOKEN=...      (from @BotFather)
#   ANTHROPIC_API_KEY=...      (from console.anthropic.com)
#   MASTERY_CHAT_ID=...        (your Telegram chat id; get via @userinfobot)

python bot.py
```

The first run will create `mastery.db` (SQLite) and seed the full 107-concept
curriculum as `not_started`.

## Curriculum

- **P&L**: 17 line items + 8 ratios
- **Balance Sheet**: 23 line items + 10 ratios
- **Cash Flow Statement**: 10 line items + 4 ratios
- **SaaS Metrics**: 11 concepts
- **Consulting Frameworks**: 8 templates with how-to-think guidance
- **Valuation**: 12 concepts (EV, multiples, DCF, WACC, TV, sensitivity)
- **Private Equity**: 9 concepts (LBO, returns, exits, case studies)
- **Venture Capital**: 9 concepts (cap tables, term sheets, portfolio math)

**Total: 121 concepts.** (Note: the original spec's example map listed 107, but
its own per-subject breakdown sums to 121. Every concept from the spec is
included verbatim.)

## Commands

- `/start` / `/help` — list everything
- `/next` — next concept in your current subject
- `/goto [subject]` — switch subject (`pnl`, `balance`, `cashflow`, `saas`,
  `consulting`, `valuation`, `pe`, `vc`)
- `/concept [name]` — explain any concept on demand (e.g. `/concept WACC`)
- `/formula [name]` — formula + worked example
- `/example [concept]` — another real-world example
- `/map` — full curriculum map with progress (pinnable)
- `/progress` — quick stats
- `/skip` — mark next concept as already known
- `/review` — 5 quick-fire questions
- `/test` — full 10-question assessment (scored)
- `/weak` — reinforce your weakest area
- `/score` — your average score per subject

**Reply to any of the bot's messages with a question to clarify** — a
follow-up handler will answer with a new example or analogy.

## Scheduled (Asia/Kolkata)

- **08:30 IST** — morning concept
- **19:30 IST** — evening concept
- **12:00 IST** — daily spaced-repetition surfacing of one due concept
- **Sunday 10:00 IST** — weekly assessment
- **1st of month 10:00 IST** — monthly report

## Spaced repetition

After a concept is introduced it is re-surfaced on a ladder: 1 → 3 → 7 → 14 →
30 days. Each re-surfacing applies the concept to a **new real example** and
includes a quick application question. A wrong answer resets the interval; a
correct one extends it.

## Difficulty levels

Each subject has a level 1–5, starting at 1. Weekly assessment scores adjust
the level: average ≥ 4.5 promotes, average < 2.5 demotes.

## Notes & assumptions

- One-user bot: `MASTERY_CHAT_ID` is read from `.env` and used for all
  scheduled sends. The bot will respond to commands from any chat, but only
  scheduled sends go to that chat id.
- SQLite is used for simplicity. Schema is in `database.py`.
- All Claude calls go through `_call_claude` in `content_engine.py`, which
  retries once on API failure.
- Web search uses tool spec `web_search_20250305`.
- Messages over 4096 chars are split on newlines.
