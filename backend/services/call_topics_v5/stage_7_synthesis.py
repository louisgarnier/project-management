"""Stage 7 — per-topic task synthesis (LLM, temperature=0).

ONE LLM call per topic. Narrow context = only that topic's atomic units.
Validates: ≥2 evidence_unit_ids per task (unless only 1 unit total), all
unit_ids present in input set.

Sequential baseline — parallelization deferred per the plan.
"""

from __future__ import annotations

import json
import logging
from typing import TypedDict

from backend.prompts.call_topics_v5_synthesis import (
    CALL_TOPICS_V5_SYNTHESIS_SYSTEM,
    build_synthesis_user_message,
)
from backend.services.call_topics_v5.stage_2_atomic import _strip_code_fences
from backend.services.llm_service import call_llm_raw

logger = logging.getLogger("calltracker.call_topics_v5.stage_7")

TASK_STATUS = {"open", "in_progress", "resolved"}


class SynthesizedTask(TypedDict, total=False):
    task: str
    next_step: str
    owner: str
    status: str
    key_terms: list[str]
    open_questions: list[dict]
    decisions: list[dict]
    evidence_unit_ids: list[str]


def _validate_synthesized(
    raw: list,
    valid_unit_ids: set[str],
    topic_unit_count: int,
) -> tuple[list[SynthesizedTask], list[str]]:
    """Validate the LLM output for one topic."""
    kept: list[SynthesizedTask] = []
    reasons: list[str] = []
    min_evidence = 1 if topic_unit_count == 1 else 2

    for i, t in enumerate(raw):
        if not isinstance(t, dict):
            reasons.append(f"task {i}: not a dict")
            continue
        task = (t.get("task") or "").strip()
        if not task:
            reasons.append(f"task {i}: empty task field")
            continue
        next_step = t.get("next_step")
        if next_step is None or not isinstance(next_step, str):
            next_step = ""
        owner = (t.get("owner") or "unassigned").strip() or "unassigned"
        status = (t.get("status") or "open").lower()
        if status not in TASK_STATUS:
            status = "open"
        key_terms = t.get("key_terms")
        if not isinstance(key_terms, list):
            key_terms = []
        key_terms = [str(k).strip() for k in key_terms if str(k).strip()]
        oqs = t.get("open_questions")
        if not isinstance(oqs, list):
            oqs = []
        decs = t.get("decisions")
        if not isinstance(decs, list):
            decs = []
        ev_ids = t.get("evidence_unit_ids")
        if not isinstance(ev_ids, list) or not all(isinstance(x, str) for x in ev_ids):
            reasons.append(f"task {i} ({task!r}): evidence_unit_ids must be a list of strings")
            continue
        bad = [uid for uid in ev_ids if uid not in valid_unit_ids]
        if bad:
            reasons.append(f"task {i} ({task!r}): unknown unit_ids {bad}")
            continue
        if len(ev_ids) < min_evidence:
            reasons.append(
                f"task {i} ({task!r}): evidence_unit_ids has {len(ev_ids)} entries, need ≥{min_evidence}"
            )
            continue
        kept.append({
            "task": task,
            "next_step": next_step.strip(),
            "owner": owner,
            "status": status,
            "key_terms": key_terms,
            "open_questions": oqs,
            "decisions": decs,
            "evidence_unit_ids": ev_ids,
        })
    return kept, reasons


async def synthesize_topic(
    topic_name: str,
    importance: str,
    topic_units: list[dict],
    *,
    llm: str,
    model: str | None,
) -> dict:
    """Run Stage 7 for one topic.

    Returns: {topic_name, importance, tasks: [...], rejected: [...]}
    """
    if not topic_units:
        return {"topic_name": topic_name, "importance": importance, "tasks": [], "rejected": ["no units"]}

    user_msg = build_synthesis_user_message(topic_name, importance, topic_units)
    logger.info(
        "[Stage 7] synthesizing topic %r (%d units, temp=0)",
        topic_name, len(topic_units),
    )
    raw = await call_llm_raw(
        CALL_TOPICS_V5_SYNTHESIS_SYSTEM,
        user_msg,
        llm,
        max_tokens=8192,
        model=model,
        temperature=0,
    )

    body = _strip_code_fences(raw)
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        logger.error("[Stage 7] LLM did not return valid JSON for topic %r: %s", topic_name, e)
        return {
            "topic_name": topic_name,
            "importance": importance,
            "tasks": [],
            "rejected": [f"synthesis LLM response not parseable: {e}"],
        }
    if not isinstance(parsed, list):
        if isinstance(parsed, dict):
            for k in ("tasks", "items"):
                if isinstance(parsed.get(k), list):
                    parsed = parsed[k]
                    break
        if not isinstance(parsed, list):
            return {
                "topic_name": topic_name,
                "importance": importance,
                "tasks": [],
                "rejected": [f"synthesis LLM returned {type(parsed).__name__}, expected array"],
            }

    valid_ids = {u["unit_id"] for u in topic_units}
    tasks, rejected = _validate_synthesized(parsed, valid_ids, len(topic_units))
    logger.info(
        "[Stage 7] topic %r: %d tasks synthesized (rejected %d)",
        topic_name, len(tasks), len(rejected),
    )
    return {
        "topic_name": topic_name,
        "importance": importance,
        "tasks": tasks,
        "rejected": rejected,
    }


async def synthesize_all_topics(
    working_topics: list[dict],
    atomic_pool: list[dict],
    *,
    llm: str,
    model: str | None,
    progress_callback=None,
) -> list[dict]:
    """Synthesize every working topic. Sequential per the plan baseline."""
    by_uid = {u["unit_id"]: u for u in atomic_pool}
    out: list[dict] = []
    for i, wt in enumerate(working_topics, start=1):
        topic_units = [by_uid[uid] for uid in (wt.get("unit_ids") or []) if uid in by_uid]
        if progress_callback:
            await progress_callback(f"Stage 7: synthesizing topic {i}/{len(working_topics)}: {wt.get('topic_name')!r}")
        result = await synthesize_topic(
            wt.get("topic_name") or "",
            wt.get("importance") or "medium",
            topic_units,
            llm=llm,
            model=model,
        )
        # Carry through registry linkage
        result["registry_id"] = wt.get("registry_id")
        result["new_topic"] = wt.get("new_topic", False)
        result["provisional"] = wt.get("provisional", False)
        out.append(result)
    return out
