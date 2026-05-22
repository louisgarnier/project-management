"""Stage 12 — final output serialization (pure code, no LLM).

Converts the v5 pipeline internal topic structure to v4-compatible JSON.
Each task carries per-task key_terms / OQ / decisions / citations + the
new `confidence` field.
"""

from __future__ import annotations

import logging
import uuid
from typing import TypedDict

logger = logging.getLogger("calltracker.call_topics_v5.stage_12")


class V4Task(TypedDict, total=False):
    task_id: str  # stable UUID — required for stable React keys + move-task identity
    task: str
    next_step: str
    owner: str
    status: str
    key_terms: list[str]
    open_questions: list[dict]
    decisions: list[dict]
    citations: list[dict]
    confidence: dict  # new in v5: {score, signals}


class V4Topic(TypedDict, total=False):
    name: str
    importance: str
    tasks: list[V4Task]


def _stamp_id(existing: object) -> str:
    """Keep an existing task_id when present + non-empty; otherwise mint a fresh UUID."""
    if isinstance(existing, str) and existing.strip():
        return existing
    return str(uuid.uuid4())


def serialize_to_v4(synthesized_topics: list[dict]) -> list[V4Topic]:
    """Map v5 internal shape → v4-compatible JSON.

    Note: tasks keep their full per-task structure. confidence is additive
    (existing v4 consumers ignore unknown fields). task_id is stamped per task —
    required for stable React keys + move-task identity in the UI (without it
    the frontend renders all tasks with the same DOM key and uncontrolled
    <input> rows share values across rows after a move).
    """
    out: list[V4Topic] = []
    for topic in synthesized_topics:
        v4_tasks: list[V4Task] = []
        for task in (topic.get("tasks") or []):
            v4_tasks.append({
                "task_id": _stamp_id(task.get("task_id")),
                "task": task.get("task") or "",
                "next_step": task.get("next_step") or "",
                "owner": task.get("owner") or "unassigned",
                "status": task.get("status") or "open",
                "key_terms": task.get("key_terms") or [],
                "open_questions": task.get("open_questions") or [],
                "decisions": task.get("decisions") or [],
                "citations": task.get("citations") or [],
                "confidence": task.get("confidence") or {"score": 0.0, "signals": {}},
            })
        out.append({
            "name": topic.get("topic_name") or "",
            "importance": topic.get("importance") or "medium",
            "tasks": v4_tasks,
        })
    logger.info("[Stage 12] serialized %d topics → v4-compatible format", len(out))
    return out
