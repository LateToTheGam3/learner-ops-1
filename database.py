"""SQLite schema + queries for MasteryBot. Async via aiosqlite."""
import aiosqlite
import hashlib
import datetime as dt
from typing import Optional, List, Dict, Any
import config


SCHEMA = """
CREATE TABLE IF NOT EXISTS curriculum_progress (
    subject_id TEXT NOT NULL,
    module_id  TEXT NOT NULL,
    concept_id TEXT PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'not_started',
    introduced_at TEXT,
    last_reviewed TEXT,
    next_review_due TEXT
);

CREATE TABLE IF NOT EXISTS content_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    subject_id TEXT,
    concept_id TEXT,
    content_text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    math_verified INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS verification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER NOT NULL,
    claims_total INTEGER DEFAULT 0,
    claims_verified INTEGER DEFAULT 0,
    claims_flagged INTEGER DEFAULT 0,
    math_errors_found INTEGER DEFAULT 0,
    flagged_details TEXT,
    FOREIGN KEY (content_id) REFERENCES content_log(id)
);

CREATE TABLE IF NOT EXISTS assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    question_type TEXT,
    concept_id TEXT,
    score INTEGER,
    feedback TEXT
);

CREATE TABLE IF NOT EXISTS spaced_repetition (
    concept_id TEXT PRIMARY KEY,
    last_sent TEXT,
    interval_days INTEGER NOT NULL DEFAULT 1,
    next_due TEXT,
    consecutive_correct INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS subject_levels (
    subject_id TEXT PRIMARY KEY,
    level INTEGER NOT NULL DEFAULT 1,
    last_updated TEXT
);

CREATE TABLE IF NOT EXISTS engagement (
    content_id INTEGER PRIMARY KEY,
    replied INTEGER DEFAULT 0,
    reply_timestamp TEXT,
    asked_followup INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS qa_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    original_content_id INTEGER,
    question TEXT,
    answer TEXT
);

CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def now_iso() -> str:
    return dt.datetime.now(config.TZ).isoformat()


def today_str() -> str:
    return dt.datetime.now(config.TZ).date().isoformat()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# -----------------------------------------------------------------------------
# Initialization
# -----------------------------------------------------------------------------
async def init_db():
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def seed_curriculum(concepts: List[Dict[str, Any]]):
    """Insert all concepts as not_started if not present."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        for c in concepts:
            await db.execute(
                """INSERT OR IGNORE INTO curriculum_progress
                   (subject_id, module_id, concept_id, state)
                   VALUES (?, ?, ?, 'not_started')""",
                (c["subject"], c["module"], c["id"]),
            )
        await db.commit()


