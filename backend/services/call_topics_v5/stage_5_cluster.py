"""Stage 5 — topic clustering (LLM, temperature=0).

The LLM groups atomic units into topics. Validates: every unit_id appears in
exactly one topic (no orphans, no duplicates). Registry-matched topic names
must be byte-identical to the canonical string.
"""

from __future__ import annotations

import json
import logging
from typing import TypedDict

from backend.prompts.call_topics_v5_cluster import (
    CALL_TOPICS_V5_CLUSTER_SYSTEM,
    build_cluster_system_prompt,
    build_cluster_user_message,
)
from backend.services.call_topics_v5.stage_2_atomic import _strip_code_fences
from backend.services.llm_service import call_llm_raw

logger = logging.getLogger("calltracker.call_topics_v5.stage_5")

IMPORTANCE_VALUES = {"low", "medium", "high"}


class TopicCluster(TypedDict, total=False):
    topic_name: str
    unit_ids: list[str]
    new_topic: bool
    importance: str


def _validate_clusters(
    raw: list,
    all_unit_ids: set[str],
    registry_names: set[str],
) -> tuple[list[TopicCluster], list[str]]:
    """Validate clustering output:
    - every unit_id appears in exactly one cluster
    - no extra unit_ids
    - registry matches use the canonical name exactly
    """
    kept: list[TopicCluster] = []
    reasons: list[str] = []
    seen_units: set[str] = set()
    canonical_lc = {n.lower(): n for n in registry_names}

    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            reasons.append(f"cluster {i}: not a dict")
            continue
        name = (c.get("topic_name") or "").strip()
        if not name:
            reasons.append(f"cluster {i}: empty topic_name")
            continue
        units = c.get("unit_ids")
        if not isinstance(units, list) or not units:
            reasons.append(f"cluster {i} ({name!r}): unit_ids must be non-empty list")
            continue
        if not all(isinstance(u, str) for u in units):
            reasons.append(f"cluster {i} ({name!r}): all unit_ids must be strings")
            continue
        # Detect duplicates ACROSS clusters
        dups = [u for u in units if u in seen_units]
        if dups:
            reasons.append(f"cluster {i} ({name!r}): unit_ids already assigned: {dups}")
            continue
        # Detect unknown unit_ids
        unknown = [u for u in units if u not in all_unit_ids]
        if unknown:
            reasons.append(f"cluster {i} ({name!r}): unknown unit_ids: {unknown}")
            continue
        seen_units.update(units)
        # new_topic flag — default False
        new_topic = bool(c.get("new_topic", False))
        # If the LLM claims new_topic but the name matches a registry entry
        # (case-insensitive), normalise: it's NOT new, snap to canonical.
        if name.lower() in canonical_lc:
            name = canonical_lc[name.lower()]
            new_topic = False
        importance = (c.get("importance") or "medium").lower()
        if importance not in IMPORTANCE_VALUES:
            importance = "medium"
        kept.append({
            "topic_name": name,
            "unit_ids": units,
            "new_topic": new_topic,
            "importance": importance,
        })

    # Detect orphans (units that should have been assigned)
    orphans = sorted(all_unit_ids - seen_units)
    if orphans:
        reasons.append(f"ORPHANS — units not assigned to any cluster: {orphans}")
    return kept, reasons


async def cluster_topics(
    atomic_units: list[dict],
    topic_registry: list[dict],
    *,
    llm: str,
    model: str | None,
    project_context: str = "",
) -> dict:
    """Run Stage 5. Returns clusters + rejections.

    If orphans detected, they are reported in rejected — Stage 10 will escalate.
    """
    if not atomic_units:
        return {"clusters": [], "rejected": ["no atomic units to cluster"], "orphans": []}

    user_msg = build_cluster_user_message(atomic_units, topic_registry)
    logger.info(
        "[Stage 5] clustering %d units against %d registry entries (temp=0)",
        len(atomic_units), len(topic_registry),
    )
    raw = await call_llm_raw(
        build_cluster_system_prompt(project_context),
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
        logger.error("[Stage 5] LLM did not return valid JSON: %s", e)
        return {
            "clusters": [],
            "rejected": [f"clustering LLM response not parseable: {e}"],
            "orphans": [u["unit_id"] for u in atomic_units],
        }
    if not isinstance(parsed, list):
        if isinstance(parsed, dict):
            for k in ("clusters", "topics", "items"):
                if isinstance(parsed.get(k), list):
                    parsed = parsed[k]
                    break
        if not isinstance(parsed, list):
            return {
                "clusters": [],
                "rejected": [f"clustering LLM returned {type(parsed).__name__}, expected array"],
                "orphans": [u["unit_id"] for u in atomic_units],
            }

    all_ids = {u["unit_id"] for u in atomic_units}
    registry_names = {r["name"] for r in topic_registry}
    clusters, rejected = _validate_clusters(parsed, all_ids, registry_names)
    seen = {uid for c in clusters for uid in c["unit_ids"]}
    orphans = sorted(all_ids - seen)
    logger.info(
        "[Stage 5] %d clusters (%d orphan units, %d validation failures)",
        len(clusters), len(orphans), len(rejected),
    )
    return {"clusters": clusters, "rejected": rejected, "orphans": orphans}
