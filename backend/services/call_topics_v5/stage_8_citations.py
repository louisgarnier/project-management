"""Stage 8 — task-level citation attachment (pure code, no LLM).

For each synthesized task, walks `evidence_unit_ids` → collects citations
from the atomic_pool (already resolved verbatim in Stage 4) → attaches as
the task's `citations` list. Enforces ≥ 2 citations per task (flagged if not).
"""

from __future__ import annotations

import logging
from typing import TypedDict

logger = logging.getLogger("calltracker.call_topics_v5.stage_8")


class TaskCitation(TypedDict, total=False):
    speaker: str          # the owner of the source unit
    quote: str            # verbatim transcript text (from Stage 4)
    lines: str            # "NNNN-NNNN" range string
    unit_id: str          # provenance


def _build_citation(unit: dict) -> TaskCitation:
    """Map an atomic unit (with citation_valid + citation field from Stage 4) to a task citation."""
    ev = unit.get("evidence_lines") or [0, 0]
    return {
        "speaker": unit.get("owner") or "",
        "quote": unit.get("citation") or "",
        "lines": f"{int(ev[0]):04d}-{int(ev[1]):04d}" if len(ev) == 2 else "",
        "unit_id": unit.get("unit_id") or "",
    }


def attach_citations(
    synthesized_topics: list[dict],
    atomic_pool_with_citations: list[dict],
) -> list[dict]:
    """For each task in each topic, attach `citations` from the referenced atomic units.

    Returns the input topics with each task augmented:
      - `citations`: list of {speaker, quote, lines, unit_id}
      - `citations_below_min`: bool — set True when < 2 citations (flag for Stage 10)
    """
    by_uid = {u["unit_id"]: u for u in atomic_pool_with_citations}
    out: list[dict] = []
    for topic in synthesized_topics:
        topic_out = dict(topic)
        new_tasks: list[dict] = []
        for task in (topic.get("tasks") or []):
            ev_ids = task.get("evidence_unit_ids") or []
            cits = []
            missing: list[str] = []
            for uid in ev_ids:
                unit = by_uid.get(uid)
                if not unit:
                    missing.append(uid)
                    continue
                if not unit.get("citation_valid"):
                    # Stage 4 already flagged it; we skip (don't propagate invalid quotes)
                    continue
                cits.append(_build_citation(unit))
            new_task = dict(task)
            new_task["citations"] = cits
            new_task["citations_below_min"] = len(cits) < 2
            if missing:
                new_task["missing_evidence_unit_ids"] = missing
            new_tasks.append(new_task)
        topic_out["tasks"] = new_tasks
        out.append(topic_out)
    flagged = sum(1 for t in out for tk in t.get("tasks", []) if tk.get("citations_below_min"))
    logger.info(
        "[Stage 8] attached citations across %d topics (%d tasks flagged citations_below_min)",
        len(out), flagged,
    )
    return out
