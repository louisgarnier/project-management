"""Pipeline orchestrator — runs Stages 0-10 sequentially, persists per-stage
state in calls.call_topics_v5_payload, manages the state machine
(idle → running → awaiting_review | done | failed).

Stage 11 (human review) is a DB state, not a backend wait. The pipeline runs
Stages 0-10, persists the review payload, sets state to awaiting_review. The
frontend polls + surfaces the banner. User resolves via a dedicated endpoint
that triggers Stages 11-12.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Awaitable, Callable

from backend.database.supabase_client import get_client
from backend.services.call_topics_v5.stage_0_ingest import ingest_transcript
from backend.services.call_topics_v5.stage_1_context import load_context
from backend.services.call_topics_v5.stage_2_atomic import extract_atomic_units
from backend.services.call_topics_v5.stage_3_recall import recall_pass
from backend.services.call_topics_v5.stage_4_citations import resolve_citations
from backend.services.call_topics_v5.stage_5_cluster import cluster_topics
from backend.services.call_topics_v5.stage_6_reconcile import reconcile_with_registry
from backend.services.call_topics_v5.stage_7_synthesis import synthesize_all_topics
from backend.services.call_topics_v5.stage_8_citations import attach_citations
from backend.services.call_topics_v5.stage_9_confidence import attach_confidence
from backend.services.call_topics_v5.stage_10_validation import validate

logger = logging.getLogger("calltracker.call_topics_v5.orchestrator")

ProgressFn = Callable[[str], Awaitable[None]]


async def run_pipeline(
    call_id: str,
    *,
    topics_explicitly_excluded: list[dict] | None = None,
    progress: ProgressFn | None = None,
    db=None,
) -> dict:
    """Run Stages 0-10 against one call's transcript.

    Persists per-stage outputs + final review payload to calls.call_topics_v5_payload.
    Sets state to 'awaiting_review' or 'done' (clean path) or 'failed'.

    Returns the full payload dict written to DB.
    """
    client = db if db is not None else get_client()

    async def _emit(msg: str) -> None:
        logger.info(msg)
        if progress:
            await progress(msg)

    # Helper: state machine writes
    def _set_state(state: str, payload: dict | None = None) -> None:
        update = {"call_topics_v5_state": state}
        if payload is not None:
            update["call_topics_v5_payload"] = payload
        client.table("calls").update(update).eq("id", call_id).execute()

    started_at = _dt.datetime.utcnow().isoformat() + "Z"
    payload: dict = {
        "started_at": started_at,
        "stages": {},
    }

    try:
        _set_state("running", payload)

        # ── Stage 0 ──
        await _emit("Stage 0: loading transcript…")
        call_rows = client.table("calls").select("project_id, transcript").eq("id", call_id).execute().data
        if not call_rows:
            raise ValueError(f"call {call_id!r} not found")
        project_id = call_rows[0]["project_id"]
        transcript = (call_rows[0].get("transcript") or "").strip()
        if not transcript:
            raise ValueError("no_transcript")
        ingested = ingest_transcript(transcript)
        payload["stages"]["0"] = {"line_count": ingested["line_count"], "format": ingested["format_detected"]}
        await _emit(f"Stage 0: ingested {ingested['line_count']} lines ({ingested['format_detected']} format)")

        # ── Stage 1 ──
        await _emit("Stage 1: loading project context + topic registry…")
        ctx = load_context(project_id, db=client)
        payload["stages"]["1"] = {
            "project_name": ctx["project_metadata"]["name"],
            "registry_size": len(ctx["topic_registry"]),
        }
        await _emit(f"Stage 1: registry has {len(ctx['topic_registry'])} canonical topics")

        # LLM config from project default
        llm = ctx["project_metadata"]["default_llm"]
        model = ctx["project_metadata"]["default_model"]
        payload["model_used"] = f"{llm}/{model}"
        payload["params"] = {"temperature": 0}
        await _emit(f"🤖 Using model: {llm}/{model}")

        # ── Stage 2 ──
        await _emit("Stage 2: atomic unit extraction (LLM)…")
        s2 = await extract_atomic_units(ingested, ctx["project_metadata"]["context"], llm=llm, model=model)
        payload["stages"]["2"] = {"units_count": len(s2["units"]), "rejected": s2["rejected"]}
        await _emit(f"Stage 2: extracted {len(s2['units'])} atomic units ({len(s2['rejected'])} rejected)")
        if s2["rejected"]:
            for r in s2["rejected"][:5]:
                await _emit(f"  ✗ rejected: {r}")
            if len(s2["rejected"]) > 5:
                await _emit(f"  … +{len(s2['rejected']) - 5} more")

        # ── Stage 3 ──
        await _emit("Stage 3: adversarial recall pass (LLM)…")
        s3 = await recall_pass(ingested, s2["units"], llm=llm, model=model)
        payload["stages"]["3"] = {"new_units": len(s3["new_units"]), "merged_pool_size": len(s3["merged_pool"])}
        await _emit(f"Stage 3: found {len(s3['new_units'])} missed units (pool now {len(s3['merged_pool'])})")

        # ── Stage 4 ──
        await _emit("Stage 4: resolving citations from line ranges…")
        atomic_pool = resolve_citations(s3["merged_pool"], ingested)
        invalid = sum(1 for u in atomic_pool if not u.get("citation_valid"))
        payload["stages"]["4"] = {"pool_size": len(atomic_pool), "invalid_citations": invalid}
        await _emit(f"Stage 4: {len(atomic_pool)} citations resolved ({invalid} invalid → flagged)")

        # ── Stage 5 ──
        await _emit("Stage 5: clustering atomic units into topics (LLM)…")
        project_context = ctx["project_metadata"].get("context", "") or ""
        s5 = await cluster_topics(atomic_pool, ctx["topic_registry"], llm=llm, model=model, project_context=project_context)
        payload["stages"]["5"] = {
            "clusters": len(s5["clusters"]),
            "orphans": s5["orphans"],
            "rejected": s5["rejected"],
        }
        await _emit(f"Stage 5: {len(s5['clusters'])} topics ({len(s5['orphans'])} orphan units)")
        if s5["rejected"]:
            for r in s5["rejected"][:5]:
                await _emit(f"  ✗ cluster rejected: {r}")
        if s5["orphans"]:
            await _emit(f"  ⓘ orphan unit_ids: {', '.join(s5['orphans'][:10])}" + (" …" if len(s5["orphans"]) > 10 else ""))

        # ── Stage 6 ──
        await _emit("Stage 6: reconciling with topic registry…")
        s6 = reconcile_with_registry(s5["clusters"], ctx["topic_registry"])
        payload["stages"]["6"] = {
            "working_topics": len(s6["working_topics"]),
            "new_proposals": len(s6["new_topic_proposals"]),
        }
        await _emit(f"Stage 6: {len(s6['working_topics'])} working topics, {len(s6['new_topic_proposals'])} new proposals")

        # ── Stage 7 (sequential, per topic) ──
        await _emit(f"Stage 7: per-topic synthesis ({len(s6['working_topics'])} topics, sequential)…")
        synthesized = await synthesize_all_topics(
            s6["working_topics"], atomic_pool, llm=llm, model=model, progress_callback=_emit if progress else None,
        )
        payload["stages"]["7"] = {
            "topics_synthesized": len(synthesized),
            "total_tasks": sum(len(t.get("tasks") or []) for t in synthesized),
        }
        await _emit(f"Stage 7: synthesized {len(synthesized)} topics with {payload['stages']['7']['total_tasks']} tasks total")
        # Surface per-topic rejections (Stage 7 schema/citation validation drops)
        for t in synthesized:
            rej = t.get("rejected") or []
            if rej:
                await _emit(f"  ✗ {t.get('topic_name')!r}: {len(rej)} task(s) rejected")
                for r in rej[:3]:
                    await _emit(f"      {r}")

        # ── Stage 8 ──
        await _emit("Stage 8: attaching task-level citations…")
        with_cits = attach_citations(synthesized, atomic_pool)
        payload["stages"]["8"] = {
            "below_min_tasks": sum(
                1 for t in with_cits for tk in t.get("tasks") or []
                if tk.get("citations_below_min")
            ),
        }
        await _emit("Stage 8: citations attached")

        # ── Stage 9 ──
        await _emit("Stage 9: computing per-task confidence…")
        with_conf = attach_confidence(with_cits, atomic_pool)
        avg_conf = (
            sum(
                (tk.get("confidence") or {}).get("score", 0.0)
                for t in with_conf for tk in t.get("tasks") or []
            )
            / max(1, sum(len(t.get("tasks") or []) for t in with_conf))
        )
        payload["stages"]["9"] = {"avg_confidence": round(avg_conf, 3)}
        await _emit(f"Stage 9: average task confidence = {avg_conf:.2f}")

        # ── Stage 10 ──
        await _emit("Stage 10: validation (hard + soft + clean)…")
        report = validate(
            with_conf, atomic_pool, s5["orphans"],
            topics_explicitly_excluded=topics_explicitly_excluded or [],
        )
        payload["stages"]["10"] = report
        await _emit(
            f"Stage 10: {len(report['hard_failures'])} hard, {len(report['soft_warnings'])} soft, "
            f"{report['new_topic_proposals_count']} new proposals, {report['low_confidence_tasks_count']} low-conf → "
            f"clean={report['clean']}"
        )

        # ── Orphan auto-rescue ──
        # Any unit not clustered by Stage 5 becomes its own task under an
        # 'Uncategorized' synthetic topic. Nothing lost. The user can rename
        # / redispatch from the call_topics UI after the pipeline finishes.
        orphan_units = [u for u in atomic_pool if u.get("unit_id") in set(s5["orphans"])]
        if orphan_units:
            await _emit(f"Auto-rescue: {len(orphan_units)} orphan unit(s) → 'Uncategorized' topic")
            rescued_tasks = []
            for u in orphan_units:
                if not u.get("citation_valid"):
                    continue
                ev = u.get("evidence_lines") or [0, 0]
                rescued_tasks.append({
                    "task": (u.get("text") or "(uncategorized)")[:120],
                    "next_step": "",
                    "owner": u.get("owner") or "unassigned",
                    "status": "open",
                    "key_terms": [],
                    "open_questions": [],
                    "decisions": [],
                    "evidence_unit_ids": [u.get("unit_id")],
                    "citations": [{
                        "speaker": u.get("owner") or "",
                        "quote": u.get("citation") or "",
                        "lines": f"{int(ev[0]):04d}-{int(ev[1]):04d}" if len(ev) == 2 else "",
                        "unit_id": u.get("unit_id"),
                    }],
                    "citations_below_min": True,  # only 1 citation by construction
                    "confidence": {
                        "score": 0.3,  # low — single unit, no clustering signal
                        "signals": {"orphan_rescued": True},
                    },
                })
            if rescued_tasks:
                with_conf.append({
                    "topic_name": "Uncategorized",
                    "importance": "low",
                    "new_topic": True,
                    "provisional": True,
                    "registry_id": None,
                    "tasks": rescued_tasks,
                })

        # Persist all internal stages
        payload["synthesized_topics"] = with_conf
        payload["new_topic_proposals"] = s6["new_topic_proposals"]

        # Build review payload
        approvals_needed: list[dict] = []
        for prop in s6["new_topic_proposals"]:
            approvals_needed.append({
                "type": "new_topic",
                "proposal": prop,
            })
        for hf in report["hard_failures"]:
            approvals_needed.append({
                "type": "hard_failure_escalation",
                "failure": hf,
            })
        confidence_review: list[dict] = []
        for t in with_conf:
            for tk in t.get("tasks") or []:
                score = (tk.get("confidence") or {}).get("score", 1.0)
                if score < 0.5:
                    confidence_review.append({
                        "task_text": tk.get("task"),
                        "topic_name": t.get("topic_name"),
                        "score": score,
                    })
        warnings = report["soft_warnings"]
        payload["review_payload"] = {
            "approvals_needed": approvals_needed,
            "confidence_review": confidence_review,
            "warnings": warnings,
        }

        # ── Stage 11 SKIPPED (EPIC-17 simplification) ──
        # New topic approvals, confidence review, warnings → all moved to the
        # call_topics UI where the user can edit/delete tasks directly. The
        # gate-style banner added friction without value because everything
        # ended up Approve-all anyway. Confidence is now displayed PER TASK in
        # the table (colored chip). Warnings are computed + persisted but not
        # surfaced as blocking review.
        #
        # New topics: auto-added to the project topic_registry so future calls
        # see them in Stage 5's vocabulary. The user can rename / delete from
        # the regular call_topics UI; downstream changes to the registry are
        # rare and can be made via an admin endpoint when needed.

        # Resolve project_id (we have it from earlier — call_rows fetch)
        proj_id = call_rows[0]["project_id"]
        new_topics_added: list[str] = []
        for prop in s6["new_topic_proposals"]:
            name = (prop.get("proposed_name") or "").strip()
            if not name:
                continue
            try:
                # Insert into topic_registry; idempotent via the unique index
                # on (project_id, lower(name)) — duplicates silently skipped.
                client.table("topic_registry").insert({
                    "project_id": proj_id,
                    "name": name,
                    "approved_by_call_id": call_id,
                }).execute()
                new_topics_added.append(name)
            except Exception as e:  # noqa: BLE001
                # Likely a unique constraint hit if the topic already exists
                # (race or case-only difference). Don't fail the pipeline.
                logger.warning("[Stage 11 auto-approve] registry insert skipped %r: %s", name, e)
        if new_topics_added:
            await _emit(f"Auto-added to registry: {', '.join(new_topics_added)}")

        # Always run Stage 12 — no human gate.
        from backend.services.call_topics_v5.stage_12_serialize import serialize_to_v4
        v4_output = serialize_to_v4(with_conf)
        payload["v4_output"] = v4_output
        payload["auto_registry_additions"] = new_topics_added
        payload["completed_at"] = _dt.datetime.utcnow().isoformat() + "Z"

        client.table("calls").update({
            "call_topics_v5_state": "done",
            "call_topics_v5_payload": payload,
            "extraction_cache": v4_output,
            "extraction_status": "done",
        }).eq("id", call_id).execute()
        await _emit(
            f"Stage 12: serialized {len(v4_output)} topic(s) → DONE "
            f"({report['low_confidence_tasks_count']} task(s) with conf<0.5 visible in table chip; "
            f"{len(report['soft_warnings'])} warning(s) persisted in payload but non-blocking)"
        )
        return payload

    except Exception as e:  # noqa: BLE001
        logger.exception("[Pipeline] failed for call %s: %s", call_id, e)
        payload["error"] = str(e)
        payload["completed_at"] = _dt.datetime.utcnow().isoformat() + "Z"
        _set_state("failed", payload)
        if progress:
            await progress(f"❌ Pipeline FAILED: {e}")
        raise


async def resolve_review(
    call_id: str,
    decisions: dict,
    *,
    db=None,
) -> dict:
    """Apply user's Stage 11 decisions → run Stage 12 → state = done.

    decisions shape:
      {
        "approved_new_topics": [{proposed_name, registry_action: "approve"|"merge"|"reject", merge_with_id?}],
        "confidence_decisions": [{task_index_path, action: "approve"|"edit"|"drop", edits?}],
        "acknowledged_warnings": [warning_idx]
      }
    """
    client = db if db is not None else get_client()
    row = client.table("calls").select("call_topics_v5_state, call_topics_v5_payload, project_id").eq("id", call_id).execute().data
    if not row:
        raise ValueError(f"call {call_id!r} not found")
    state = row[0].get("call_topics_v5_state")
    if state != "awaiting_review":
        raise ValueError(f"call {call_id!r} is not awaiting_review (state={state!r})")
    payload = row[0].get("call_topics_v5_payload") or {}
    project_id = row[0]["project_id"]

    synthesized = payload.get("synthesized_topics") or []
    approved_new_topics = decisions.get("approved_new_topics") or []
    # NEW: list of {topic_name, task_text} tuples flagged for drop (from warnings UI)
    dropped_task_keys = {
        (d.get("topic_name", "").strip().lower(), d.get("task_text", "").strip())
        for d in (decisions.get("dropped_tasks") or [])
    }

    # Apply new topic decisions → registry mutation
    name_remap: dict[str, str] = {}  # old proposed_name → final canonical name
    for nt in approved_new_topics:
        proposed = nt.get("proposed_name") or ""
        action = nt.get("registry_action")
        if action == "approve":
            # Insert new registry entry
            inserted = client.table("topic_registry").insert({
                "project_id": project_id,
                "name": proposed,
                "approved_by_call_id": call_id,
            }).execute()
            if inserted.data:
                # Name stays as proposed
                name_remap[proposed.lower()] = proposed
        elif action == "merge":
            merge_id = nt.get("merge_with_id")
            if merge_id:
                merge_rows = client.table("topic_registry").select("name").eq("id", merge_id).execute().data
                if merge_rows:
                    name_remap[proposed.lower()] = merge_rows[0]["name"]
        elif action == "reject":
            # Drop the topic entirely from output
            name_remap[proposed.lower()] = ""

    # Drop confidence-rejected tasks
    rejected_task_paths = set()
    for cd in (decisions.get("confidence_decisions") or []):
        if cd.get("action") == "drop":
            rejected_task_paths.add(cd.get("task_index_path") or "")

    # Apply name remap + drop rejected
    final_topics: list[dict] = []
    for ti, topic in enumerate(synthesized):
        tname = topic.get("topic_name") or ""
        remapped = name_remap.get(tname.lower())
        if remapped == "":
            # Whole topic rejected
            continue
        if remapped:
            topic["topic_name"] = remapped
            topic["new_topic"] = False
        tasks_out: list[dict] = []
        for taski, tk in enumerate(topic.get("tasks") or []):
            path = f"{ti}.{taski}"
            if path in rejected_task_paths:
                continue
            # NEW: drop via warning UI
            key = ((topic.get("topic_name") or "").strip().lower(), (tk.get("task") or "").strip())
            if key in dropped_task_keys:
                continue
            tasks_out.append(tk)
        if tasks_out:
            topic["tasks"] = tasks_out
            final_topics.append(topic)

    # Stage 12: serialize
    from backend.services.call_topics_v5.stage_12_serialize import serialize_to_v4
    v4_output = serialize_to_v4(final_topics)
    payload["v4_output"] = v4_output
    payload["resolve_decisions"] = decisions
    payload["resolved_at"] = _dt.datetime.utcnow().isoformat() + "Z"

    client.table("calls").update({
        "call_topics_v5_state": "done",
        "call_topics_v5_payload": payload,
        "extraction_cache": v4_output,
        "extraction_status": "done",
    }).eq("id", call_id).execute()

    return payload
