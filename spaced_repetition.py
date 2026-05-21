"""Spaced repetition scheduling and surfacing."""
import datetime as dt
from typing import List, Optional, Dict, Any

import config
import database as db
from curriculum import get_concept
import content_engine


async def schedule_after_introduction(concept_id: str):
    """First scheduling: due in 1 day."""
    await db.schedule_spaced(concept_id, interval_days=config.SR_INTERVALS[0])


async def due_concepts() -> List[str]:
    return await db.due_for_spaced()


async def days_since_introduced(concept_id: str) -> int:
    prog = await db.get_progress(concept_id)
    if not prog or not prog.get("introduced_at"):
        return 0
    try:
        introduced = dt.datetime.fromisoformat(prog["introduced_at"]).date()
        today = dt.datetime.now(config.TZ).date()
        return max(0, (today - introduced).days)
    except (ValueError, TypeError):
        return 0


async def build_reminder(concept_id: str) -> Optional[Dict[str, Any]]:
    """Generate spaced-repetition surfacing text for a concept."""
    c = get_concept(concept_id)
    if not c:
        return None
    days = await days_since_introduced(concept_id)
    text = await content_engine.generate_spaced_reminder(c, days_ago=days)
    return {"concept_id": concept_id, "text": text}


async def mark_answered(concept_id: str, correct: bool):
    await db.update_spaced(concept_id, correct=correct)
