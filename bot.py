"""
MasteryBot — Telegram bot for structured finance/consulting/PE/VC learning.

Handles:
  - Scheduled morning + evening concept sends
  - On-demand commands (/next, /goto, /concept, /formula, /example,
    /map, /progress, /skip, /review, /test, /weak, /score)
  - Q&A via message replies
  - Weekly assessment + monthly report
  - Daily spaced-repetition surfacing
"""
import asyncio
import logging
import datetime as dt
from typing import Optional, List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
import database as db
import content_engine
import spaced_repetition as sr
import assessment as asm
from curriculum import (
    SUBJECTS,
    all_concepts,
    get_concept,
    subject_for,
    find_concept_by_name,
    concepts_count_per_subject,
    concepts_count_per_module,
    subject_modules,
    subject_title,
    total_concepts,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("masterybot")


# Map of concept_id -> last sent content_id (for reply attribution)
_LAST_CONTENT_PER_MSG: dict = {}
# Track outstanding assessments per chat_id: chat_id -> {"questions": str, "kind": "review"|"test"}
_PENDING_ASSESSMENTS: dict = {}
# Track current subject for /next
_CURRENT_SUBJECT_KEY = "current_subject"


# -----------------------------------------------------------------------------
# Utility: send (split for >4096 chars), remember content_id for replies
# -----------------------------------------------------------------------------
def _split_message(text: str, limit: int = config.TG_MAX_MSG_LEN) -> List[str]:
    if len(text) <= limit:
        return [text]
    chunks: List[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # find the last newline before the limit
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks


async def _send(
    context_or_app, chat_id: int, text: str, content_id: Optional[int] = None
) -> Optional[int]:
    """Send a message (split if needed). Returns last telegram message_id."""
    bot = context_or_app.bot if hasattr(context_or_app, "bot") else context_or_app
    last_msg_id = None
    for chunk in _split_message(text):
        msg = await bot.send_message(chat_id=chat_id, text=chunk)
        last_msg_id = msg.message_id
        if content_id is not None:
            _LAST_CONTENT_PER_MSG[msg.message_id] = content_id
    return last_msg_id


# -----------------------------------------------------------------------------
# Core delivery: generate + verify + send + log
# -----------------------------------------------------------------------------
async def _deliver_concept(context, chat_id: int, concept: dict):
    """Generate, verify, send, log progress + spaced repetition."""
    level = await db.get_level(concept["subject"])
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception:  # noqa: BLE001
        pass
    try:
        text, stats = await content_engine.generate_and_verify(concept, level=level)
    except Exception as e:  # noqa: BLE001
        log.exception("generation failed")
        await _send(context, chat_id, f"⚠️ Couldn't generate {concept['title']}: {e}")
        return

    content_id = await db.log_content(
        subject_id=concept["subject"],
        concept_id=concept["id"],
        text=text,
        verified=True,
        math_verified=(stats.get("math_errors_found", 0) == 0),
    )
    await db.log_verification(
        content_id=content_id,
        claims_total=int(stats.get("claims_total", 0) or 0),
        claims_verified=int(stats.get("claims_verified", 0) or 0),
        claims_flagged=int(stats.get("claims_flagged", 0) or 0),
        math_errors=int(stats.get("math_errors_found", 0) or 0),
        flagged_details=str(stats.get("flagged_details", "") or ""),
    )
    await db.set_progress(concept["id"], "introduced")
    await sr.schedule_after_introduction(concept["id"])
    await db.update_streak()
    await db.set_state(_CURRENT_SUBJECT_KEY, concept["subject"])
    await _send(context, chat_id, text, content_id=content_id)


# -----------------------------------------------------------------------------
# Command handlers
# -----------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 MasteryBot ready.\n\n"
        "I'll teach you finance, consulting, VC, PE, and investing — atoms first, "
        "then frameworks. Two concepts a day by default (8:30 AM and 7:30 PM IST).\n\n"
        "Commands:\n"
        "/next — next concept in current subject\n"
        "/goto [subject] — switch subject (pnl, balance, cashflow, saas, "
        "consulting, valuation, pe, vc)\n"
        "/concept [name] — explain any concept\n"
        "/formula [name] — formula + worked example\n"
        "/example [concept] — another real-world example\n"
        "/map — full curriculum map with progress\n"
        "/progress — quick stats\n"
        "/skip — mark current concept as known\n"
        "/review — 5 quick-fire questions\n"
        "/test — full 10-question assessment\n"
        "/weak — content from your weakest area\n"
        "/score — assessment averages\n\n"
        "Reply to any of my messages with a question to clarify."
    )
    await _send(context, update.effective_chat.id, text)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, context)


