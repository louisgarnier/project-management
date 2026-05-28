from typing import Optional, Literal

from backend.database.supabase_client import get_client
from backend.services.topic_lineage import (
    get_topic_lineage,
    get_lineage_topic_updates,
)
from backend.services.topics_service import (
    save_topics, validate_call, generate_brief,
    list_project_topics, list_call_topics, extract_call_topics, aggregate_topics,
    get_pending_topics, save_match_groups, validate_project_updates,
    run_extraction_background,
    list_topics_timeline,
    list_topics_prior_to_call, rollback_to_stage,
    TopicUpdate,
    _stamp_item_ids, _status_rollup,
)
from backend.services.finalized_topics_service import (
    FinalizedTopic,
    load_finalized_topics,
    save_finalized_topics,
)
from backend.services.project_topic_state import get_project_topic_state
from backend.services.task_grouping_service import run_task_grouping
from backend.services.task_match_persistence import (
    TaskMatchGroup,
    load_task_match_groups,
    save_task_match_groups,
)
from backend.utils.logger import get_logger
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from openai import APIStatusError as OpenAIStatusError
from pydantic import BaseModel as PydanticBaseModel

router = APIRouter(prefix="/api", tags=["topics"])
logger = get_logger("topics_router")



@router.post("/calls/{call_id}/topics/extract_call")
async def extract_call(call_id: str, background_tasks: BackgroundTasks):
    """Step 1: fire-and-forget extraction. Result saved to calls.extraction_cache."""
    logger.info(f"📥 [Topics] Background extraction requested: call={call_id}")
    db = get_client()

    # Check if already processing
    call_row = db.table("calls").select("extraction_status").eq("id", call_id).execute().data
    if not call_row:
        raise HTTPException(status_code=404, detail=f"Call {call_id} not found")

    status = call_row[0].get("extraction_status", "idle")
    if status == "processing":
        logger.info(f"⚠️ [Topics] Extraction already in progress: call={call_id}")
        return {"status": "processing"}

    # Mark as processing and fire background task
    db.table("calls").update({"extraction_status": "processing", "extraction_cache": None}).eq("id", call_id).execute()
    background_tasks.add_task(run_extraction_background, call_id)

    logger.info(f"✅ [Topics] Background extraction started: call={call_id}")
    return {"status": "processing"}


class AggregatePayload(PydanticBaseModel):
    topics: list[dict]


@router.post("/calls/{call_id}/topics/aggregate")
async def aggregate(call_id: str, payload: AggregatePayload):
    """Step 2: save pending call topics → advance to project_matching (or auto-advance Call 1)."""
    logger.info(
        f"📥 [Topics] Step-2 aggregate requested: call={call_id}, "
        f"input_topics={len(payload.topics)}"
    )
    try:
        result = await aggregate_topics(call_id, payload.topics)
        if result.get("auto_advanced"):
            logger.info(f"✅ [Topics] Auto-advanced Call 1: {call_id}")
        else:
            logger.info(f"✅ [Topics] Saved pending topics → project_matching: {call_id}")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except OpenAIStatusError as e:
        if e.status_code in (413, 429) or "rate_limit" in str(e).lower():
            logger.warning(f"⚠️ [Topics] LLM rate limit on Step-2: {e}")
            raise HTTPException(
                status_code=429,
                detail="Transcript too large for current LLM tier — wait a moment and try again",
            )
        logger.exception(f"❌ [Topics] Step-2 aggregation failed: {e}")
        raise HTTPException(status_code=500, detail="Aggregation failed")
    except Exception as e:
        logger.exception(f"❌ [Topics] Step-2 aggregation failed: {e}")
        raise HTTPException(status_code=500, detail="Aggregation failed")


@router.post("/calls/{call_id}/topics")
async def save(call_id: str, topics: list[TopicUpdate]):
    logger.info(f"📥 [Topics] Save requested: call={call_id}, count={len(topics)}")
    try:
        result = await save_topics(call_id, topics)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"❌ [Topics] Save failed: {e}")
        raise HTTPException(status_code=500, detail="Topic save failed")

    # After saving topics:
    # 1. Mark this call's artifacts stale
    # 2. Roll back any later calls that are past call_topics (their data is now stale)
    try:
        db = get_client()
        call_row = db.table("calls").select("kanban_stage, project_id, created_at").eq("id", call_id).execute().data
        if call_row:
            # Mark this call's artifacts stale
            artifacts = db.table("artifacts").select("id").eq("call_id", call_id).execute().data
            artifact_ids = [a["id"] for a in artifacts]
            if artifact_ids:
                db.table("artifacts").update({"status": "stale"}).in_("id", artifact_ids).execute()
                logger.info(f"⚠️ [Topics] Marked {len(artifact_ids)} artifacts stale: {call_id}")

            # Roll back later calls that are past call_topics
            project_id = call_row[0]["project_id"]
            created_at = call_row[0]["created_at"]
            _STAGE_ORDER = ["transcript", "call_topics", "topic_confirmation", "project_matching", "project_updates", "artifacts", "done"]
            later_calls = (
                db.table("calls")
                .select("id, kanban_stage")
                .eq("project_id", project_id)
                .gt("created_at", created_at)
                .order("created_at")
                .execute()
                .data
            )
            for lc in later_calls:
                rollback_to_stage(lc["id"], "call_topics")
                logger.info(f"⚠️ [Topics] Rolled back later call {lc['id']} to call_topics after topic edit on {call_id}")
    except Exception as stale_err:
        logger.warning(f"⚠️ [Topics] Post-save cascade failed (non-fatal): {stale_err}")

    return result


@router.post("/calls/{call_id}/topics/validate")
async def validate(call_id: str):
    logger.info(f"📥 [Topics] Validate requested: call={call_id}")
    try:
        result = await validate_call(call_id)
        logger.info(f"✅ [Topics] Call validated: {call_id}")
        return result
    except ValueError as e:
        msg = str(e)
        if msg == "no_topics":
            raise HTTPException(status_code=422, detail="No topics saved for this call")
        if msg.startswith("unacknowledged_topics:"):
            ids = msg.split(":")[1].split(",")
            raise HTTPException(
                status_code=422,
                detail={"error": "unacknowledged_topics", "ids": ids},
            )
        raise HTTPException(status_code=422, detail=msg)


@router.get("/calls/{call_id}/topics/by-call")
async def list_topics_by_call(call_id: str):
    """Return topics that have a topic_update for this specific call (call-scoped view)."""
    logger.info(f"📥 [Topics] Call-scoped topics requested: call={call_id}")
    result = await list_call_topics(call_id)
    logger.info(f"✅ [Topics] Returned {len(result)} call-scoped topics")
    return result


@router.get("/calls/{call_id}/topics/pending")
async def get_pending(call_id: str):
    """Return validated call topics stored between call_topics and project_matching stages."""
    logger.info(f"📥 [Topics] Pending topics requested: call={call_id}")
    try:
        result = await get_pending_topics(call_id)
        logger.info(f"✅ [Topics] Returned {len(result)} pending topics")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class TaskRefIn(PydanticBaseModel):
    call_topic_name: str | None = None
    project_topic_id: str | None = None
    task_id: str | None = None


class TaskMatchGroupIn(PydanticBaseModel):
    kind: Literal["binding", "topic_merge"] = "binding"
    call_task_refs: list[TaskRefIn] = []
    project_task_refs: list[TaskRefIn] = []
    target_topic_name: str | None = None  # EPIC-19


