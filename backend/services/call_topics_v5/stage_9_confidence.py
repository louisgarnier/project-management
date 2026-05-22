"""Stage 9 — confidence scoring (pure heuristic, no LLM).

Computes a 0.0-1.0 confidence per task using 5 weighted signals:
- atomic_units (count, capped 5)        weight 0.30
- distinct_speakers (capped 4)          weight 0.20
- owner_clarity (explicit non-empty)    weight 0.15
- citation_count (capped 4)             weight 0.20
- registry_topic (matched vs new)       weight 0.15

Weights are initial; tune against gold set (see plan Task 5.9).
"""

from __future__ import annotations

import logging
from typing import TypedDict

logger = logging.getLogger("calltracker.call_topics_v5.stage_9")

WEIGHTS = {
    "atomic_units": 0.30,
    "distinct_speakers": 0.20,
    "owner_clarity": 0.15,
    "citation_count": 0.20,
    "registry_topic": 0.15,
}


class ConfidenceBreakdown(TypedDict, total=False):
    score: float
    signals: dict


def _signal_atomic_units(n: int) -> float:
    """Capped at 5: 0 units → 0.0; 5+ → 1.0; linear in between."""
    return min(n, 5) / 5.0


def _signal_distinct_speakers(n: int) -> float:
    return min(n, 4) / 4.0


def _signal_owner_clarity(owner: str) -> float:
    owner = (owner or "").strip().lower()
    return 1.0 if (owner and owner not in {"unassigned", "tbd", "?", ""}) else 0.0


def _signal_citation_count(n: int) -> float:
    return min(n, 4) / 4.0


def _signal_registry_topic(is_new: bool) -> float:
    """Matched canonical topic → 1.0; new proposal → 0.5 (intentionally penalized)."""
    return 0.5 if is_new else 1.0


def compute_task_confidence(task: dict, topic_meta: dict, atomic_pool: list[dict]) -> ConfidenceBreakdown:
    """Compute a single task's confidence.

    Args:
        task: synthesized task with evidence_unit_ids + citations + owner
        topic_meta: {"new_topic": bool, ...} (Stage 6 output)
        atomic_pool: full list of atomic units (Stage 4 output)
    """
    by_uid = {u["unit_id"]: u for u in atomic_pool}
    ev_ids = task.get("evidence_unit_ids") or []
    supporting_units = [by_uid[uid] for uid in ev_ids if uid in by_uid]
    distinct_speakers = len({(u.get("owner") or "").strip().lower() for u in supporting_units if u.get("owner")})
    citation_count = len(task.get("citations") or [])

    signals_raw = {
        "atomic_units": len(supporting_units),
        "distinct_speakers": distinct_speakers,
        "owner_clarity": task.get("owner") or "",
        "citation_count": citation_count,
        "registry_topic_is_new": bool(topic_meta.get("new_topic")),
    }
    sub_scores = {
        "atomic_units": _signal_atomic_units(len(supporting_units)),
        "distinct_speakers": _signal_distinct_speakers(distinct_speakers),
        "owner_clarity": _signal_owner_clarity(task.get("owner") or ""),
        "citation_count": _signal_citation_count(citation_count),
        "registry_topic": _signal_registry_topic(bool(topic_meta.get("new_topic"))),
    }
    weighted = sum(sub_scores[k] * WEIGHTS[k] for k in WEIGHTS)
    return {
        "score": round(weighted, 3),
        "signals": {
            "raw": signals_raw,
            "sub_scores": {k: round(v, 3) for k, v in sub_scores.items()},
            "weights": WEIGHTS,
        },
    }


def attach_confidence(synthesized_topics: list[dict], atomic_pool: list[dict]) -> list[dict]:
    """For every task in every topic, attach `confidence: {score, signals}`."""
    out: list[dict] = []
    for topic in synthesized_topics:
        topic_out = dict(topic)
        new_tasks: list[dict] = []
        topic_meta = {"new_topic": topic.get("new_topic", False)}
        for task in (topic.get("tasks") or []):
            tk = dict(task)
            tk["confidence"] = compute_task_confidence(tk, topic_meta, atomic_pool)
            new_tasks.append(tk)
        topic_out["tasks"] = new_tasks
        out.append(topic_out)
    n_tasks = sum(len(t.get("tasks") or []) for t in out)
    logger.info("[Stage 9] confidence attached to %d tasks across %d topics", n_tasks, len(out))
    return out
