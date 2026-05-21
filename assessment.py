"""Weekly assessment + scoring + difficulty adjustment."""
import datetime as dt
from typing import Dict, Any, List, Optional, Tuple

import config
import database as db
import content_engine
from curriculum import (
    get_concept,
    SUBJECTS,
    subject_title,
)


async def recently_covered(limit: int = 30) -> List[Dict[str, Any]]:
    """Return list of {id, title} that have been introduced, most recent first."""
    import aiosqlite

    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            """SELECT concept_id, introduced_at FROM curriculum_progress
               WHERE state != 'not_started'
               ORDER BY introduced_at DESC LIMIT ?""",
            (limit,),
        ) as cur:
            rows = [dict(r) async for r in cur]
    out = []
    for r in rows:
        c = get_concept(r["concept_id"])
        if c:
            out.append({"id": c["id"], "title": c["title"]})
    return out


async def build_assessment(num_questions: int = 10) -> Optional[str]:
    covered = await recently_covered(limit=30)
    if not covered:
        return None
    ids = [c["id"] for c in covered]
    titles = [c["title"] for c in covered]
    return await content_engine.generate_assessment_questions(
        ids, titles, num_questions=num_questions
    )


async def build_quickfire(num_questions: int = 5) -> Optional[str]:
    """/review — 5 quick-fire questions from recently covered material."""
    return await build_assessment(num_questions=num_questions)


async def score_and_store(
    questions_text: str, answers_text: str
) -> Tuple[str, Dict[str, Any]]:
    summary, records = await content_engine.score_assessment(questions_text, answers_text)

    per_subject_scores: Dict[str, List[int]] = {}
    for r in records:
        cid = r.get("concept_id")
        qtype = r.get("type") or ""
        score = int(r.get("score") or 0)
        fb = r.get("feedback") or ""
        if cid and score:
            await db.log_assessment(qtype, cid, score, fb)
        c = get_concept(cid) if cid else None
        if c and score:
            per_subject_scores.setdefault(c["subject"], []).append(score)

    # Adjust subject level
    adjustments: Dict[str, Dict[str, int]] = {}
    for sid, scores in per_subject_scores.items():
        avg = sum(scores) / len(scores)
        cur = await db.get_level(sid)
        new = cur
        if avg >= 4.5 and cur < config.MAX_LEVEL:
            new = cur + 1
        elif avg < 2.5 and cur > 1:
            new = cur - 1
        if new != cur:
            await db.set_level(sid, new)
            adjustments[sid] = {"from": cur, "to": new, "avg": round(avg, 2)}

    return summary, {"records": records, "adjustments": adjustments}


async def weakest_concept_ids(limit: int = 5) -> List[str]:
    """Return concept_ids with the lowest average score so far."""
    import aiosqlite

    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            """SELECT concept_id, AVG(score) AS avg_score
               FROM assessments
               WHERE concept_id IS NOT NULL
               GROUP BY concept_id
               ORDER BY avg_score ASC
               LIMIT ?""",
            (limit,),
        ) as cur:
            return [r["concept_id"] async for r in cur]


async def score_report() -> str:
    avg = await db.average_score_per_subject()
    if not avg:
        return "📊 No assessments yet. Take one with /test."
    lines = ["📊 Assessment averages by subject:"]
    for sid, score in sorted(avg.items(), key=lambda x: -x[1]):
        title = subject_title(sid) if sid in SUBJECTS else sid
        lines.append(f"  • {title}: {score:.2f}/5")
    return "\n".join(lines)


async def monthly_report() -> str:
    """Concepts covered, score trends, strongest/weakest, suggested focus."""
    import aiosqlite

    today = dt.datetime.now(config.TZ).date()
    first_of_prev_month = (today.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    cutoff = first_of_prev_month.isoformat()

    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        async with conn.execute(
            """SELECT subject_id, COUNT(*) AS n
               FROM curriculum_progress
               WHERE state != 'not_started' AND introduced_at >= ?
               GROUP BY subject_id""",
            (cutoff,),
        ) as cur:
            covered_rows = [dict(r) async for r in cur]

        async with conn.execute(
            """SELECT date, AVG(score) AS avg FROM assessments
               WHERE date >= ? GROUP BY date ORDER BY date ASC""",
            (cutoff,),
        ) as cur:
            trend = [dict(r) async for r in cur]

    avg_per_subject = await db.average_score_per_subject()
    if avg_per_subject:
        strongest = max(avg_per_subject.items(), key=lambda x: x[1])
        weakest = min(avg_per_subject.items(), key=lambda x: x[1])
    else:
        strongest = weakest = None

    lines = [f"📅 Monthly Report — {today.isoformat()}", ""]
    if covered_rows:
        lines.append("Concepts covered this period:")
        for r in covered_rows:
            t = subject_title(r["subject_id"]) if r["subject_id"] in SUBJECTS else r["subject_id"]
            lines.append(f"  • {t}: {r['n']}")
    else:
        lines.append("No new concepts covered this period.")

    if trend:
        lines.append("")
        lines.append("Score trend:")
        for t in trend:
            lines.append(f"  • {t['date']}: {t['avg']:.2f}/5")

    if strongest:
        lines.append("")
        s_title = subject_title(strongest[0]) if strongest[0] in SUBJECTS else strongest[0]
        lines.append(f"💪 Strongest area: {s_title} ({strongest[1]:.2f}/5)")
    if weakest:
        w_title = subject_title(weakest[0]) if weakest[0] in SUBJECTS else weakest[0]
        lines.append(f"📌 Suggested focus: {w_title} ({weakest[1]:.2f}/5)")

    return "\n".join(lines)