@router.post("/calls/{call_id}/topics/save-matches", status_code=200)
async def save_matches(
    call_id: str,
    groups: list[TaskMatchGroupIn],
    draft: bool = Query(default=False),
):
    """Save manual match groups. If draft=True, skips kanban_stage advance."""
    logger.info(f"📥 [Topics] Save matches: call={call_id}, groups={len(groups)}, draft={draft}")
    try:
        result = await save_match_groups(call_id, [g.model_dump() for g in groups], draft=draft)
        if not draft:
            logger.info(f"✅ [Topics] Saved match groups; project_updates stage advanced")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"❌ [Topics] Save matches failed: {e}")
        raise HTTPException(status_code=500, detail="Save matches failed")


class PromotePayload(PydanticBaseModel):
    topic_id: str


@router.post("/calls/{call_id}/topics/promote-not-discussed", status_code=200)
async def promote_not_discussed(call_id: str, payload: PromotePayload):
    """Persist a not-discussed topic promotion as a ptid-only match group so
    subsequent merge re-runs (or page refreshes) keep the topic as an Updated
    Topic instead of rebuilding it as not-discussed.
    """
    logger.info(f"📥 [Topics] Promote not-discussed: call={call_id}, topic={payload.topic_id}")
    db = get_client()
    # Idempotent: if a group for this ptid already exists, skip
    existing = (
        db.table("topic_match_groups")
        .select("project_topic_ids, call_topic_names")
        .eq("call_id", call_id)
        .execute()
        .data
    )
    for g in existing:
        ptids = g.get("project_topic_ids") or []
        cnames = g.get("call_topic_names") or []
        if payload.topic_id in ptids and not cnames:
            logger.info(f"✅ [Topics] Promote no-op — ptid-only group already exists for {payload.topic_id}")
            return {"ok": True, "created": False}
    db.table("topic_match_groups").insert({
        "call_id": call_id,
        "project_topic_ids": [payload.topic_id],
        "call_topic_names": [],
    }).execute()
    logger.info(f"✅ [Topics] Promoted topic {payload.topic_id} as ptid-only match group")
    return {"ok": True, "created": True}


@router.get("/calls/{call_id}/topics/match-groups")
async def get_match_groups(call_id: str):
    """Return saved match groups for a call with project topic names resolved."""
    logger.info(f"📥 [Topics] Match groups requested: call={call_id}")
    db = get_client()

    groups = (
        db.table("topic_match_groups")
        .select("id, kind, call_task_refs, project_task_refs, call_topic_names, project_topic_ids")
        .eq("call_id", call_id)
        .execute()
        .data
    ) or []

    result = []
    for g in groups:
        ptids = g.get("project_topic_ids") or []
        names = []
        for ptid in ptids:
            row = db.table("topics").select("name").eq("id", ptid).execute().data
            if row:
                names.append(row[0]["name"])
        result.append({
            "id": g.get("id"),
            "kind": g.get("kind", "binding"),
            "call_task_refs": g.get("call_task_refs") or [],
            "project_task_refs": g.get("project_task_refs") or [],
            "project_topic_ids": ptids,
            "project_topic_names": names,
            "call_topic_names": g.get("call_topic_names", []),
        })

    logger.info(f"✅ [Topics] Returned {len(result)} match groups")
    return result




# ─────────────────────────────────────────────────────────────────────────────
# EPIC-20 Stage 1: Topic confirmation
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/calls/{call_id}/topic-confirmation")
async def get_topic_confirmation(call_id: str):
    """Stage 1 payload: existing project topics + v5 new-topic candidates + saved finalized.

    - existing       : project topics with progression history (project_topic_state)
    - new_candidates : v5-introduced topic names for this call (synthesized_topics
                       where new_topic=true)
    - finalized      : already-saved finalized list (empty on first visit)
    """
    logger.info(f"📥 [Topics] Stage 1 payload requested: call={call_id}")
    db = get_client()

    call_row = (
        db.table("calls")
        .select("project_id, call_topics_v5_payload")
        .eq("id", call_id)
        .execute()
        .data
    )
    if not call_row:
        raise HTTPException(status_code=404, detail=f"Call {call_id} not found")
    project_id = call_row[0]["project_id"]

    # Existing topics (project history)
    existing = []
    try:
        for t in get_project_topic_state(project_id, db=db):
            existing.append({
                "topic_id": t["topic_id"],
                "name": t["name"],
                "tasks_count": len(t.get("tasks") or []),
            })
    except Exception as e:
        logger.warning(f"⚠️ [Topics] Stage 1 existing-topics load failed: {e}")

    # v5 new-topic candidates from this call
    v5_payload = call_row[0].get("call_topics_v5_payload") or {}
    synthesized = v5_payload.get("synthesized_topics") or []
    existing_names_lower = {(t["name"] or "").lower() for t in existing}
    new_candidates = []
    for s in synthesized:
        name = (s.get("topic_name") or "").strip()
        if not name:
            continue
        # v5 'new_topic' flag, OR fallback: a name not present in project_topic_state
        is_new = s.get("new_topic") or (name.lower() not in existing_names_lower)
        if is_new:
            new_candidates.append({
                "name": name,
                "v5_cluster_id": s.get("registry_id") or s.get("cluster_id"),
                "task_count": len(s.get("tasks") or []),
            })

    # Existing finalized list (empty on first visit)
    try:
        finalized = load_finalized_topics(call_id, db=db)
    except Exception as e:
        logger.warning(f"⚠️ [Topics] Stage 1 load_finalized failed (migration 037 not applied?): {e}")
        finalized = []

    logger.info(
        f"✅ [Topics] Stage 1 payload: {len(existing)} existing, "
        f"{len(new_candidates)} new candidates, {len(finalized)} already-finalized"
    )
    return {"existing": existing, "new_candidates": new_candidates, "finalized": finalized}


class TopicConfirmationSavePayload(PydanticBaseModel):
    topics: list[dict]  # each: {name, source, topic_id?, v5_cluster_id?, _original_name?}


@router.post("/calls/{call_id}/topic-confirmation/save")
async def save_topic_confirmation(call_id: str, payload: TopicConfirmationSavePayload):
    """Persist the finalized topic list AND propagate renames to topic_registry.

    Renames are detected by comparing _original_name (sent by client) vs name.
    Renaming an 'existing' entry updates the canonical name in topic_registry
    (EPIC-20 decision: immediate propagation, not per-call alias).
    """
    logger.info(f"📥 [Topics] Stage 1 save: call={call_id}, {len(payload.topics)} topics")
    db = get_client()

    renames_applied = 0
    for t in payload.topics:
        orig = (t.get("_original_name") or "").strip()
        new_name = (t.get("name") or "").strip()
        topic_id = t.get("topic_id")
        if orig and topic_id and new_name and orig != new_name:
            try:
                # Update topics.name (the operational table); topic_registry is
                # the vocabulary table — update it too if the row exists.
                db.table("topics").update({"name": new_name}).eq("id", topic_id).execute()
                # topic_registry: lookup by current (orig) name in this project,
                # update if present (operational topic_id != registry id, names align).
                call_row = db.table("calls").select("project_id").eq("id", call_id).execute().data
                if call_row:
                    proj_id = call_row[0]["project_id"]
                    db.table("topic_registry").update({"name": new_name}).eq(
                        "project_id", proj_id
                    ).ilike("name", orig).execute()
                renames_applied += 1
                logger.info(f"🗄️ [Topics] Renamed topic {topic_id}: {orig!r} → {new_name!r}")
            except Exception as e:
                logger.warning(f"⚠️ [Topics] Rename failed for {topic_id}: {e}")

    # Build clean finalized rows
    clean: list[FinalizedTopic] = []
    for t in payload.topics:
        clean.append(FinalizedTopic(
            name=(t["name"] or "").strip(),
            source=t.get("source", "existing"),
            topic_id=t.get("topic_id"),
            v5_cluster_id=t.get("v5_cluster_id"),
        ))
    result = save_finalized_topics(call_id, clean, db=db)

    # Advance kanban stage: topic_confirmation → project_matching
    try:
        db.table("calls").update({"kanban_stage": "project_matching"}).eq("id", call_id).execute()
    except Exception as e:
        logger.warning(f"⚠️ [Topics] Advance to project_matching failed: {e}")

    logger.info(f"✅ [Topics] Stage 1 saved: {result['saved']} topics, {renames_applied} renames")
    return {"saved": result["saved"], "renames_applied": renames_applied}


