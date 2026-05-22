"""
Content generation + verification engine — with per-call cost tracking.

Two-pass system:
  Pass 1: generate(concept, level) -> text          (web search enabled)
  Pass 2: verify(text)            -> text, stats    (web search enabled, math checked)

Model routing (cost optimisation):
  Level 1-2 concepts → CLAUDE_MODEL_FAST (Haiku)  ~$0.005-0.02 per call
  Level 3+ concepts  → CLAUDE_MODEL      (Sonnet) ~$0.05-0.10 per call
  Haiku is 3-5× cheaper on output and produces quality output for basic concepts.

Cost tracking:
  _recent_calls deque  — last 50 calls in-memory; shown by /cost
  api_call_log table   — every call persisted to DB; survives restarts
"""
import asyncio
import datetime as dt
import json
import re
from collections import deque
from typing import Tuple, Dict, Any, Optional, List

import anthropic
from anthropic import Anthropic
import config


_client: Optional[Anthropic] = None


def client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


# -----------------------------------------------------------------------------
# Cost tracking (process-lifetime totals + per-call ring buffer)
# -----------------------------------------------------------------------------
_cost_state: Dict[str, Any] = {
    "calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cost_usd": 0.0,
    "by_model": {},
}

_recent_calls: deque = deque(maxlen=50)  # cleared on bot restart; DB has the full history


def _record_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    call_type: str = "unknown",
    concept_id: str = "",
) -> float:
    """Update in-memory totals and per-call log. Returns cost in USD for this call."""
    pricing = config.PRICING.get(model, {"input": 0.0, "output": 0.0})
    cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
    _cost_state["calls"] += 1
    _cost_state["input_tokens"] += input_tokens
    _cost_state["output_tokens"] += output_tokens
    _cost_state["cost_usd"] += cost
    m = _cost_state["by_model"].setdefault(
        model, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    )
    m["calls"] += 1
    m["input_tokens"] += input_tokens
    m["output_tokens"] += output_tokens
    m["cost_usd"] += cost
    _recent_calls.append(
        {
            "ts": dt.datetime.now().strftime("%H:%M"),
            "call_type": call_type,
            "concept_id": concept_id or "—",
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
        }
    )
    return cost


def get_cost_stats() -> Dict[str, Any]:
    """Snapshot of API cost since process start."""
    return {
        "calls": _cost_state["calls"],
        "input_tokens": _cost_state["input_tokens"],
        "output_tokens": _cost_state["output_tokens"],
        "cost_usd": round(_cost_state["cost_usd"], 4),
        "by_model": {
            m: {**v, "cost_usd": round(v["cost_usd"], 4)}
            for m, v in _cost_state["by_model"].items()
        },
    }


def get_recent_calls(limit: int = 10) -> List[Dict[str, Any]]:
    """Return the most recent calls, newest first."""
    calls = list(_recent_calls)
    return list(reversed(calls))[:limit]


# -----------------------------------------------------------------------------
# Low-level Claude call with retry + 429 backoff
# -----------------------------------------------------------------------------
def _is_rate_limit(err: Exception) -> bool:
    if isinstance(err, anthropic.RateLimitError):
        return True
    status = getattr(err, "status_code", None)
    if status == 429:
        return True
    return "429" in str(err)


async def _call_claude(
    system: str,
    user: str,
    max_tokens: int,
    use_web_search: bool = True,
    model: Optional[str] = None,
    call_type: str = "unknown",
    concept_id: str = "",
) -> str:
    """
    Single call to Claude. Retries with backoff on errors.
    Records per-call token usage + cost to both in-memory ring buffer and DB.
    """
    model = model or config.CLAUDE_MODEL

    def _go() -> Tuple[str, int, int]:
        kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if use_web_search:
            kwargs["tools"] = [config.WEB_SEARCH_TOOL]
        resp = client().messages.create(**kwargs)
        usage = getattr(resp, "usage", None)
        in_tok = int(getattr(usage, "input_tokens", 0) or 0) if usage else 0
        out_tok = int(getattr(usage, "output_tokens", 0) or 0) if usage else 0
        out = [
            block.text
            for block in resp.content
            if getattr(block, "type", None) == "text"
        ]
        return "\n".join(out).strip(), in_tok, out_tok

    last_err: Optional[Exception] = None
    for attempt in range(config.RETRY_ATTEMPTS):
        try:
            text, in_tok, out_tok = await asyncio.to_thread(_go)
            cost = _record_usage(model, in_tok, out_tok, call_type, concept_id)
            # Persist to DB — fire-and-forget; a DB failure must never break delivery
            try:
                import database as _db  # lazy import avoids module-load ordering issues
                asyncio.create_task(
                    _db.log_api_call(call_type, concept_id, model, in_tok, out_tok, cost)
                )
            except Exception:  # noqa: BLE001
                pass
            return text
        except Exception as e:  # noqa: BLE001
            last_err = e
            if _is_rate_limit(e):
                await asyncio.sleep(config.RATE_LIMIT_BACKOFF_SECONDS)
            else:
                await asyncio.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Claude API failed after {config.RETRY_ATTEMPTS} attempts: {last_err}")


