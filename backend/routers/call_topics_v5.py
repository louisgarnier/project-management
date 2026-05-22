"""Endpoints for the call_topics v5 pipeline (EPIC-17).

  POST /api/calls/{call_id}/call-topics-v5/run          → triggers run_pipeline in background
  GET  /api/calls/{call_id}/call-topics-v5/state         → returns {state, payload}
  POST /api/calls/{call_id}/call-topics-v5/resolve-review → applies Stage 11 decisions + runs Stage 12

Feature gate: set CALL_TOPICS_V5_ENABLED=true to enable v5 paths from the
extraction route; otherwise these endpoints still work but the legacy v4
single-shot path is used by default in run_extraction_background.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException

from backend.database.supabase_client import get_client
from backend.services.call_topics_v5.orchestrator import resolve_review, run_pipeline

logger = logging.getLogger("calltracker.call_topics_v5.router")
router = APIRouter(prefix="/api/calls", tags=["call_topics_v5"])


async def _run_pipeline_safely(call_id: str) -> None:
    """Wrap run_pipeline so background-task failures don't crash silently."""
    try:
        await run_pipeline(call_id)
    except Exception:
        logger.exception("[v5 pipeline] uncaught error for call %s", call_id)


@router.post("/{call_id}/call-topics-v5/run", status_code=202)
def trigger_pipeline(call_id: str, background_tasks: BackgroundTasks):
    """Trigger the v5 pipeline. Returns 202 + current state."""
    client = get_client()
    row = client.table("calls").select("call_topics_v5_state, transcript").eq("id", call_id).execute().data
    if not row:
        raise HTTPException(status_code=404, detail="call not found")
    if not (row[0].get("transcript") or "").strip():
        raise HTTPException(status_code=422, detail="call has no transcript")
    current_state = row[0].get("call_topics_v5_state")
    if current_state == "running":
        raise HTTPException(status_code=409, detail="pipeline already running")

    # Reset state + clear payload before starting
    client.table("calls").update({
        "call_topics_v5_state": "running",
        "call_topics_v5_payload": None,
    }).eq("id", call_id).execute()
    background_tasks.add_task(_run_pipeline_safely, call_id)
    return {"state": "running", "call_id": call_id}


@router.get("/{call_id}/call-topics-v5/state")
def get_state(call_id: str):
    client = get_client()
    row = client.table("calls").select("call_topics_v5_state, call_topics_v5_payload").eq("id", call_id).execute().data
    if not row:
        raise HTTPException(status_code=404, detail="call not found")
    return {
        "state": row[0].get("call_topics_v5_state") or "idle",
        "payload": row[0].get("call_topics_v5_payload"),
    }


@router.post("/{call_id}/call-topics-v5/resolve-review")
async def resolve_review_endpoint(call_id: str, decisions: dict):
    """Apply user's Stage 11 decisions → run Stage 12 → state = done."""
    try:
        payload = await resolve_review(call_id, decisions)
        return {"state": "done", "v4_output_topic_count": len(payload.get("v4_output") or [])}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