# ─────────────────────────────────────────────────────────────────────────────
# EPIC-20 Stage 2: Task grouping (cluster + route + drag UX)
# ─────────────────────────────────────────────────────────────────────────────


def _collect_tasks_for_grouping(db, call_id: str, finalized: list[dict]) -> tuple[list[dict], list[dict]]:
    """Build the prev/new task lists for Stage 2.

    Returns (prev_tasks, new_tasks). Each task has:
      - id: prefixed local identifier ("prev:<uuid>" or "new:<uuid>")
      - text: task text
      - origin: 'previous' | 'new'
      - _task_id / _topic_id (prev) | _unit_id (new): raw identifiers for routing back
      - _topic_name: source topic name (for context)
    """
    prev_tasks: list[dict] = []
    for ft in finalized:
        if ft.get("source") != "existing" or not ft.get("topic_id"):
            continue
        try:
            state_rows = (
                db.table("project_topic_state")
                .select("tasks")
                .eq("topic_id", ft["topic_id"])
                .execute()
                .data
            )
        except Exception:
            state_rows = []
        for sr in state_rows or []:
            for pt in (sr.get("tasks") or []):
                tid = pt.get("task_id")
                if not tid:
                    continue
                prev_tasks.append({
                    "id": f"prev:{tid}",
                    "text": (pt.get("task") or "").strip(),
                    "origin": "previous",
                    "_task_id": tid,
                    "_topic_id": ft["topic_id"],
                    "_topic_name": ft["name"],
                })

    call_row = db.table("calls").select("call_topics_v5_payload, extraction_cache").eq("id", call_id).execute().data
    v5 = (call_row[0] or {}).get("call_topics_v5_payload") or {} if call_row else {}
    # Prefer synthesized_topics (task-level, post stage 8) over raw atomic_units
    new_tasks: list[dict] = []
    for st in (v5.get("synthesized_topics") or []):
        topic_name = (st.get("topic_name") or "").strip()
        for tk in (st.get("tasks") or []):
            tid = tk.get("task_id")
            if not tid:
                continue
            new_tasks.append({
                "id": f"new:{tid}",
                "text": (tk.get("task") or "").strip(),
                "origin": "new",
                "_unit_id": tid,
                "_topic_name": topic_name,
            })
    # Fallback: if synthesized_topics is empty, pull from extraction_cache (v4-shape)
    if not new_tasks:
        for st in ((call_row[0] or {}).get("extraction_cache") or []) if call_row else []:
            for tk in (st.get("tasks") or []):
                tid = tk.get("task_id")
                if not tid:
                    continue
                new_tasks.append({
                    "id": f"new:{tid}",
                    "text": (tk.get("task") or "").strip(),
                    "origin": "new",
                    "_unit_id": tid,
                    "_topic_name": (st.get("name") or "").strip(),
                })
    return prev_tasks, new_tasks


@router.get("/calls/{call_id}/task-grouping/state")
async def get_task_grouping_state(call_id: str):
    """Stage 2 state for the UI: topics, all tasks (prev+new), existing groups, orphans."""
    logger.info(f"📥 [TaskGrouping] state requested: call={call_id}")
    db = get_client()
    finalized = load_finalized_topics(call_id, db=db)
    topics_out = [{"id": t["id"], "name": t["name"]} for t in finalized]

    prev_tasks, new_tasks = _collect_tasks_for_grouping(db, call_id, finalized)
    all_tasks = prev_tasks + new_tasks
    tasks_out = [
        {"id": t["id"], "text": t["text"], "origin": t["origin"], "topic_name": t.get("_topic_name", "")}
        for t in all_tasks
    ]

    # Load existing groups → convert to local prefixed IDs
    groups_db = load_task_match_groups(call_id, db=db)
    groups_out: list[dict] = []
    assigned: set[str] = set()
    for g in groups_db:
        task_ids: list[str] = []
        for r in (g.get("call_task_refs") or []):
            tid = r.get("task_id")
            if tid:
                task_ids.append(f"new:{tid}")
        for r in (g.get("project_task_refs") or []):
            tid = r.get("task_id")
            if tid:
                task_ids.append(f"prev:{tid}")
        assigned.update(task_ids)
        groups_out.append({
            "id": g.get("id"),
            "finalized_topic_id": g.get("finalized_topic_id"),
            "group_kind": g.get("group_kind") or "new_only",
            "task_ids": task_ids,
        })
    orphans = [t["id"] for t in all_tasks if t["id"] not in assigned]
    logger.info(
        f"✅ [TaskGrouping] state: {len(topics_out)} topics, {len(all_tasks)} tasks, "
        f"{len(groups_out)} groups, {len(orphans)} orphans"
    )
    return {"topics": topics_out, "tasks": tasks_out, "groups": groups_out, "orphans": orphans}


def _resolve_project_default_llm(db, call_id: str) -> tuple[str, str | None]:
    """Look up project default_llm / default_model. Fallback: openrouter sonnet."""
    try:
        call_row = db.table("calls").select("project_id").eq("id", call_id).single().execute().data or {}
        proj_id = call_row.get("project_id")
        if proj_id:
            proj = db.table("projects").select("default_llm, default_model").eq("id", proj_id).single().execute().data or {}
            llm = proj.get("default_llm") or "openrouter"
            model = proj.get("default_model") or "anthropic/claude-sonnet-4-6"
            return llm, model
    except Exception as e:
        logger.warning(f"⚠️ [TaskGrouping] LLM lookup failed: {e}")
    return "openrouter", "anthropic/claude-sonnet-4-6"


@router.post("/calls/{call_id}/task-grouping/run")
async def run_task_grouping_endpoint(call_id: str):
    """Stage 2 LLM cluster+route. Persists groups as draft topic_match_groups."""
    logger.info(f"📥 [TaskGrouping] LLM run: call={call_id}")
    db = get_client()
    finalized = load_finalized_topics(call_id, db=db)
    if not finalized:
        raise HTTPException(status_code=400, detail="No finalized topics — complete Stage 1 first")
    topic_names = [t["name"] for t in finalized]
    ft_by_name = {t["name"]: t["id"] for t in finalized}

    prev_tasks, new_tasks = _collect_tasks_for_grouping(db, call_id, finalized)
    all_tasks = prev_tasks + new_tasks
    if not all_tasks:
        return {"groups": [], "unassigned": [], "rejected": ["no tasks to group"]}

    llm, model = _resolve_project_default_llm(db, call_id)
    result = await run_task_grouping(topic_names, all_tasks, llm=llm, model=model)

    # Convert LLM output → TaskMatchGroup rows and persist as draft
    tasks_by_id = {t["id"]: t for t in all_tasks}
    groups_to_save: list[TaskMatchGroup] = []
    for g in result["groups"]:
        ftid = ft_by_name.get(g["target_topic"])
        if not ftid:
            continue
        call_refs, proj_refs = [], []
        for tid in g["task_ids"]:
            t = tasks_by_id.get(tid)
            if not t:
                continue
            if t["origin"] == "new":
                call_refs.append({"task_id": t["_unit_id"]})
            else:
                proj_refs.append({"project_topic_id": t["_topic_id"], "task_id": t["_task_id"]})
        if not call_refs and not proj_refs:
            continue
        kind = "mixed" if (call_refs and proj_refs) else ("new_only" if call_refs else "old_only")
        groups_to_save.append(TaskMatchGroup(
            finalized_topic_id=ftid,
            group_kind=kind,
            call_task_refs=call_refs,
            project_task_refs=proj_refs,
        ))
    save_task_match_groups(call_id, groups_to_save, db=db)
    logger.info(
        f"✅ [TaskGrouping] LLM produced {len(result['groups'])} groups, "
        f"{len(result['unassigned'])} unassigned, persisted {len(groups_to_save)}"
    )
    return {
        "groups_count": len(groups_to_save),
        "unassigned": result["unassigned"],
        "rejected": result["rejected"],
    }