# -----------------------------------------------------------------------------
# Prompts
# -----------------------------------------------------------------------------
TEACHING_RULES = """\
You are MasteryBot, teaching finance/consulting/VC/PE/investing from the ground up.

Assume the learner knows NOTHING. Build from zero.
Every new term must include a plain-English explanation in brackets the first time
it appears, with the business term in brackets after, e.g.
"how much money is left after making the product (this is called Gross Profit)."

ABSOLUTE RULES:
- No jargon without immediate plain-English explanation in brackets on first use.
- No motivational filler. Every sentence teaches.
- Every concept has a REAL company example with REAL numbers, named and specific.
- Every concept has an analogy from everyday life.
- Every formula must include a worked numerical example. Show the maths step by step.
- Verify your maths. Every number you write must be correct.
- The quick check must have ONE unambiguous answer.
- Output length 150-400 words. Dense, no padding.
- Use the exact section structure shown below.
"""


CONCEPT_TEMPLATE = """\
📚 [Subject] → [Module] → [Concept Name]

WHAT IT IS:
[1-2 sentences. Plain English. No jargon.]
(This is called "[business term]" in business/finance.)

WHY IT MATTERS:
[Who looks at this? What decisions depend on it? Be specific —
"PE investors use this to..." not "this is important."]

HOW IT WORKS:
[Mechanics. If there's a formula, show it with worked numbers — first round numbers,
then a real company.]

Formula: [plain English name] = [components in plain English]
Worked example: [step by step with actual numbers, one clear answer]

EXAMPLE:
[Real company, real situation, real numbers. Named. Specific.]

ANALOGY:
[Something intuitive from everyday life that locks it in.]

CONNECTS TO:
← [prereq knowledge]
→ [what this leads to next]

💡 Quick check: [ONE question with ONE unambiguous answer]
"""


LEVEL_HINTS = {
    1: "Level 1 — basic. Define, give one formula, one real example, one analogy.",
    2: "Level 2 — applied. Use a recent real company. Show full calculations.",
    3: "Level 3 — edge cases. Where this metric misleads. Cross-concept connections.",
    4: "Level 4 — expert. Second-order effects. Synthesis across statements.",
    5: "Level 5 — mastery. Teach-quality. Spot loopholes and where smart investors find edge.",
}


def _build_generation_prompt(concept: Dict[str, Any], level: int) -> Tuple[str, str]:
    system = TEACHING_RULES + "\n\nFollow this exact template:\n\n" + CONCEPT_TEMPLATE
    level_hint = LEVEL_HINTS.get(level, LEVEL_HINTS[1])
    user = (
        f"Teach the concept: {concept['title']} (id: {concept['id']}).\n"
        f"Subject: {concept['subject']}. Module: {concept['module']}.\n"
        f"{level_hint}\n\n"
        "Use web_search to find a recent real company example with real numbers.\n"
        "Verify every number you cite. Show maths step by step.\n"
        "Write the lesson now. Do not include any other commentary."
    )
    return system, user


VERIFICATION_RULES = """\
You are MasteryBot's verification pass. Your job is to make sure the lesson is correct,
clear, and unambiguous before it is sent to the learner.

Do the following:
1. Extract every factual claim (numbers, dates, company names, deal details).
2. Verify each via web_search where possible.
3. Re-solve EVERY formula / calculation in the lesson independently. If the
   maths don't match, FIX them and note the correction.
4. Solve the quick-check question yourself. Confirm one unambiguous answer.
5. Look for currency mixing errors (e.g. ₹ and $ in the same equation).
6. Look for ambiguous wording that allows two valid interpretations.
7. Flag anything unverifiable.

Return a single JSON object on one line, then a separator line `---FINAL---`,
then the corrected, final lesson text to send.

JSON schema:
{
  "claims_total": int,
  "claims_verified": int,
  "claims_flagged": int,
  "math_errors_found": int,
  "flagged_details": "short description of any issues, or empty string"
}

Do not include any other commentary outside the JSON and the final lesson.
"""