async def cmd_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sid = await db.get_state(_CURRENT_SUBJECT_KEY) or "pnl"
    cid = await db.next_concept_in_subject(sid)
    if not cid:
        await _send(
            context,
            update.effective_chat.id,
            f"🎉 You've covered every concept in {subject_title(sid)}. "
            "Try /goto [subject] to switch.",
        )
        return
    c = get_concept(cid)
    await _deliver_concept(context, update.effective_chat.id, c)


async def cmd_goto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await _send(
            context,
            update.effective_chat.id,
            "Usage: /goto [subject]\nSubjects: pnl, balance, cashflow, saas, "
            "consulting, valuation, pe, vc",
        )
        return
    sid = subject_for(" ".join(args))
    if not sid:
        await _send(
            context,
            update.effective_chat.id,
            "Unknown subject. Try: pnl, balance, cashflow, saas, consulting, "
            "valuation, pe, vc",
        )
        return
    await db.set_state(_CURRENT_SUBJECT_KEY, sid)
    cid = await db.next_concept_in_subject(sid)
    if not cid:
        await _send(
            context,
            update.effective_chat.id,
            f"🎉 You've already covered every concept in {subject_title(sid)}.",
        )
        return
    c = get_concept(cid)
    await _deliver_concept(context, update.effective_chat.id, c)


async def cmd_concept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await _send(context, update.effective_chat.id, "Usage: /concept [name]")
        return
    query = " ".join(args)
    c = find_concept_by_name(query)
    if not c:
        await _send(context, update.effective_chat.id, f"No concept matching '{query}'.")
        return
    await _deliver_concept(context, update.effective_chat.id, c)