class TaskGroupingSavePayload(PydanticBaseModel):
    groups: list[dict]


@router.post("/calls/{call_id}/task-grouping/save")
async def save_task_grouping_endpoint(call_id: str, payload: TaskGroupingSavePayload):
    """Persist user-edited groups (after drag-drop). Idempotent (delete-then-insert).

    Optionally advances kanban stage to project_updates when called with no orphans
    and all task_ids are placed in a group.
    """
    logger.info(f"📥 [TaskGrouping] save: call={call_id}, {len(payload.groups)} groups")
    db = get_client()
    finalized = load_finalized_topics(call_id, db=db)
    if not finalized:
        raise HTTPException(status_code=400, detail="No finalized topics")
    prev_tasks, new_tasks = _collect_tasks_for_grouping(db, call_id, finalized)
    tasks_by_id = {t["id"]: t for t in prev_tasks + new_tasks}
    all_task_ids = set(tasks_by_id.keys())
    placed: set[str] = set()

    groups_to_save: list[TaskMatchGroup] = []
    for g in payload.groups:
        ftid = g.get("finalized_topic_id")
        if not ftid:
            continue
        call_refs, proj_refs = [], []
        for tid in (g.get("task_ids") or []):
            t = tasks_by_id.get(tid)
            if not t:
                continue
            if t["origin"] == "new":
                call_refs.append({"task_id": t["_unit_id"]})
            else:
                proj_refs.append({"project_topic_id": t["_topic_id"], "task_id": t["_task_id"]})
            placed.add(tid)
        if not call_refs and not proj_refs:
            continue
        kind = "mixed" if (call_refs and proj_refs) else ("new_only" if call_refs else "old_only")
        groups_to_save.append(TaskMatchGroup(
            id=g.get("id"),
            finalized_topic_id=ftid,
            group_kind=kind,
            call_task_refs=call_refs,
            project_task_refs=proj_refs,
        ))
    save_task_match_groups(call_id, groups_to_save, db=db)

    orphans = sorted(all_task_ids - placed)
    advanced = False
    if not orphans and groups_to_save:
        try:
            db.table("calls").update({"kanban_stage": "project_updates"}).eq("id", call_id).execute()
            advanced = True
        except Exception as e:
            logger.warning(f"⚠️ [TaskGrouping] stage advance failed: {e}")

    logger.info(
        f"✅ [TaskGrouping] saved {len(groups_to_save)} groups, {len(orphans)} orphans, advanced={advanced}"
    )
    return {"saved": len(groups_to_save), "orphans": orphans, "advanced": advanced}


@router.post("/calls/{call_id}/topics/validate-updates")
async def validate_updates(call_id: str, topics: list[dict]):
    """Save reviewed merged topics and advance to artifacts."""
    logger.info(f"📥 [Topics] Validate updates: call={call_id}, count={len(topics)}")
    try:
        result = await validate_project_updates(call_id, topics)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception(f"❌ [Topics] Validate updates failed: {e}")
        raise HTTPException(status_code=500, detail="Validate updates failed")


@router.get("/projects/{project_id}/topics")
async def list_topics(project_id: str):
    logger.info(f"📥 [Topics] Dashboard requested: project={project_id}")
    db = get_client()
    result = await list_project_topics(project_id, db)
    logger.info(f"✅ [Topics] Returned {len(result)} topics")
    return result


@router.get("/projects/{project_id}/topics/prior-to-call/{call_id}")
async def get_topics_prior_to_call(project_id: str, call_id: str):
    """Return project topics that existed before the given call (timestamp-scoped)."""
    logger.info(f"📥 [Topics] Prior-to-call requested: project={project_id}, call={call_id}")
    db = get_client()
    try:
        result = list_topics_prior_to_call(call_id, project_id, db)
        logger.info(f"✅ [Topics] Prior-to-call: {len(result)} topics")
        return result
    except Exception as e:
        logger.error(f"❌ [Topics] Prior-to-call failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to load prior topics")


@router.get("/projects/{project_id}/topics/timeline")
async def get_topics_timeline(project_id: str):
    """Return the full topic x call matrix for the timeline grid."""
    logger.info(f"📥 [Topics] Timeline requested: project={project_id}")
    db = get_client()
    try:
        result = list_topics_timeline(project_id, db)
        logger.info(
            f"✅ [Topics] Timeline: {len(result['calls'])} calls, {len(result['topics'])} topics"
        )
        return result
    except Exception as e:
        logger.error(f"❌ [Topics] Timeline failed: project={project_id} — {e}")
        raise HTTPException(status_code=500, detail="Failed to load topics timeline")


@router.delete("/calls/{call_id}/topics/{topic_id}", status_code=204)
async def delete_topic_from_call(call_id: str, topic_id: str):
    """
    Remove a topic from one specific call.
    - Deletes the topic_update row for (topic_id, call_id).
    - Recalculates topics.calls_open.
    - Deletes the topics row entirely if no updates remain (orphan).
    - Updates first_raised_call_id if it pointed at this call.
    Does NOT touch topic_updates from other calls.
    """
    logger.info(f"📥 [Topics] Delete topic {topic_id} from call {call_id}")
    db = get_client()

    # 1. Delete this call's update for the topic
    db.table("topic_updates").delete().eq("topic_id", topic_id).eq("call_id", call_id).execute()

    # 2. Check remaining updates across all calls
    remaining = (
        db.table("topic_updates")
        .select("call_id, status, created_at")
        .eq("topic_id", topic_id)
        .order("created_at")
        .execute()
        .data
    )

    if not remaining:
        # No updates left anywhere — delete the topic row entirely
        db.table("topics").delete().eq("id", topic_id).execute()
        logger.info(f"🗄️ [DB] Deleted orphan topic {topic_id} (no remaining updates)")
        return

    # 3. Recalculate calls_open
    calls_open = sum(1 for r in remaining if r["status"] in ("open", "in_progress"))
    db.table("topics").update({"calls_open": calls_open}).eq("id", topic_id).execute()

    # 4. Fix first_raised_call_id if it pointed at the deleted call
    topic_row = db.table("topics").select("first_raised_call_id").eq("id", topic_id).execute().data
    if topic_row and topic_row[0]["first_raised_call_id"] == call_id:
        # Assign to the earliest remaining call that has an update
        new_first = remaining[0]["call_id"]  # already ordered by created_at asc
        db.table("topics").update({"first_raised_call_id": new_first}).eq("id", topic_id).execute()
        logger.info(f"🗄️ [DB] Updated first_raised_call_id for topic {topic_id} → {new_first}")

    logger.info(f"✅ [Topics] Removed topic {topic_id} from call {call_id}, calls_open={calls_open}")


# --------------------------------------------------------------------------- #
# Story 10.3 — Topic Evidence API
# --------------------------------------------------------------------------- #


class LineageNode(PydanticBaseModel):
    topic_id: str
    name: str
    archived: bool
    merged_into_topic_id: str | None


