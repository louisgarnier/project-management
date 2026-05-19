"""Accumulator: runs at project_updates commit (Story 15.7).

For every topic_updates row touched in the current call:
1. (Lifecycle stamping happens inside _persist_topic_update — accumulator
   does NOT re-stamp here, just kicks off chronology gen.)
2. Trigger chronology_service.generate_chronology_cell per topic, with
   bounded concurrency.

Per-topic errors are caught and logged so one bad topic doesn't block the
others. Returns a small stats dict for the caller.
"""

import asyncio
import logging
import time

from backend.services.chronology_service import generate_chronology_cell

logger = logging.getLogger("topic_updates_accumulator")

MAX_CONCURRENT_LLM = 8


async def accumulate_into_project_state(call_id: str, db) -> dict:
    """Run accumulator side effects for all topics touched in this call.

    Returns {"topics_touched": N, "wall_clock_ms": M}. Never raises.
    Per-topic chronology failures are caught and logged.
    """
    start = time.time()
    rows = (
        db.table("topic_updates")
        .select("id, topic_id, call_id")
        .eq("call_id", call_id)
        .execute()
        .data
    )
    if not rows:
        logger.info(f"⚠️  [Accumulator] no topic_updates rows for call={call_id}")
        wall_ms = int((time.time() - start) * 1000)
        return {"topics_touched": 0, "wall_clock_ms": wall_ms}

    sem = asyncio.Semaphore(MAX_CONCURRENT_LLM)

    async def _one(row):
        async with sem:
            try:
                await generate_chronology_cell(row["topic_id"], call_id, db)
            except Exception:  # noqa: BLE001
                logger.exception(
                    f"❌ [Accumulator] chronology failed for topic={row['topic_id']}"
                )

    await asyncio.gather(*[_one(r) for r in rows])
    wall_ms = int((time.time() - start) * 1000)
    logger.info(
        f"✅ [Accumulator] call={call_id} topics_touched={len(rows)} "
        f"wall_clock_ms={wall_ms}"
    )
    return {"topics_touched": len(rows), "wall_clock_ms": wall_ms}