# -----------------------------------------------------------------------------
# Curriculum progress
# -----------------------------------------------------------------------------
async def get_progress(concept_id: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM curriculum_progress WHERE concept_id = ?", (concept_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def set_progress(concept_id: str, state: str):
    from curriculum import get_concept as _gc
    c = _gc(concept_id)
    subject_id = c["subject"] if c else ""
    module_id = c["module"] if c else ""
    now = now_iso()
    async with aiosqlite.connect(config.DB_PATH) as db:
        if state == "introduced":
            await db.execute(
                """INSERT INTO curriculum_progress
                   (concept_id, subject_id, module_id, state, introduced_at, last_reviewed)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(concept_id) DO UPDATE
                   SET state = excluded.state,
                       introduced_at = COALESCE(curriculum_progress.introduced_at,
                                                excluded.introduced_at),
                       last_reviewed = excluded.last_reviewed""",
                (concept_id, subject_id, module_id, state, now, now),
            )
        else:
            await db.execute(
                """INSERT INTO curriculum_progress
                   (concept_id, subject_id, module_id, state, last_reviewed)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(concept_id) DO UPDATE
                   SET state = excluded.state, last_reviewed = excluded.last_reviewed""",
                (concept_id, subject_id, module_id, state, now),
            )
        await db.commit()


async def next_concept_in_subject(subject_id: str) -> Optional[str]:
    """Return concept_id of the next not_started concept in this subject, in order."""
    from curriculum import concepts_in_subject

    rows = concepts_in_subject(subject_id)
    if not rows:
        return None
    rows.sort(key=lambda c: (c["module"], c["order"]))
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute(
            "SELECT concept_id, state FROM curriculum_progress WHERE subject_id = ?",
            (subject_id,),
        ) as cur:
            states = {r[0]: r[1] async for r in cur}
    for c in rows:
        if states.get(c["id"]) in (None, "not_started"):
            return c["id"]
    return None


async def progress_summary() -> Dict[str, Dict[str, int]]:
    """Return per-subject and per-module counts of states."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        out_subject: Dict[str, Dict[str, int]] = {}
        out_module: Dict[str, Dict[str, int]] = {}
        async with db.execute(
            "SELECT subject_id, module_id, state FROM curriculum_progress"
        ) as cur:
            async for row in cur:
                s = out_subject.setdefault(row["subject_id"], {})
                s[row["state"]] = s.get(row["state"], 0) + 1
                m = out_module.setdefault(row["module_id"], {})
                m[row["state"]] = m.get(row["state"], 0) + 1
        return {"subject": out_subject, "module": out_module}


# -----------------------------------------------------------------------------
# Content log
# -----------------------------------------------------------------------------
async def log_content(
    subject_id: Optional[str],
    concept_id: Optional[str],
    text: str,
    verified: bool = False,
    math_verified: bool = False,
) -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO content_log
               (timestamp, subject_id, concept_id, content_text, content_hash,
                verified, math_verified)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                now_iso(),
                subject_id,
                concept_id,
                text,
                content_hash(text),
                int(verified),
                int(math_verified),
            ),
        )
        await db.commit()
        return cur.lastrowid


async def log_verification(
    content_id: int,
    claims_total: int,
    claims_verified: int,
    claims_flagged: int,
    math_errors: int,
    flagged_details: str,
):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO verification_log
               (content_id, claims_total, claims_verified, claims_flagged,
                math_errors_found, flagged_details)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                content_id,
                claims_total,
                claims_verified,
                claims_flagged,
                math_errors,
                flagged_details,
            ),
        )
        await db.commit()


async def get_content(content_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM content_log WHERE id = ?", (content_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def last_content_for_concept(concept_id: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM content_log
               WHERE concept_id = ? ORDER BY id DESC LIMIT 1""",
            (concept_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


# -----------------------------------------------------------------------------
# Engagement / Q&A
# -----------------------------------------------------------------------------
async def mark_replied(content_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO engagement (content_id, replied, reply_timestamp)
               VALUES (?, 1, ?)
               ON CONFLICT(content_id) DO UPDATE
               SET replied = 1, reply_timestamp = excluded.reply_timestamp""",
            (content_id, now_iso()),
        )
        await db.commit()


async def log_qa(original_content_id: Optional[int], question: str, answer: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO qa_log (timestamp, original_content_id, question, answer)
               VALUES (?, ?, ?, ?)""",
            (now_iso(), original_content_id, question, answer),
        )
        await db.commit()


# -----------------------------------------------------------------------------
# Spaced repetition
# -----------------------------------------------------------------------------
async def schedule_spaced(concept_id: str, interval_days: int = 1):
    next_due = (
        dt.datetime.now(config.TZ) + dt.timedelta(days=interval_days)
    ).date().isoformat()
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO spaced_repetition
               (concept_id, last_sent, interval_days, next_due, consecutive_correct)
               VALUES (?, ?, ?, ?, 0)
               ON CONFLICT(concept_id) DO UPDATE
               SET interval_days = excluded.interval_days,
                   next_due = excluded.next_due""",
            (concept_id, now_iso(), interval_days, next_due),
        )
        await db.commit()


async def due_for_spaced() -> List[str]:
    today = today_str()
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute(
            "SELECT concept_id FROM spaced_repetition WHERE next_due <= ?",
            (today,),
        ) as cur:
            return [r[0] async for r in cur]


async def update_spaced(concept_id: str, correct: bool):
    """After a re-surfacing question, extend or reset interval."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM spaced_repetition WHERE concept_id = ?", (concept_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return
        cur_interval = row["interval_days"]
        cur_correct = row["consecutive_correct"]
        if correct:
            ladder = config.SR_INTERVALS
            try:
                idx = ladder.index(cur_interval)
                new_interval = ladder[min(idx + 1, len(ladder) - 1)]
            except ValueError:
                new_interval = ladder[0]
            new_correct = cur_correct + 1
        else:
            new_interval = config.SR_INTERVALS[0]
            new_correct = 0
        next_due = (
            dt.datetime.now(config.TZ) + dt.timedelta(days=new_interval)
        ).date().isoformat()
        await db.execute(
            """UPDATE spaced_repetition
               SET last_sent = ?, interval_days = ?, next_due = ?,
                   consecutive_correct = ?
               WHERE concept_id = ?""",
            (now_iso(), new_interval, next_due, new_correct, concept_id),
        )
        await db.commit()


# -----------------------------------------------------------------------------
# Subject levels
# -----------------------------------------------------------------------------
async def get_level(subject_id: str) -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute(
            "SELECT level FROM subject_levels WHERE subject_id = ?", (subject_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else config.DEFAULT_LEVEL


async def set_level(subject_id: str, level: int):
    level = max(1, min(config.MAX_LEVEL, level))
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO subject_levels (subject_id, level, last_updated)
               VALUES (?, ?, ?)
               ON CONFLICT(subject_id) DO UPDATE
               SET level = excluded.level, last_updated = excluded.last_updated""",
            (subject_id, level, now_iso()),
        )
        await db.commit()


# -----------------------------------------------------------------------------
# Assessments
# -----------------------------------------------------------------------------
async def log_assessment(
    question_type: str, concept_id: str, score: int, feedback: str
):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO assessments (date, question_type, concept_id, score, feedback)
               VALUES (?, ?, ?, ?, ?)""",
            (today_str(), question_type, concept_id, score, feedback),
        )
        await db.commit()


async def assessment_history() -> List[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM assessments ORDER BY date DESC LIMIT 200"
        ) as cur:
            return [dict(r) async for r in cur]


async def average_score_per_subject() -> Dict[str, float]:
    """Join assessments to curriculum_progress to bucket by subject."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT cp.subject_id AS subject_id, a.score AS score
               FROM assessments a
               JOIN curriculum_progress cp ON cp.concept_id = a.concept_id"""
        ) as cur:
            buckets: Dict[str, List[int]] = {}
            async for row in cur:
                if row["score"] is None:
                    continue
                buckets.setdefault(row["subject_id"], []).append(row["score"])
    return {k: sum(v) / len(v) for k, v in buckets.items() if v}


# -----------------------------------------------------------------------------
# Generic key/value state
# -----------------------------------------------------------------------------
async def set_state(key: str, value: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO state (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )
        await db.commit()


async def get_state(key: str) -> Optional[str]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute("SELECT value FROM state WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


# -----------------------------------------------------------------------------
# Streak
# -----------------------------------------------------------------------------
async def update_streak() -> int:
    """Bump streak based on last-active date; return current streak."""
    last_active = await get_state("last_active_date")
    streak_s = await get_state("streak") or "0"
    streak = int(streak_s)
    today = today_str()
    if last_active == today:
        pass
    else:
        if last_active:
            try:
                last = dt.date.fromisoformat(last_active)
                delta = (dt.date.fromisoformat(today) - last).days
                if delta == 1:
                    streak += 1
                elif delta > 1:
                    streak = 1
                else:
                    streak = max(1, streak)
            except ValueError:
                streak = 1
        else:
            streak = 1
        await set_state("last_active_date", today)
        await set_state("streak", str(streak))
    return streak


async def get_streak() -> int:
    s = await get_state("streak")
    return int(s) if s else 0