class EvidenceRawExtract(PydanticBaseModel):
    summary: str
    follow_up_items: list[str]
    decisions: list[str]


class EvidenceMatchGroup(PydanticBaseModel):
    project_topic_ids: list[str]
    call_topic_names: list[str]


class EvidenceVerification(PydanticBaseModel):
    discussed: bool | None
    transcript_excerpt: str | None
    reasoning: str
    error: str | None = None


class EvidenceCall(PydanticBaseModel):
    call_id: str
    call_title: str
    call_date: str | None
    source_topic_id: str
    source_topic_name: str
    transcript_excerpt: str | None
    merged_summary: str
    follow_up_items: list[str]
    decisions: list[str]
    status: str
    raw_extract: EvidenceRawExtract | None
    match_group: EvidenceMatchGroup | None
    not_discussed_verification: EvidenceVerification | None
    is_not_discussed: bool


class TopicEvidenceResponse(PydanticBaseModel):
    topic_id: str
    topic_name: str
    lineage: list[LineageNode]
    calls: list[EvidenceCall]


@router.get("/topics/{topic_id}/evidence", response_model=TopicEvidenceResponse)
async def get_topic_evidence(topic_id: str):
    """Return the ancestor-aware per-call evidence trail for a topic.

    Used by the frontend evidence panel (Story 10.4). Walks the lineage chain via
    topics.merged_into_topic_id, collects topic_updates rows across all ancestors,
    and enriches each row with call metadata, the original raw pending_topics
    extract, the saved match group, and any not-discussed verification result.
    """
    logger.info(f"📥 [Topics] Evidence requested: topic={topic_id}")
    db = get_client()

    # 1. Fetch the target topic — 404 if missing
    topic_rows = (
        db.table("topics")
        .select("id, name, archived, merged_into_topic_id")
        .eq("id", topic_id)
        .execute()
        .data
    )
    if not topic_rows:
        logger.info(f"⚠️ [Topics] Evidence 404: topic {topic_id} not found")
        raise HTTPException(status_code=404, detail=f"Topic {topic_id} not found")
    topic_row = topic_rows[0]

    # 2. Lineage
    lineage_raw = get_topic_lineage(topic_id, db)
    lineage = [
        LineageNode(
            topic_id=n["id"],
            name=n["name"],
            archived=bool(n.get("archived", False)),
            merged_into_topic_id=n.get("merged_into_topic_id"),
        )
        for n in lineage_raw
    ]

    # 3. Ancestor-inclusive topic_updates rows (chronological)
    update_rows = get_lineage_topic_updates(topic_id, db)

    # Caches to avoid N+1 lookups
    call_cache: dict[str, dict | None] = {}
    match_group_cache: dict[str, list[dict]] = {}

    def _load_call(call_id: str) -> dict | None:
        if call_id in call_cache:
            return call_cache[call_id]
        rows = (
            db.table("calls")
            .select("id, title, created_at, pending_topics, verification_cache")
            .eq("id", call_id)
            .execute()
            .data
        )
        call_cache[call_id] = rows[0] if rows else None
        return call_cache[call_id]

    def _load_match_groups(call_id: str) -> list[dict]:
        if call_id in match_group_cache:
            return match_group_cache[call_id]
        rows = (
            db.table("topic_match_groups")
            .select("project_topic_ids, call_topic_names")
            .eq("call_id", call_id)
            .execute()
            .data
        )
        match_group_cache[call_id] = rows or []
        return match_group_cache[call_id]

    def _find_raw_extract(pending_topics, source_name: str) -> EvidenceRawExtract | None:
        if not pending_topics or not isinstance(pending_topics, list):
            return None
        needle = (source_name or "").strip().lower()
        if not needle:
            return None
        for pt in pending_topics:
            if not isinstance(pt, dict):
                continue
            name = (pt.get("name") or "").strip().lower()
            if name == needle:
                return EvidenceRawExtract(
                    summary=pt.get("summary", "") or "",
                    follow_up_items=pt.get("follow_up_items", []) or [],
                    decisions=pt.get("decisions", []) or [],
                )
        return None

    def _find_match_group(call_id: str, source_tid: str) -> EvidenceMatchGroup | None:
        for g in _load_match_groups(call_id):
            ptids = g.get("project_topic_ids") or []
            if source_tid in ptids:
                return EvidenceMatchGroup(
                    project_topic_ids=ptids,
                    call_topic_names=g.get("call_topic_names") or [],
                )
        return None

    def _find_verification(verification_cache, source_tid: str) -> EvidenceVerification | None:
        if not isinstance(verification_cache, dict):
            return None
        entry = verification_cache.get(source_tid)
        if not isinstance(entry, dict):
            return None
        discussed_raw = entry.get("discussed")
        return EvidenceVerification(
            discussed=discussed_raw if isinstance(discussed_raw, bool) else None,
            transcript_excerpt=entry.get("transcript_excerpt"),
            reasoning=entry.get("reasoning", "") or "",
            error=entry.get("error"),
        )

    calls: list[EvidenceCall] = []
    for row in update_rows:
        call_id = row["call_id"]
        source_tid = row["source_topic_id"]
        source_name = row["source_topic_name"]
        call = _load_call(call_id) or {}

        calls.append(EvidenceCall(
            call_id=call_id,
            call_title=row.get("call_title") or call_id,
            call_date=call.get("created_at"),
            source_topic_id=source_tid,
            source_topic_name=source_name,
            transcript_excerpt=row.get("transcript_excerpt"),
            merged_summary=row.get("summary") or "",
            follow_up_items=row.get("follow_up_items") or [],
            decisions=row.get("decisions") or [],
            status=row.get("status") or "open",
            raw_extract=_find_raw_extract(call.get("pending_topics"), source_name),
            match_group=_find_match_group(call_id, source_tid),
            not_discussed_verification=_find_verification(call.get("verification_cache"), source_tid),
            is_not_discussed=False,
        ))

    logger.info(
        f"✅ [Topics] Evidence assembled: topic={topic_id}, "
        f"lineage={len(lineage)}, calls={len(calls)}"
    )
    return TopicEvidenceResponse(
        topic_id=topic_row["id"],
        topic_name=topic_row["name"],
        lineage=lineage,
        calls=calls,
    )


# --------------------------------------------------------------------------- #
# Story 15.1 — PATCH /api/topics/{topic_id}  (partial new-shape body)
# --------------------------------------------------------------------------- #


class TopicPatch(PydanticBaseModel):
    name: Optional[str] = None
    importance: Optional[str] = None
    key_terms: Optional[list[str]] = None
    evidence: Optional[list[dict]] = None
    tasks: Optional[list[dict]] = None
    open_questions: Optional[list[dict]] = None
    decisions: Optional[list[dict]] = None


