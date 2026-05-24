"""Stage 6 — topic registry reconciliation (pure code, no LLM).

For each cluster from Stage 5:
- If it matches a registry entry → finalize canonical name + record registry_id.
- If it's flagged new_topic → mark provisional + queue for Stage 11 human approval.

Also computes lexical similarity (Jaccard on tokens) against the registry —
new proposals with similarity ≥ 0.6 get a `suggested_match_id` so the user
can "merge with existing" instead of approving a new entry.
"""

from __future__ import annotations

import logging
from typing import TypedDict

from backend.services.topic_similarity import effective_token_set

logger = logging.getLogger("calltracker.call_topics_v5.stage_6")

LEXICAL_MERGE_SUGGESTION_THRESHOLD = 0.6  # tuned later against gold set


def _jaccard(a: str, b: str) -> float:
    """Stage 6 name-vs-name jaccard. Stable wrapper over shared effective_token_set."""
    sa = effective_token_set({"name": a})
    sb = effective_token_set({"name": b})
    inter, union = sa & sb, sa | sb
    return (len(inter) / len(union)) if union else 0.0


class WorkingTopic(TypedDict, total=False):
    topic_name: str
    unit_ids: list[str]
    registry_id: str | None
    new_topic: bool
    provisional: bool
    importance: str


class NewTopicProposal(TypedDict, total=False):
    proposed_name: str
    unit_ids: list[str]
    suggested_match_id: str | None
    suggested_match_name: str | None
    lexical_similarity_to_existing: float
    importance: str


class ReconciliationResult(TypedDict):
    working_topics: list[WorkingTopic]
    new_topic_proposals: list[NewTopicProposal]


def reconcile_with_registry(
    clusters: list[dict],
    topic_registry: list[dict],
) -> ReconciliationResult:
    """For each cluster:
      - If name matches a registry entry (case-insensitive) → working_topic with registry_id.
      - Else → new_topic_proposal with optional suggested_match (≥ threshold Jaccard).
      Working topics still include new proposals with provisional=True so downstream
      stages have a name to operate on (per PRD).
    """
    # Build case-insensitive name lookup
    registry_by_lc: dict[str, dict] = {r["name"].lower(): r for r in topic_registry}

    working: list[WorkingTopic] = []
    proposals: list[NewTopicProposal] = []

    for c in clusters:
        name = c.get("topic_name") or ""
        unit_ids = c.get("unit_ids") or []
        importance = c.get("importance") or "medium"
        flagged_new = bool(c.get("new_topic", False))

        # Case-insensitive match against registry
        reg = registry_by_lc.get(name.lower())
        if reg and not flagged_new:
            # Canonical match — finalize
            working.append({
                "topic_name": reg["name"],
                "unit_ids": unit_ids,
                "registry_id": reg["id"],
                "new_topic": False,
                "provisional": False,
                "importance": importance,
            })
            continue

        # Treat as a new proposal — find best suggested_match via Jaccard
        best_match_id: str | None = None
        best_match_name: str | None = None
        best_sim = 0.0
        for r in topic_registry:
            sim = _jaccard(name, r["name"])
            if sim > best_sim:
                best_sim = sim
                best_match_id = r["id"]
                best_match_name = r["name"]
        suggestion_id = best_match_id if best_sim >= LEXICAL_MERGE_SUGGESTION_THRESHOLD else None
        suggestion_name = best_match_name if best_sim >= LEXICAL_MERGE_SUGGESTION_THRESHOLD else None
        proposals.append({
            "proposed_name": name,
            "unit_ids": unit_ids,
            "suggested_match_id": suggestion_id,
            "suggested_match_name": suggestion_name,
            "lexical_similarity_to_existing": round(best_sim, 3),
            "importance": importance,
        })
        # Also add to working topics provisionally so downstream stages have it
        working.append({
            "topic_name": name,
            "unit_ids": unit_ids,
            "registry_id": None,
            "new_topic": True,
            "provisional": True,
            "importance": importance,
        })

    logger.info(
        "[Stage 6] reconciled — %d working topics (%d canonical, %d provisional/new); %d proposals queued",
        len(working),
        sum(1 for w in working if not w.get("new_topic")),
        sum(1 for w in working if w.get("new_topic")),
        len(proposals),
    )
    return {"working_topics": working, "new_topic_proposals": proposals}