def _build_verification_prompt(text: str) -> Tuple[str, str]:
    system = VERIFICATION_RULES
    user = "Here is the lesson to verify:\n\n" + text
    return system, user


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------
async def generate_concept(concept: Dict[str, Any], level: int = 1) -> str:
    """Pass 1 — generate raw lesson.
    Uses Haiku for level 1-2 (cheap, still high quality for basics),
    Sonnet for level 3+ (complex edge-case / synthesis content).
    """
    model = (
        config.CLAUDE_MODEL_FAST
        if level <= config.FAST_MODEL_MAX_LEVEL
        else config.CLAUDE_MODEL
    )
    system, user = _build_generation_prompt(concept, level)
    return await _call_claude(
        system, user, config.MAX_TOKENS_GENERATION,
        model=model, call_type="generation", concept_id=concept.get("id", ""),
    )


async def verify_concept(text: str, concept_id: str = "") -> Tuple[str, Dict[str, Any]]:
    """Pass 2 — verify + correct. Runs on the cheaper Haiku model."""
    system, user = _build_verification_prompt(text)
    raw = await _call_claude(
        system, user, config.MAX_TOKENS_VERIFICATION,
        model=config.CLAUDE_MODEL_VERIFY,
        call_type="verification", concept_id=concept_id,
    )
    return _parse_verification(raw, fallback=text)


def _parse_verification(raw: str, fallback: str) -> Tuple[str, Dict[str, Any]]:
    """Parse the JSON + final text from the verification response."""
    default_stats = {
        "claims_total": 0,
        "claims_verified": 0,
        "claims_flagged": 0,
        "math_errors_found": 0,
        "flagged_details": "",
    }
    if "---FINAL---" not in raw:
        stats = _extract_first_json(raw) or default_stats
        text = re.sub(r"^\s*\{.*?\}\s*", "", raw, count=1, flags=re.DOTALL).strip()
        if not text:
            text = fallback
        return text, {**default_stats, **stats}

    json_part, _, final_part = raw.partition("---FINAL---")
    stats = _extract_first_json(json_part) or default_stats
    final_text = final_part.strip() or fallback
    return final_text, {**default_stats, **stats}


def _extract_first_json(text: str) -> Optional[Dict[str, Any]]:
    """Find the first balanced JSON object in text and parse it."""
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    start = -1
    return None


async def generate_and_verify(
    concept: Dict[str, Any], level: int = 1
) -> Tuple[str, Dict[str, Any]]:
    """End-to-end: generate then verify. Returns (final_text, stats)."""
    raw = await generate_concept(concept, level)
    await asyncio.sleep(config.INTER_PASS_DELAY_SECONDS)
    final, stats = await verify_concept(raw, concept_id=concept.get("id", ""))
    return final, stats


# -----------------------------------------------------------------------------
# Other modes
# -----------------------------------------------------------------------------
async def answer_followup(original_lesson: str, question: str) -> str:
    """Doubt-clearing reply mode."""
    system = (
        "You are MasteryBot answering a learner's follow-up question on a lesson "
        "you just sent. Rules:\n"
        "- Answer the SPECIFIC question only. 2-4 sentences max for the direct answer.\n"
        "- If the original example didn't click, give ONE new example or analogy.\n"
        "- Don't repeat the whole concept.\n"
        "- If the question reveals a prerequisite gap, name it and give a one-line bridge.\n"
        "- Use plain English. Explain any new jargon in brackets on first use.\n"
        "- Verify any numbers you cite (web_search if needed)."
    )
    user = f"Original lesson:\n{original_lesson}\n\nLearner's question:\n{question}"
    return await _call_claude(
        system, user, config.MAX_TOKENS_QA,
        model=config.CLAUDE_MODEL_QA, call_type="qa",
    )


async def generate_example(concept: Dict[str, Any]) -> str:
    """/example — another worked real-world example."""
    system = (
        TEACHING_RULES
        + "\n\nGenerate ANOTHER real-world example for an already-learned concept. "
        "Use a DIFFERENT company than the one in the original lesson if you can. "
        "Format: 1) one-sentence recap of the concept, 2) the new real example with real "
        "numbers and a worked calculation, 3) what insight this example reveals. "
        "150-300 words."
    )
    user = f"Concept: {concept['title']} (id: {concept['id']}). Give a new example now."
    return await _call_claude(
        system, user, config.MAX_TOKENS_GENERATION,
        call_type="example", concept_id=concept.get("id", ""),
    )