@router.patch("/topics/{topic_id}")
async def patch_topic(topic_id: str, body: TopicPatch):
    """Partially update a topic_updates row by its row id.

    Accepts any subset of: name, importance, key_terms, evidence, tasks,
    open_questions, decisions. When tasks/open_questions/decisions are supplied,
    items get stable ids + added_in_call_id stamped (resolved from the row's
    call_id via a single SELECT shared across all 3 stamping paths). When tasks
    are supplied, topic-level status is rolled up from task statuses.
    """
    logger.info(f"📥 [Topics] PATCH requested: topic_updates.id={topic_id}")
    db = get_client()

    needs_stamping = (
        body.tasks is not None
        or body.open_questions is not None
        or body.decisions is not None
    )
    call_id_for_stamp = None
    if needs_stamping:
        row = db.table("topic_updates").select("call_id").eq("id", topic_id).execute().data
        if not row:
            raise HTTPException(status_code=404, detail="topic not found")
        call_id_for_stamp = row[0]["call_id"]

    payload: dict = {}
    if body.name is not None:
        payload["name"] = body.name
    if body.importance is not None:
        payload["importance"] = body.importance
    if body.key_terms is not None:
        payload["key_terms"] = body.key_terms
    if body.evidence is not None:
        payload["evidence"] = body.evidence
    if body.tasks is not None:
        stamped = _stamp_item_ids({"tasks": body.tasks}, call_id_for_stamp)["tasks"]
        payload["tasks"] = stamped
        payload["status"] = _status_rollup(stamped)
    if body.open_questions is not None:
        stamped_oq = _stamp_item_ids(
            {"open_questions": body.open_questions}, call_id_for_stamp
        )["open_questions"]
        payload["open_questions"] = stamped_oq
    if body.decisions is not None:
        stamped_d = _stamp_item_ids(
            {"decisions": body.decisions}, call_id_for_stamp
        )["decisions"]
        payload["decisions"] = stamped_d

    if not payload:
        raise HTTPException(status_code=400, detail="no fields to update")

    res = db.table("topic_updates").update(payload).eq("id", topic_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="topic not found")

    logger.info(f"✅ [Topics] PATCH applied: topic_updates.id={topic_id}, fields={list(payload)}")
    return res.data[0]


