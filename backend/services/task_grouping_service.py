"""EPIC-20 Stage 2: LLM cluster + route service.

Inputs: finalized topic list + all tasks (previous-call + new-call).
Output: groups (each with task_ids + target_topic) + unassigned bin + rejections.

The LLM job is narrow on purpose: a fixed topic enum + a fixed task list.
No verdict scoring, no confidence math — those happen in Pass 1/2/3 downstream.
"""
from __future__ import annotations

import json
import logging

from backend.prompts.group_tasks import (
    GROUP_TASKS_SYSTEM,
    build_group_tasks_user_message,
)
from backend.services.call_topics_v5.stage_2_atomic import _strip_code_fences
from backend.services.llm_service import call_llm_raw

logger = logging.getLogger("calltracker.task_grouping")


async def run_task_grouping(
    topics: list[str],
    tasks: list[dict],
    *,
    llm: str,
    model: str | None,
) -> dict:
    """Cluster `tasks` into groups, route each group to one topic in `topics`.

    Returns: {
        groups:     [{task_ids: [...], target_topic: "..."}, ...],
        unassigned: [task_id, ...],   # LLM didn't place these
        rejected:   [reason, ...],    # validation failures
    }
    """
    if not tasks:
        return {"groups": [], "unassigned": [], "rejected": []}
    if not topics:
        return {
            "groups": [],
            "unassigned": [t["id"] for t in tasks],
            "rejected": ["no topics provided"],
        }

    user_msg = build_group_tasks_user_message(topics, tasks)
    logger.info("📥 [TaskGrouping] %d topics, %d tasks", len(topics), len(tasks))
    raw = await call_llm_raw(
        GROUP_TASKS_SYSTEM,
        user_msg,
        llm,
        max_tokens=4096,
        model=model,
        temperature=0,
    )

    body = _strip_code_fences(raw)
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        logger.error("❌ [TaskGrouping] invalid JSON: %s", e)
        return {
            "groups": [],
            "unassigned": [t["id"] for t in tasks],
            "rejected": [f"invalid JSON: {e}"],
        }

    # Some models wrap in {"groups": [...]} — unwrap defensively
    if isinstance(parsed, dict):
        for k in ("groups", "clusters", "items"):
            if isinstance(parsed.get(k), list):
                parsed = parsed[k]
                break
    if not isinstance(parsed, list):
        return {
            "groups": [],
            "unassigned": [t["id"] for t in tasks],
            "rejected": [f"expected array, got {type(parsed).__name__}"],
        }

    valid_topics = set(topics)
    all_ids = {t["id"] for t in tasks}
    kept: list[dict] = []
    reasons: list[str] = []
    seen: set[str] = set()

    for i, g in enumerate(parsed):
        if not isinstance(g, dict):
            reasons.append(f"group {i}: not a dict")
            continue
        topic = (g.get("target_topic") or "").strip()
        if topic not in valid_topics:
            reasons.append(f"group {i}: unknown target_topic {topic!r}")
            continue
        ids_raw = g.get("task_ids") or []
        if not isinstance(ids_raw, list):
            reasons.append(f"group {i}: task_ids must be a list")
            continue
        # Drop unknowns + duplicates (first-occurrence wins)
        ids: list[str] = []
        for x in ids_raw:
            if not isinstance(x, str):
                continue
            if x not in all_ids:
                continue
            if x in seen:
                continue
            ids.append(x)
            seen.add(x)
        if not ids:
            reasons.append(f"group {i}: no valid task_ids after dedup")
            continue
        kept.append({"task_ids": ids, "target_topic": topic})

    unassigned = sorted(all_ids - seen)
    logger.info(
        "📤 [TaskGrouping] %d groups, %d unassigned, %d rejections",
        len(kept), len(unassigned), len(reasons),
    )
    return {"groups": kept, "unassigned": unassigned, "rejected": reasons}