async def generate_formula(concept: Dict[str, Any]) -> str:
    """/formula — just the formula + worked example."""
    system = (
        "You are MasteryBot. Give ONLY the formula and a tight worked example.\n"
        "Format:\n"
        "Formula (plain English): ...\n"
        "Formula (symbolic): ...\n"
        "Worked example (real company, real numbers, step by step):\n"
        "Answer: ...\n"
        "Verify your maths. No padding. 120-250 words."
    )
    user = f"Concept: {concept['title']} (id: {concept['id']})."
    return await _call_claude(
        system, user, config.MAX_TOKENS_QA,
        call_type="formula", concept_id=concept.get("id", ""),
    )


async def generate_spaced_reminder(concept: Dict[str, Any], days_ago: int) -> str:
    """Spaced-repetition surface with a NEW application."""
    system = (
        "You are MasteryBot doing a spaced-repetition re-surfacing.\n"
        "Format:\n"
        f"🔄 {concept['title']} — you learned this {days_ago} day(s) ago.\n"
        "Here's how it shows up somewhere different: [a NEW real example, named company, "
        "real numbers, 2-4 sentences, verify any number].\n"
        "💡 Quick check: [ONE application question with ONE unambiguous answer].\n"
        "120-220 words."
    )
    user = f"Concept: {concept['title']} (id: {concept['id']}). Days since first taught: {days_ago}."
    return await _call_claude(
        system, user, config.MAX_TOKENS_QA,
        call_type="spaced", concept_id=concept.get("id", ""),
    )


# -----------------------------------------------------------------------------
# Assessment helpers
# -----------------------------------------------------------------------------
async def generate_assessment_questions(
    concept_ids: List[str], titles: List[str], num_questions: int = 10
) -> str:
    """Build an assessment over a list of recently-covered concepts."""
    listing = "\n".join(f"- {cid}: {t}" for cid, t in zip(concept_ids, titles))
    system = (
        "You are MasteryBot generating a learner assessment.\n"
        f"Generate exactly {num_questions} questions across the following covered concepts:\n"
        f"{listing}\n\n"
        "Mix: ~30% recall (definitions/formulas), ~50% application (given a scenario, "
        "what number / what would you look at / why), ~20% connection (how A relates to B).\n"
        "Each question must have one unambiguous answer.\n"
        "Format each question:\n"
        "Q<n>. [question]\n"
        "   (type: recall|application|connection; concept_id: <id>)\n"
        "Do not include answers. End with: 'Reply with your answers in order.'"
    )
    user = "Generate the assessment now."
    return await _call_claude(
        system, user, config.MAX_TOKENS_GENERATION,
        use_web_search=False, call_type="assessment_gen",
    )


async def score_assessment(
    questions_text: str, learner_answers: str
) -> Tuple[str, List[Dict[str, Any]]]:
    """Score a learner's answers. Returns (markdown_summary, per_question_records)."""
    system = (
        "You are MasteryBot scoring a learner's assessment answers.\n"
        "For each question:\n"
        "- Decide score 1-5 on reasoning quality (1 = wrong/blank, 3 = correct but shallow, "
        "5 = correct with sharp reasoning).\n"
        "- Give one-sentence feedback.\n"
        "Return a single JSON array on one line, then '---SUMMARY---', then a short "
        "markdown summary for the learner.\n\n"
        "JSON schema (array): [{question_number:int, concept_id:string, type:string, "
        "score:int, feedback:string}]"
    )
    user = (
        "Questions:\n"
        + questions_text
        + "\n\nLearner answers:\n"
        + learner_answers
    )
    raw = await _call_claude(
        system, user, config.MAX_TOKENS_VERIFICATION,
        use_web_search=False, call_type="assessment_score",
    )
    return _parse_score(raw)


def _parse_score(raw: str) -> Tuple[str, List[Dict[str, Any]]]:
    if "---SUMMARY---" in raw:
        json_part, _, summary = raw.partition("---SUMMARY---")
    else:
        json_part, summary = raw, ""
    records: List[Dict[str, Any]] = []
    depth = 0
    start = -1
    for i, ch in enumerate(json_part):
        if ch == "[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    records = json.loads(json_part[start : i + 1])
                except json.JSONDecodeError:
                    records = []
                break
    return summary.strip() or "Scored.", records