@router.get("/calls/{call_id}/brief")
async def brief(call_id: str):
    logger.info(f"📥 [Topics] Brief requested: call={call_id}")
    try:
        result = await generate_brief(call_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# --------------------------------------------------------------------------- #
# EPIC-16 — Pass ① /verify-new
# --------------------------------------------------------------------------- #


from backend.services.topic_verification import run_verify_new as _run_verify_new


async def _run_verify_new_background(call_id: str) -> None:
    """EPIC-19 Pass 1: per X:0 group verification.

    Each X:0 binding group (call_task_refs only, no project_task_refs) becomes
    one LLM call. The verdict is stored keyed by group ID.
    """
    import asyncio
    from backend.services.task_match_persistence import load_task_match_groups
    from backend.services.topic_verification import run_verify_new, ProgressLogger
    from backend.services.call_topics_v5.stage_0_ingest import ingest_transcript
    from backend.services.project_topic_state import get_project_topic_state
    from backend.services.topics_service import _resolve_workflow_llm_for_category

    db = get_client()
    plog = ProgressLogger(db, call_id, "verify_new_cache")
    await plog.start()

    try:
        await plog.log("🔍 Pass 1 — Verifying that your new task groups are really new (not continuations of past work).")
        groups = load_task_match_groups(call_id, db=db)
        # EPIC-20: prefer group_kind enum when present; fall back to legacy EPIC-19 shape inference.
        x0_groups = [
            g for g in groups
            if (g.get("group_kind") == "new_only")
            or (
                not g.get("group_kind")
                and g.get("kind") == "binding"
                and g.get("call_task_refs")
                and not g.get("project_task_refs")
            )
        ]
        await plog.log(f"You marked {len(x0_groups)} group(s) as new in matching. I'll check each one against past calls.")

        if not x0_groups:
            db.table("calls").update({
                "verify_new_cache": {"__progress__": plog.entries_snapshot()},
                "verify_new_status": "done",
            }).eq("id", call_id).execute()
            await plog.log("No new groups to verify — nothing to do.")
            return

        # Load call context
        call_row = db.table("calls").select("project_id, pending_topics").eq("id", call_id).execute().data
        if not call_row:
            return
        project_id = call_row[0]["project_id"]
        pending = call_row[0].get("pending_topics") or []

        # Build a flat map: task_id → task dict (with parent topic name attached)
        pending_task_by_id: dict = {}
        for p in pending:
            for t in (p.get("tasks") or []):
                if t.get("task_id"):
                    pending_task_by_id[t["task_id"]] = {**t, "_parent_topic": p.get("name")}

        # Existing project state (used as comparison pool for LLM)
        project_topics = get_project_topic_state(project_id, db=db)

        # Past transcripts (line-numbered)
        all_calls = (
            db.table("calls").select("id, transcript, created_at")
            .eq("project_id", project_id).order("created_at").execute().data
        )
        past_calls = [c for c in all_calls if c["id"] != call_id and c.get("transcript")]
        transcripts = {c["id"]: ingest_transcript(c.get("transcript") or "") for c in past_calls}

        # LLM config
        llm, model = _resolve_workflow_llm_for_category(project_id, "verify_new_topic", db)
        await plog.log(f"📚 Looking at: {len(project_topics)} existing project topic(s) and {len(transcripts)} past call transcript(s).")
        await plog.log(f"🤖 Using model: {llm}/{model or 'default'}.")
        await plog.log("─" * 60)

        # Stable order so log numbering matches what user sees
        x0_groups_indexed = list(enumerate(x0_groups, start=1))

        # Per-group async helper
        async def _verify_group(group_num, g):
            gid = g.get("id")
            if not gid:
                await plog.log(f"⚠ Group #{group_num} has no id — skipping (was the row saved properly?)")
                return None, None
            # Build a synthetic "candidate topic" from this group's tasks
            task_objs = []
            for r in (g.get("call_task_refs") or []):
                t = pending_task_by_id.get(r.get("task_id"))
                if t:
                    task_objs.append(t)
            if not task_objs:
                await plog.log(f"⚠ Group #{group_num} has no resolvable tasks — skipping.")
                return gid, None
            cand_name = (
                g.get("target_topic_name")
                or (task_objs[0].get("_parent_topic") if task_objs else "(unnamed group)")
            )
            candidate = {
                "topic_id": gid,
                "name": cand_name,
                "summary": "",
                "tasks": task_objs,
            }

            # ── Narrative: announce the group ──
            await plog.log(f"")
            await plog.log(f"━━━ Group #{group_num}: \"{cand_name}\" ━━━")
            await plog.log(f"   Contains {len(task_objs)} task(s):")
            for i, t in enumerate(task_objs, 1):
                ttext = (t.get("task") or "(no task)").strip()
                next_step = (t.get("next_step") or "").strip()
                if next_step:
                    await plog.log(f"      {i}. {ttext}  →  {next_step}")
                else:
                    await plog.log(f"      {i}. {ttext}")

            # Layer 1: mechanical pre-filter
            from backend.services.topic_verification import lexical_precheck, compute_confidence as _conf
            pre = lexical_precheck(candidate, project_topics, transcripts)
            qualified_ids = set(pre.get("qualified_topic_ids") or [])
            qualified_topics = [t for t in project_topics if t.get("topic_id") in qualified_ids]

            await plog.log(f"   Step 1 — keyword pre-check: comparing the group's terms against existing project topics' terms.")
            if not qualified_topics:
                await plog.log(f"      No existing project topic has overlapping terms with this group.")
                await plog.log(f"   ✓ VERDICT: TRULY NEW — these tasks don't appear to relate to any past work in this project. (No LLM call needed — confirmed by keyword check alone.)")
                stub = {
                    "verdict": "truly_new",
                    "final_verdict": "truly_new",
                    "matched_topic_id": None,
                    "matched_topic_name": None,
                    "extraction_grounded": True,
                    "ungrounded_items": [],
                    "citations": [],
                    "evaluations": [],
                    "merge_reasoning": "No existing project topic scored above the mechanical merge threshold — confirmed new without LLM evaluation.",
                    "needs_manual_review": False,
                    "lexical_precheck": {k: v for k, v in pre.items() if not k.startswith("_")},
                    "mechanical_skip": True,
                    "kind": "new_topic_verification",
                }
                stub["confidence"] = _conf(stub)
                return gid, stub

            qual_names = ", ".join(f"\"{t.get('name', '?')}\"" for t in qualified_topics[:3])
            more = f" + {len(qualified_topics) - 3} more" if len(qualified_topics) > 3 else ""
            await plog.log(f"      {len(qualified_topics)} existing topic(s) share terms with this group: {qual_names}{more}.")
            await plog.log(f"   Step 2 — asking the LLM to read past transcripts and decide: is this group genuinely new, or does its work continue any of those existing topics?")

            # Layer 2: LLM judgment (suppress internal noise by passing a filter log_fn)
            async def _quiet_log(msg: str):
                # Forward only attempt + retry signals; suppress the deep technical lines
                low = msg.lower()
                if "attempt" in low and "retrying" in low:
                    await plog.log(f"      (the LLM's first answer didn't include valid citations — retrying)")
                # else: silently swallow

            r = await run_verify_new(
                candidate, qualified_topics, transcripts,
                llm=llm, model=model, log_fn=_quiet_log, precheck=pre,
            )
            if r:
                r["kind"] = "new_topic_verification"
            verdict = (r or {}).get("verdict", "?")
            matched_name = (r or {}).get("matched_topic_name")
            reasoning = (r or {}).get("merge_reasoning") or ""
            needs_review = (r or {}).get("needs_manual_review")

            # ── Narrative verdict ──
            if verdict in ("truly_new", "confirmed_new"):
                await plog.log(f"   ✓ VERDICT: TRULY NEW — the LLM agrees these tasks don't continue any existing work.")
            elif verdict in ("should_be_merged_with", "suggest_merge_with"):
                await plog.log(f"   ↻ VERDICT: SUGGEST MERGE — the LLM thinks these tasks continue \"{matched_name or '?'}\".")
                if reasoning:
                    await plog.log(f"      Reason: {reasoning.strip()}")
            else:
                await plog.log(f"   ? VERDICT: {verdict}")

            if needs_review:
                await plog.log(f"   ⚠ The LLM's evidence didn't fully check out (citations failed verification) — you'll want to review this manually.")

            return gid, r

        # SERIAL execution so the narrative log reads cleanly one group at a time
        # (parallel execution interleaved the lines and made the log unreadable).
        results: list = []
        for num, g in x0_groups_indexed:
            results.append(await _verify_group(num, g))

        cache: dict = {}
        for gid, r in results:
            if gid and r is not None:
                cache[gid] = r
        await plog.log("─" * 60)
        await plog.log(f"✅ Pass 1 complete — {len([r for _, r in results if r is not None])} verdict(s) ready. Review them on the cards above.")
        cache["__progress__"] = plog.entries_snapshot()
        db.table("calls").update(
            {"verify_new_cache": cache, "verify_new_status": "done"}
        ).eq("id", call_id).execute()
        logger.info(f"✅ [verify_new] done for call {call_id} ({len(x0_groups)} X:0 groups)")
    except Exception as e:
        logger.exception(f"❌ [verify_new] failed for call {call_id}: {e}")
        try:
            await plog.log(f"❌ ERROR: {e}")
        except Exception:
            pass
        db.table("calls").update({"verify_new_status": "failed"}).eq("id", call_id).execute()
    finally:
        await plog.stop()


@router.post("/calls/{call_id}/topics/verify-new")
async def verify_new(call_id: str, background_tasks: BackgroundTasks):
    """EPIC-16 Pass ① — verify that newly-classified topics are truly new + extraction-grounded."""
    logger.info(f"📥 [verify_new] requested for call {call_id}")
    db = get_client()
    db.table("calls").update({"verify_new_status": "processing", "verify_new_cache": None}).eq("id", call_id).execute()
    background_tasks.add_task(_run_verify_new_background, call_id)
    return {"status": "processing"}


# --------------------------------------------------------------------------- #
# EPIC-16 — Pass ② /verify-not-discussed (lean transcript-only check)
# --------------------------------------------------------------------------- #


from backend.services.topic_verification import run_verify_not_discussed as _run_verify_not_discussed


async def _run_verify_not_discussed_background(call_id: str) -> None:
    """Pass ② for every old topic not in any match group."""
    import asyncio
    import datetime as _dt2
    from backend.services.topics_service import _resolve_workflow_llm_for_category, _get_previous_topics
    from backend.services.topic_verification import ProgressLogger
    from backend.services.call_topics_v5.stage_0_ingest import ingest_transcript
    db = get_client()
    plog = ProgressLogger(db, call_id, "verify_not_discussed_cache")
    try:
        await plog.start()
        await plog.log("Starting Pass ② — Verify not discussed")
        call_row = db.table("calls").select("project_id, transcript").eq("id", call_id).execute().data
        if not call_row:
            return
        project_id = call_row[0]["project_id"]
        transcript_raw = call_row[0].get("transcript") or ""
        ingested = ingest_transcript(transcript_raw)
        await plog.log(f"Loaded transcript for current call ({ingested['line_count']} lines)")

        # EPIC-20: prefer per-group routing when finalized_topic_id is set.
        # 'old_only' groups represent specific previous-call tasks the user
        # said weren't progressed this call → Pass 2 verifies that claim.
        all_groups = load_task_match_groups(call_id, db=db)
        epic20_mode = any(g.get("finalized_topic_id") for g in all_groups)
        previous = _get_previous_topics(project_id, db)

        if epic20_mode:
            old_only_groups = [g for g in all_groups if g.get("group_kind") == "old_only"]
            # For each old_only group, treat it as a synthetic "topic" for Pass 2.
            not_discussed_candidates = []
            previous_by_topic_id = {p["topic_id"]: p for p in previous}
            for g in old_only_groups:
                refs = g.get("project_task_refs") or []
                if not refs:
                    continue
                # Group's nominal topic: take first ref's project_topic_id
                ptid = refs[0].get("project_topic_id")
                src_topic = previous_by_topic_id.get(ptid) or {"topic_id": ptid, "name": "(unknown)", "tasks": []}
                # Build a topic-shaped row with ONLY the group's tasks (subset)
                ref_task_ids = {r.get("task_id") for r in refs if r.get("task_id")}
                gtopic_tasks = [t for t in (src_topic.get("tasks") or []) if t.get("task_id") in ref_task_ids]
                not_discussed_candidates.append({
                    "topic_id": g.get("id"),       # cache key = group_id in EPIC-20 mode
                    "name": src_topic["name"],
                    "tasks": gtopic_tasks,
                    "_source_project_topic_id": ptid,
                })
            await plog.log(f"EPIC-20: {len(not_discussed_candidates)} old-only group(s) to verify")
        else:
            # Legacy: topic is a not-discussed candidate when no match group references it.
            matched_ids = {pid for g in all_groups for pid in (g.get("project_topic_ids") or [])}
            not_discussed_candidates = [t for t in previous if t["topic_id"] not in matched_ids]
            await plog.log(f"Found {len(not_discussed_candidates)} candidate topic(s) marked not-discussed")

        llm, model = _resolve_workflow_llm_for_category(project_id, "verify_not_discussed", db)
        await plog.log(f"Calling LLM ({llm}/{model or 'default'}) on {len(not_discussed_candidates)} topic(s) in parallel")

        async def _one(t):
            await plog.log(f"  → Topic \"{t['name']}\": scanning current call transcript…")
            r = await _run_verify_not_discussed(
                {"name": t["name"], "tasks": t.get("tasks") or []},
                ingested, call_id=call_id, llm=llm, model=model, log_fn=plog.log,
            )
            verdict = (r or {}).get("verdict", "?")
            need_review = (r or {}).get("needs_manual_review")
            if need_review:
                fails = (r or {}).get("failed_citations") or []
                await plog.log(f"  ⚠ Topic \"{t['name']}\": needs manual review — citation issue: {'; '.join(fails[:2])}")
            elif verdict == "confirmed_not_discussed":
                await plog.log(f"  ✓ Topic \"{t['name']}\": confirmed NOT discussed in this call")
            elif verdict == "suggest_discussed_at":
                cit = (r or {}).get("citation") or {}
                ev = (cit.get("evidence_lines") or [None])[0]
                await plog.log(f"  ↻ Topic \"{t['name']}\": actually mentioned (line ~{ev}) → moving to Merged section")
            else:
                await plog.log(f"  ✓ Topic \"{t['name']}\": {verdict}")
            return r

        results = await asyncio.gather(*[_one(t) for t in not_discussed_candidates])
        cache = {t["topic_id"]: r for t, r in zip(not_discussed_candidates, results)}
        cache["__progress__"] = plog.entries_snapshot()
        cache["__progress__"].append({"ts": _dt2.datetime.utcnow().isoformat() + "Z", "msg": f"Pass ② complete — {len(results)} topic(s) checked"})
        db.table("calls").update(
            {"verify_not_discussed_cache": cache, "verify_not_discussed_status": "done"}
        ).eq("id", call_id).execute()
        logger.info(f"✅ [verify_not_discussed] done for call {call_id} ({len(results)} candidates)")
    except Exception as e:
        logger.exception(f"❌ [verify_not_discussed] failed for call {call_id}: {e}")
        try:
            await plog.log(f"❌ ERROR: {e}")
        except Exception:
            pass
        db.table("calls").update({"verify_not_discussed_status": "failed"}).eq("id", call_id).execute()
    finally:
        await plog.stop()


@router.post("/calls/{call_id}/topics/verify-not-discussed")
async def verify_not_discussed(call_id: str, background_tasks: BackgroundTasks):
    """EPIC-16 Pass ② — verify each not-matched project topic truly wasn't discussed in call N."""
    logger.info(f"📥 [verify_not_discussed] requested for call {call_id}")
    db = get_client()
    db.table("calls").update(
        {"verify_not_discussed_status": "processing", "verify_not_discussed_cache": None}
    ).eq("id", call_id).execute()
    background_tasks.add_task(_run_verify_not_discussed_background, call_id)
    return {"status": "processing"}


# --------------------------------------------------------------------------- #
# EPIC-16 — Pass ③ /extract-updates
# --------------------------------------------------------------------------- #


async def _run_extract_updates_background(call_id: str) -> None:
    """EPIC-19 Pass 3 — synthesize merged topic states from bound tasks."""
    from backend.services.task_match_persistence import load_task_match_groups
    from backend.services.topic_verification import run_synthesize_merged_topic
    from backend.services.call_topics_v5.stage_0_ingest import ingest_transcript
    from backend.services.project_topic_state import get_project_topic_state
    from backend.services.topics_service import _resolve_workflow_llm_for_category
    from backend.services.topic_verification import ProgressLogger

    db = get_client()
    plog = ProgressLogger(db, call_id, "extract_updates_cache")
    await plog.start()

    try:
        await plog.log("Loading task-level match groups…")
        groups = load_task_match_groups(call_id, db=db)
        # EPIC-20: Pass 3 fires on 'mixed' groups (call+project tasks both present).
        # Legacy: 'binding' kind with project_task_refs.
        binding_groups = [
            g for g in groups
            if (g.get("group_kind") == "mixed")
            or (
                not g.get("group_kind")
                and g.get("kind") == "binding"
                and g.get("project_task_refs")
            )
        ]
        merged_topic_ids = set()
        for g in binding_groups:
            for r in g.get("project_task_refs") or []:
                if r.get("project_topic_id"):
                    merged_topic_ids.add(r["project_topic_id"])

        if not merged_topic_ids:
            await plog.log("No merged topics for this call — Pass 3 no-op")
            db.table("calls").update({
                "extract_updates_cache": {"__progress__": plog.entries_snapshot()},
                "extract_updates_status": "done",
            }).eq("id", call_id).execute()
            return

        # Project context
        call_row = db.table("calls").select("project_id, transcript").eq("id", call_id).execute().data
        project_id = call_row[0]["project_id"]

        # Existing project topics (full state)
        all_state = get_project_topic_state(project_id, db=db)
        state_by_id = {t["topic_id"]: t for t in all_state}

        # Pending tasks (this call's candidates)
        pending_row = db.table("calls").select("pending_topics").eq("id", call_id).execute().data
        pending = (pending_row[0] or {}).get("pending_topics") or []
        pending_tasks_by_topic_name = {(p.get("name") or "").lower(): p.get("tasks", []) for p in pending}

        # All transcripts in project
        all_calls = db.table("calls").select("id, transcript, created_at").eq("project_id", project_id).order("created_at").execute().data
        transcripts = {
            c["id"]: ingest_transcript(c.get("transcript") or "")
            for c in all_calls if c.get("transcript")
        }
        await plog.log(f"Loaded {len(transcripts)} transcript(s) for synthesis context")

        # Resolve LLM config
        llm, model = _resolve_workflow_llm_for_category(project_id, "extract_topic_updates", db)
        await plog.log(f"Calling LLM ({llm}/{model or 'default'}) per merged topic ({len(merged_topic_ids)} topic(s))")

        results = {}
        for topic_id in merged_topic_ids:
            topic = state_by_id.get(topic_id)
            if not topic:
                await plog.log(f"  ⚠ Skipping topic_id {topic_id} (not in project state)")
                continue
            # Collect new bound tasks for this topic
            new_bound = []
            for g in binding_groups:
                pt_ids = {r.get("task_id") for r in g["project_task_refs"] if r.get("project_topic_id") == topic_id}
                if not pt_ids:
                    continue
                for r in g["call_task_refs"]:
                    name = (r.get("call_topic_name") or "").lower()
                    if not r.get("task_id"):
                        continue
                    for t in pending_tasks_by_topic_name.get(name, []):
                        if t.get("task_id") == r["task_id"]:
                            new_bound.append(t)
            if not new_bound:
                await plog.log(f"  ⚠ Topic '{topic['name']}' has no bound new tasks — skip")
                continue
            await plog.log(f"  → Synthesizing '{topic['name']}'…")
            r = await run_synthesize_merged_topic(
                topic_name=topic["name"],
                previous_update={
                    "tasks": topic.get("tasks", []),
                    "summary": topic.get("summary"),
                    "status": topic.get("status"),
                    "key_terms": topic.get("key_terms"),
                },
                new_bound_tasks=new_bound,
                ingested_transcripts=transcripts,
                llm=llm, model=model, log_fn=plog.log,
            )
            results[topic_id] = r

        cache = {**results, "__progress__": plog.entries_snapshot()}
        db.table("calls").update({
            "extract_updates_cache": cache,
            "extract_updates_status": "done",
        }).eq("id", call_id).execute()
        await plog.log(f"✅ Pass 3 synthesis complete for {len(results)} topic(s)")
    except Exception as e:
        logger.exception(f"❌ [synthesize] failed for call {call_id}: {e}")
        db.table("calls").update({"extract_updates_status": "failed"}).eq("id", call_id).execute()
    finally:
        await plog.stop()


@router.post("/calls/{call_id}/topics/extract-updates")
async def extract_updates(call_id: str, background_tasks: BackgroundTasks):
    """EPIC-16 Pass ③ — full re-extraction of merged topics from raw transcripts with chronological evidence_trail."""
    logger.info(f"📥 [extract_updates] requested for call {call_id}")
    db = get_client()
    db.table("calls").update(
        {"extract_updates_status": "processing", "extract_updates_cache": None}
    ).eq("id", call_id).execute()
    background_tasks.add_task(_run_extract_updates_background, call_id)
    return {"status": "processing"}