async def cmd_formula(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await _send(context, update.effective_chat.id, "Usage: /formula [name]")
        return
    c = find_concept_by_name(" ".join(args))
    if not c:
        await _send(
            context, update.effective_chat.id, f"No concept matching '{' '.join(args)}'."
        )
        return
    try:
        text = await content_engine.generate_formula(c)
    except Exception as e:  # noqa: BLE001
        await _send(context, update.effective_chat.id, f"⚠️ Failed: {e}")
        return
    content_id = await db.log_content(
        subject_id=c["subject"], concept_id=c["id"], text=text, verified=False
    )
    await _send(context, update.effective_chat.id, text, content_id=content_id)


async def cmd_example(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if not args:
        await _send(context, update.effective_chat.id, "Usage: /example [concept]")
        return
    c = find_concept_by_name(" ".join(args))
    if not c:
        await _send(
            context, update.effective_chat.id, f"No concept matching '{' '.join(args)}'."
        )
        return
    try:
        text = await content_engine.generate_example(c)
    except Exception as e:  # noqa: BLE001
        await _send(context, update.effective_chat.id, f"⚠️ Failed: {e}")
        return
    content_id = await db.log_content(
        subject_id=c["subject"], concept_id=c["id"], text=text, verified=False
    )
    await _send(context, update.effective_chat.id, text, content_id=content_id)


async def cmd_map(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await build_map_text()
    await _send(context, update.effective_chat.id, text)


async def cmd_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    summary = await db.progress_summary()
    streak = await db.get_streak()
    total = total_concepts()
    counts = concepts_count_per_subject()

    introduced = sum(
        v.get("introduced", 0)
        + v.get("reinforced", 0)
        + v.get("tested", 0)
        + v.get("mastered", 0)
        for v in summary["subject"].values()
    )
    lines = [
        f"📈 Progress: {introduced}/{total} concepts covered",
        f"🔥 Streak: {streak} day(s)",
        "",
    ]
    for sid, meta in SUBJECTS.items():
        sub_states = summary["subject"].get(sid, {})
        covered = (
            sub_states.get("introduced", 0)
            + sub_states.get("reinforced", 0)
            + sub_states.get("tested", 0)
            + sub_states.get("mastered", 0)
        )
        total_s = counts.get(sid, 0)
        lvl = await db.get_level(sid)
        lines.append(f"  • {meta['title']}: {covered}/{total_s}  (level {lvl})")
    await _send(context, update.effective_chat.id, "\n".join(lines))


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mark the next-up concept in the current subject as already known."""
    sid = await db.get_state(_CURRENT_SUBJECT_KEY) or "pnl"
    cid = await db.next_concept_in_subject(sid)
    if not cid:
        await _send(context, update.effective_chat.id, "Nothing to skip — subject complete.")
        return
    c = get_concept(cid)
    await db.set_progress(cid, "mastered")
    await _send(
        context,
        update.effective_chat.id,
        f"⏭️ Skipped: {c['title']}. /next for the one after.",
    )


async def cmd_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await _send(context, chat_id, "🧠 Building 5 quick-fire questions...")
    try:
        text = await asm.build_quickfire(num_questions=5)
    except Exception as e:  # noqa: BLE001
        await _send(context, chat_id, f"⚠️ Failed: {e}")
        return
    if not text:
        await _send(context, chat_id, "Nothing covered yet to review.")
        return
    _PENDING_ASSESSMENTS[chat_id] = {"questions": text, "kind": "review"}
    await _send(
        context,
        chat_id,
        text + "\n\nReply to this message with your answers in order.",
    )


async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await _send(context, chat_id, "📝 Building your 10-question assessment...")
    try:
        text = await asm.build_assessment(num_questions=10)
    except Exception as e:  # noqa: BLE001
        await _send(context, chat_id, f"⚠️ Failed: {e}")
        return
    if not text:
        await _send(context, chat_id, "Nothing covered yet to test.")
        return
    _PENDING_ASSESSMENTS[chat_id] = {"questions": text, "kind": "test"}
    await _send(
        context,
        chat_id,
        text + "\n\nReply to this message with your answers in order.",
    )


async def cmd_weak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    weakest = await asm.weakest_concept_ids(limit=3)
    if not weakest:
        await _send(context, chat_id, "No assessment data yet — take a /test first.")
        return
    cid = weakest[0]
    c = get_concept(cid)
    if not c:
        await _send(context, chat_id, "Couldn't resolve weakest concept.")
        return
    # Use the spaced-repetition style: new example + quick check
    await _send(context, chat_id, f"📌 Reinforcing weakest area: {c['title']}")
    days = await sr.days_since_introduced(cid)
    try:
        text = await content_engine.generate_spaced_reminder(c, days_ago=days)
    except Exception as e:  # noqa: BLE001
        await _send(context, chat_id, f"⚠️ Failed: {e}")
        return
    content_id = await db.log_content(
        subject_id=c["subject"], concept_id=c["id"], text=text, verified=False
    )
    await _send(context, chat_id, text, content_id=content_id)


async def cmd_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await asm.score_report()
    await _send(context, update.effective_chat.id, text)


# -----------------------------------------------------------------------------
# Reply handler (doubt-clearing OR assessment answers)
# -----------------------------------------------------------------------------
async def on_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.reply_to_message:
        return
    chat_id = update.effective_chat.id
    pending = _PENDING_ASSESSMENTS.get(chat_id)
    replied_to_id = msg.reply_to_message.message_id

    # 1) If they're replying to a pending assessment, score it
    if pending:
        questions = pending["questions"]
        await _send(context, chat_id, "🔎 Scoring your answers...")
        try:
            summary, info = await asm.score_and_store(questions, msg.text or "")
        except Exception as e:  # noqa: BLE001
            await _send(context, chat_id, f"⚠️ Scoring failed: {e}")
            return
        _PENDING_ASSESSMENTS.pop(chat_id, None)
        out = ["🧾 Results", summary]
        if info.get("adjustments"):
            out.append("\nLevel adjustments:")
            for sid, a in info["adjustments"].items():
                t = subject_title(sid) if sid in SUBJECTS else sid
                out.append(f"  • {t}: lvl {a['from']} → {a['to']}  (avg {a['avg']})")
        await _send(context, chat_id, "\n".join(out))
        return

    # 2) Otherwise it's a doubt on a lesson
    content_id = _LAST_CONTENT_PER_MSG.get(replied_to_id)
    original_text = msg.reply_to_message.text or ""
    if content_id is None:
        # Best-effort: use the replied-to text directly
        original_text = original_text or "(no original content)"
        content_id = None

    if content_id is not None:
        c = await db.get_content(content_id)
        if c:
            original_text = c["content_text"]

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    except Exception:  # noqa: BLE001
        pass
    try:
        answer = await content_engine.answer_followup(original_text, msg.text or "")
    except Exception as e:  # noqa: BLE001
        await _send(context, chat_id, f"⚠️ Failed: {e}")
        return

    await db.log_qa(content_id, msg.text or "", answer)
    if content_id is not None:
        await db.mark_replied(content_id)
    await _send(context, chat_id, answer)


# -----------------------------------------------------------------------------
# Map text (the /map command output, also pinnable)
# -----------------------------------------------------------------------------
async def build_map_text() -> str:
    summary = await db.progress_summary()
    sub_states = summary["subject"]
    mod_states = summary["module"]
    counts_subject = concepts_count_per_subject()
    counts_module = concepts_count_per_module()
    total = total_concepts()
    streak = await db.get_streak()

    def covered(state_dict):
        return (
            state_dict.get("introduced", 0)
            + state_dict.get("reinforced", 0)
            + state_dict.get("tested", 0)
            + state_dict.get("mastered", 0)
        )

    def bar(done: int, total_n: int, width: int = 10) -> str:
        if total_n <= 0:
            return "░" * width
        filled = round(width * done / total_n)
        return "█" * filled + "░" * (width - filled)

    lines = ["📋 YOUR LEARNING MAP", ""]
    total_done = 0
    for i, (sid, meta) in enumerate(SUBJECTS.items(), 1):
        s_done = covered(sub_states.get(sid, {}))
        s_total = counts_subject.get(sid, 0)
        total_done += s_done
        lines.append(f"SUBJECT {i}: {meta['title']} {bar(s_done, s_total)} {s_done}/{s_total}")
        for mid, mtitle in subject_modules(sid):
            m_done = covered(mod_states.get(mid, {}))
            m_total = counts_module.get(mid, 0)
            lines.append(f"  └ {mtitle} {bar(m_done, m_total)} {m_done}/{m_total}")
    lines.append("")
    lines.append(f"Total: {total_done}/{total} concepts covered")
    lines.append(f"Current streak: 🔥 {streak} day(s)")
    lines.append("")
    lines.append("/goto [subject] to continue any subject")
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Scheduled jobs
# -----------------------------------------------------------------------------
async def scheduled_concept(app: Application):
    if not config.CHAT_ID:
        log.warning("No CHAT_ID configured; skipping scheduled send")
        return
    chat_id = int(config.CHAT_ID)
    sid = await db.get_state(_CURRENT_SUBJECT_KEY) or "pnl"
    cid = await db.next_concept_in_subject(sid)
    if not cid:
        # try other subjects until one has something
        for sid_alt in SUBJECTS:
            cid = await db.next_concept_in_subject(sid_alt)
            if cid:
                sid = sid_alt
                break
    if not cid:
        await _send(app, chat_id, "🎉 You've covered every concept across all subjects!")
        return
    c = get_concept(cid)
    # Reconstruct a minimal context shim
    class _Ctx:
        bot = app.bot

    await _deliver_concept(_Ctx(), chat_id, c)


async def scheduled_spaced_check(app: Application):
    if not config.CHAT_ID:
        return
    chat_id = int(config.CHAT_ID)
    due = await sr.due_concepts()
    if not due:
        return
    # Just surface the oldest-due one (keeps daily volume sensible)
    cid = due[0]
    item = await sr.build_reminder(cid)
    if not item:
        return
    content_id = await db.log_content(
        subject_id=(get_concept(cid) or {}).get("subject"),
        concept_id=cid,
        text=item["text"],
        verified=False,
    )
    await _send(app, chat_id, item["text"], content_id=content_id)
    # Default to extending (correct=True). Will adjust based on engagement later.
    await sr.mark_answered(cid, correct=True)


async def scheduled_weekly_assessment(app: Application):
    if not config.CHAT_ID:
        return
    chat_id = int(config.CHAT_ID)
    text = await asm.build_assessment(num_questions=8)
    if not text:
        return
    _PENDING_ASSESSMENTS[chat_id] = {"questions": text, "kind": "weekly"}
    await _send(
        app,
        chat_id,
        "🗓️ Weekly assessment:\n\n" + text + "\n\nReply with your answers in order.",
    )


async def scheduled_monthly_report(app: Application):
    if not config.CHAT_ID:
        return
    chat_id = int(config.CHAT_ID)
    text = await asm.monthly_report()
    await _send(app, chat_id, text)


def install_schedule(app: Application):
    sched = AsyncIOScheduler(timezone=config.TZ)
    sched.add_job(
        scheduled_concept,
        "cron",
        hour=config.MORNING_HOUR,
        minute=config.MORNING_MIN,
        args=[app],
        id="morning",
    )
    sched.add_job(
        scheduled_concept,
        "cron",
        hour=config.EVENING_HOUR,
        minute=config.EVENING_MIN,
        args=[app],
        id="evening",
    )
    sched.add_job(
        scheduled_spaced_check,
        "cron",
        hour=config.SPACED_REPETITION_HOUR,
        minute=0,
        args=[app],
        id="spaced",
    )
    sched.add_job(
        scheduled_weekly_assessment,
        "cron",
        day_of_week=config.WEEKLY_ASSESS_DAY,
        hour=config.WEEKLY_ASSESS_HOUR,
        minute=0,
        args=[app],
        id="weekly",
    )
    sched.add_job(
        scheduled_monthly_report,
        "cron",
        day=config.MONTHLY_REPORT_DAY,
        hour=config.MONTHLY_REPORT_HOUR,
        minute=0,
        args=[app],
        id="monthly",
    )
    sched.start()
    return sched


# -----------------------------------------------------------------------------
# App startup
# -----------------------------------------------------------------------------
async def post_init(app: Application):
    await db.init_db()
    await db.seed_curriculum(all_concepts())
    install_schedule(app)
    log.info("MasteryBot ready. Total concepts: %d", total_concepts())


def main():
    if not config.TELEGRAM_TOKEN:
        raise SystemExit("MASTERY_BOT_TOKEN missing in environment.")
    if not config.ANTHROPIC_API_KEY:
        raise SystemExit("ANTHROPIC_API_KEY missing in environment.")

    app = (
        ApplicationBuilder()
        .token(config.TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("next", cmd_next))
    app.add_handler(CommandHandler("goto", cmd_goto))
    app.add_handler(CommandHandler("concept", cmd_concept))
    app.add_handler(CommandHandler("formula", cmd_formula))
    app.add_handler(CommandHandler("example", cmd_example))
    app.add_handler(CommandHandler("map", cmd_map))
    app.add_handler(CommandHandler("progress", cmd_progress))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CommandHandler("review", cmd_review))
    app.add_handler(CommandHandler("test", cmd_test))
    app.add_handler(CommandHandler("weak", cmd_weak))
    app.add_handler(CommandHandler("score", cmd_score))

    # Reply handler — any non-command text that's a reply
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.REPLY, on_reply)
    )

    log.info("Starting polling...")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
