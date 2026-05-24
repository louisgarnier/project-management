"""Stage 3 — adversarial recall pass.

Runs unconditionally after Stage 2. Asks the LLM "what did we miss?" and
merges new units into the pool. Same validation as Stage 2.
"""

from __future__ import annotations

import json
import logging

from backend.prompts.call_topics_v5_recall import (
    CALL_TOPICS_V5_RECALL_SYSTEM,
    build_recall_user_message,
)
from backend.services.call_topics_v5.stage_2_atomic import (
    _format_numbered_transcript,
    _strip_code_fences,
    _validate_units,
)
from backend.services.llm_service import call_llm_raw

logger = logging.getLogger("calltracker.call_topics_v5.stage_3")


async def recall_pass(
    ingested: dict,
    existing_units: list[dict],
    *,
    llm: str,
    model: str | None,
) -> dict:
    """Run Stage 3 — find missed units.

    Returns:
        {"new_units": [...], "merged_pool": [stage2 + stage3], "rejected": [...]}
    """
    numbered = _format_numbered_transcript(ingested["lines"])
    user_msg = build_recall_user_message(numbered, existing_units)

    logger.info(
        "[Stage 3] adversarial recall on %d existing units (temp=0)",
        len(existing_units),
    )
    raw = await call_llm_raw(
        CALL_TOPICS_V5_RECALL_SYSTEM,
        user_msg,
        llm,
        max_tokens=8192,
        model=model,
        temperature=0,
    )

    body = _strip_code_fences(raw)
    try:
        parsed = json.loads(body) if body.strip() else []
    except json.JSONDecodeError as e:
        logger.error("[Stage 3] LLM did not return valid JSON: %s", e)
        return {
            "new_units": [],
            "merged_pool": list(existing_units),
            "rejected": [f"recall LLM response not parseable: {e}"],
        }
    if not isinstance(parsed, list):
        if isinstance(parsed, dict):
            for k in ("units", "new_units", "items"):
                if isinstance(parsed.get(k), list):
                    parsed = parsed[k]
                    break
        if not isinstance(parsed, list):
            return {
                "new_units": [],
                "merged_pool": list(existing_units),
                "rejected": [f"recall LLM returned {type(parsed).__name__}, expected array"],
            }

    # Validate against transcript bounds + de-dupe against existing pool
    existing_ids = {u.get("unit_id") for u in existing_units}
    new_units, rejected = _validate_units(parsed, ingested["line_count"])
    new_units = [u for u in new_units if u["unit_id"] not in existing_ids]

    merged_pool = list(existing_units) + new_units
    logger.info(
        "[Stage 3] %d new units found (rejected %d, merged pool size %d)",
        len(new_units), len(rejected), len(merged_pool),
    )
    return {
        "new_units": new_units,
        "merged_pool": merged_pool,
        "rejected": rejected,
    }
