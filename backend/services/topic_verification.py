"""EPIC-16 — Orchestration for the 3 RAG verification passes."""

import asyncio
import datetime as _dt
import json
import logging
import re as _re

from backend.prompts.verify_new_topic import VERIFY_NEW_TOPIC_PROMPT
from backend.prompts.verify_not_discussed import VERIFY_NOT_DISCUSSED_PROMPT
from backend.prompts.extract_topic_updates import EXTRACT_TOPIC_UPDATES_PROMPT
from backend.services.citation_verify import verify_citations, find_quote_lines

logger = logging.getLogger("calltracker.topic_verification")


# Thin shim around the project's LLM dispatcher — kept here so tests can monkeypatch it.
async def _call_llm(prompt: str, llm: str, *, model: str | None) -> dict:
    from backend.services.topics_service import _call_llm as _ts_call_llm
    return await _ts_call_llm(prompt, llm, model=model)


# ── Progress log helper ────────────────────────────────────────────────────────
# Used by the 3 background tasks to surface per-step progress in the UI. Writes
# accumulated entries to calls.<cache_field>.__progress__ periodically while
# verification runs. Frontend polls the cache and renders the log.


class ProgressLogger:
    """Collects timestamped progress messages + flushes them to a JSONB cache field.

    Usage:
        plog = ProgressLogger(db, call_id, "verify_new_cache")
        await plog.start()  # initial flush + start background flusher
        await plog.log("Loading transcripts…")
        ...
        await plog.stop()   # final flush + stop flusher
    """

    def __init__(self, db, call_id: str, cache_field: str, flush_interval_s: float = 2.0):
        self._db = db
        self._call_id = call_id
        self._cache_field = cache_field
        self._flush_interval = flush_interval_s
        self._entries: list[dict] = []
        self._lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def log(self, msg: str) -> None:
        async with self._lock:
            self._entries.append({"ts": _dt.datetime.utcnow().isoformat() + "Z", "msg": msg})
        logger.info(f"📥 [progress:{self._cache_field}] {msg}")

    def entries_snapshot(self) -> list[dict]:
        """Return a copy of all accumulated entries (used in final cache write)."""
        return list(self._entries)

    def _flush_sync(self) -> None:
        # Read-modify-write the cache field. Best-effort — tolerates concurrent writes.
        try:
            row = self._db.table("calls").select(self._cache_field).eq("id", self._call_id).execute().data
            cache = (row[0].get(self._cache_field) if row else None) or {}
            cache["__progress__"] = list(self._entries)
            self._db.table("calls").update({self._cache_field: cache}).eq("id", self._call_id).execute()
        except Exception as e:
            logger.warning(f"⚠️ [progress] flush failed: {e}")

    async def _flusher_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._flush_interval)
            except asyncio.TimeoutError:
                pass
            self._flush_sync()

    async def start(self) -> None:
        self._flush_sync()
        self._task = asyncio.create_task(self._flusher_loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await self._task
            except Exception:
                pass
        self._flush_sync()


# ── Lexical pre-check (deterministic, mechanical) ─────────────────────────────


def _jaccard(a: list[str], b: list[str]) -> float:
    """Jaccard similarity of two string lists (case-insensitive whitespace-trimmed)."""
    set_a = {(s or "").lower().strip() for s in a if (s or "").strip()}
    set_b = {(s or "").lower().strip() for s in b if (s or "").strip()}
    if not set_a or not set_b:
        return 0.0
    inter = set_a & set_b
    union = set_a | set_b
    return len(inter) / len(union) if union else 0.0


def _count_term_occurrences(text: str, terms: list[str]) -> dict[str, int]:
    """Whole-word case-insensitive count of each term in text."""
    if not text or not terms:
        return {}
    text_lower = text.lower()
    out: dict[str, int] = {}
    for term in terms:
        clean = (term or "").lower().strip()
        if not clean:
            continue
        try:
            pattern = r"\b" + _re.escape(clean) + r"\b"
            out[term] = len(_re.findall(pattern, text_lower))
        except _re.error:
            out[term] = 0
    return out


def lexical_precheck(
    candidate: dict,
    project_topics: list[dict],
    transcripts: dict[str, str],
) -> dict:
    """Mechanical pre-check: where do the candidate's key_terms appear?

    Independent signal from the LLM judgment. Catches LLM hallucination by
    surfacing the actual term overlap with existing topics + count of mentions
    in past transcripts.

    Returns:
        {
            "candidate_terms": [...],
            "topic_overlaps": [{"topic_id", "name", "jaccard", "shared_terms"}, ...sorted desc],
            "transcript_hits": {call_id: {"total": int, "by_term": {term: count}}},
            "verdict_hint": "likely_new" | "likely_merge_with:<topic_id>" | "uncertain",
        }
    """
    candidate_terms = list(candidate.get("key_terms") or [])

    topic_overlaps = []
    for t in project_topics:
        topic_terms = list(t.get("key_terms") or [])
        if not topic_terms:
            continue
        jacc = _jaccard(candidate_terms, topic_terms)
        shared = sorted(
            {(s or "").lower().strip() for s in candidate_terms}
            & {(s or "").lower().strip() for s in topic_terms}
        )
        topic_overlaps.append({
            "topic_id": t.get("topic_id"),
            "name": t.get("name"),
            "jaccard": round(jacc, 3),
            "shared_terms": shared,
        })
    topic_overlaps.sort(key=lambda x: -x["jaccard"])

    transcript_hits: dict[str, dict] = {}
    for cid, body in transcripts.items():
        by_term = _count_term_occurrences(body or "", candidate_terms)
        transcript_hits[cid] = {"total": sum(by_term.values()), "by_term": by_term}

    # Heuristic verdict hint (used as hint to LLM + for sanity check)
    max_overlap = topic_overlaps[0] if topic_overlaps else None
    total_hits = sum(h["total"] for h in transcript_hits.values())
    if max_overlap and max_overlap["jaccard"] >= 0.5:
        verdict_hint = f"likely_merge_with:{max_overlap['topic_id']}"
    elif total_hits == 0 and (not max_overlap or max_overlap["jaccard"] == 0.0):
        verdict_hint = "likely_new"
    else:
        verdict_hint = "uncertain"

    return {
        "candidate_terms": candidate_terms,
        "topic_overlaps": topic_overlaps,
        "transcript_hits": transcript_hits,
        "verdict_hint": verdict_hint,
    }


def sanity_check_llm_vs_lexical(llm_result: dict, precheck: dict) -> str | None:
    """Compare LLM verdict to lexical hint. Returns a flag string if they disagree.

    Returns:
        None — no contradiction
        "llm_recommends_merge_but_no_overlap" — LLM said merge but lexical found 0 overlap with target
        "llm_says_new_but_strong_overlap_exists" — LLM said new but lexical shows strong jaccard with an existing topic
    """
    verdict = (llm_result or {}).get("verdict")
    matched_id = (llm_result or {}).get("matched_topic_id")
    overlaps = (precheck or {}).get("topic_overlaps") or []
    hits = (precheck or {}).get("transcript_hits") or {}

    if verdict == "should_be_merged_with" and matched_id:
        target_overlap = next(
            (o for o in overlaps if o["topic_id"] == matched_id), None
        )
        total_hits = sum(h["total"] for h in hits.values())
        if (
            (target_overlap is None or target_overlap["jaccard"] == 0.0)
            and total_hits == 0
        ):
            return "llm_recommends_merge_but_no_overlap"

    if verdict == "truly_new":
        for o in overlaps:
            if o["jaccard"] >= 0.5:
                return "llm_says_new_but_strong_overlap_exists"

    return None


def _build_verify_new_prompt(
    candidate: dict,
    project_topics: list[dict],
    transcripts: dict[str, str],
    precheck: dict | None = None,
) -> str:
    transcripts_block = "\n\n".join(
        f"--- CALL {cid} ---\n{body}" for cid, body in transcripts.items()
    )
    # Include name + key_terms + brief summary + 1-line task briefs for each
    # existing topic so the LLM has enough signal to detect duplicates by
    # semantics, not just name. tasks/OQ/decisions on existing topics are
    # too verbose for this comparison purpose — we surface compact briefs.
    project_topics_block = json.dumps(
        [
            {
                "topic_id": t.get("topic_id"),
                "name": t.get("name"),
                "key_terms": t.get("key_terms") or [],
                "summary": t.get("summary") or "",
                "task_briefs": t.get("task_briefs") or [],
            }
            for t in project_topics
        ],
        indent=2,
    )
    candidate_block = json.dumps({
        "name": candidate.get("name"),
        "key_terms": candidate.get("key_terms", []),
        "tasks": candidate.get("tasks", []),
        "open_questions": candidate.get("open_questions", []),
        "decisions": candidate.get("decisions", []),
    }, indent=2)
    precheck_block = ""
    if precheck:
        precheck_block = (
            "\n\nLEXICAL PRE-CHECK (deterministic, fyi — your own analysis should be primary):\n"
            f"{json.dumps(precheck, indent=2)}\n"
            "Use this only as a hint. The candidate was extracted from the CURRENT call; "
            "the transcripts below are PAST calls only. Decide based on whether the topic "
            "was actually discussed before."
        )
    return (
        f"{VERIFY_NEW_TOPIC_PROMPT}\n\n"
        f"CANDIDATE NEW TOPIC (full data — what the user proposes as new in the current call):\n{candidate_block}\n\n"
        f"EXISTING PROJECT TOPICS (name + key_terms + summary + brief task list — use to check for duplicates):\n{project_topics_block}\n\n"
        f"PAST TRANSCRIPTS (calls N-1, ..., 1 — NOT the current call N):\n{transcripts_block}"
        f"{precheck_block}"
    )


async def run_verify_new(
    candidate: dict,
    project_topics: list[dict],
    transcripts: dict[str, str],
    *,
    llm: str,
    model: str | None,
    log_fn=None,
    precheck: dict | None = None,
) -> dict:
    """Run Pass ① for one candidate new topic.

    Returns the LLM verdict augmented with a `needs_manual_review` flag set to True
    if citation verification failed both on the first attempt and on one retry.

    log_fn (optional): async callable(str) → emits step-by-step progress lines.
    precheck (optional): lexical pre-check result to include in the prompt + compute sanity flag.
    """
    name = candidate.get("name", "?")

    async def _log(msg: str) -> None:
        if log_fn:
            await log_fn(msg)

    prompt = _build_verify_new_prompt(candidate, project_topics, transcripts, precheck=precheck)
    result: dict = {}
    failures: list[str] = []

    for attempt in (1, 2):
        await _log(f"      [{name}] attempt {attempt}: asking LLM to check if this candidate is a duplicate of any of the {len(project_topics)} existing project topic(s) (referencing {len(transcripts)} past transcript(s))")
        result = await _call_llm(prompt, llm, model=model)
        if not isinstance(result, dict):
            logger.warning("⚠️ [verify_new] LLM returned non-dict on attempt %d", attempt)
            await _log(f"      [{name}] attempt {attempt}: LLM response invalid — retrying")
            failures = ["LLM returned non-dict"]
            continue
        cits = result.get("citations") or []
        for c in cits:
            if not c.get("lines"):
                body = transcripts.get(c.get("call_id"), "")
                computed = find_quote_lines(c.get("quote", ""), body)
                if computed:
                    c["lines"] = computed
        await _log(f"      [{name}] attempt {attempt}: LLM responded with {len(cits)} supporting quote(s) — checking each one is actually in the transcript")
        ok, failures = verify_citations(cits, transcripts)
        if ok:
            await _log(f"      [{name}] all {len(cits)} quote(s) found in the transcripts ✓")
            final = {**result, "needs_manual_review": False}
            if precheck is not None:
                final["lexical_precheck"] = precheck
                flag = sanity_check_llm_vs_lexical(final, precheck)
                if flag:
                    final["sanity_flag"] = flag
                    await _log(f"      [{name}] ⚠ sanity flag: {flag} — LLM verdict disagrees with lexical pre-check")
            return final
        logger.warning("⚠️ [verify_new] citation verify failed on attempt %d: %s", attempt, failures)
        await _log(f"      [{name}] attempt {attempt}: {len(failures)} of {len(cits)} quote(s) NOT found in the transcripts — retrying")
        prompt = (
            f"{prompt}\n\nPREVIOUS ATTEMPT FAILED citation verification with these errors:\n"
            f"{json.dumps(failures, indent=2)}\nRedo with verbatim quotes copy-pasted from transcripts."
        )

    final = {
        **result,
        "needs_manual_review": True,
        "failed_citations": failures,
    }
    if precheck is not None:
        final["lexical_precheck"] = precheck
        flag = sanity_check_llm_vs_lexical(final, precheck)
        if flag:
            final["sanity_flag"] = flag
    return final


def _build_verify_not_discussed_prompt(topic: dict, transcript: str, call_id: str) -> str:
    anchor = json.dumps({"name": topic.get("name"), "key_terms": topic.get("key_terms", [])}, indent=2)
    return (
        f"{VERIFY_NOT_DISCUSSED_PROMPT}\n\n"
        f"TOPIC ANCHOR:\n{anchor}\n\n"
        f"TRANSCRIPT (call_id={call_id}):\n{transcript}"
    )


async def run_verify_not_discussed(
    topic: dict, transcript: str, *, call_id: str, llm: str, model: str | None, log_fn=None,
) -> dict:
    """Pass ② — verify a topic wasn't discussed in the supplied transcript.

    Returns the LLM verdict with `needs_manual_review` set to True if citation
    verification failed on both attempts (only relevant when verdict='actually_discussed').

    log_fn (optional): async callable(str) — emits per-attempt progress.
    """
    name = topic.get("name", "?")

    async def _log(msg: str) -> None:
        if log_fn:
            await log_fn(msg)

    prompt = _build_verify_not_discussed_prompt(topic, transcript, call_id)
    result: dict = {}
    failures: list[str] = []

    for attempt in (1, 2):
        await _log(f"      [{name}] attempt {attempt}: asking LLM to scan the current call transcript for any mention")
        result = await _call_llm(prompt, llm, model=model)
        if not isinstance(result, dict):
            logger.warning("⚠️ [verify_not_discussed] LLM returned non-dict on attempt %d", attempt)
            await _log(f"      [{name}] attempt {attempt}: LLM response invalid — retrying")
            failures = ["LLM returned non-dict"]
            continue
        citation = result.get("citation")
        cits = [citation] if citation else []
        for c in cits:
            if not c.get("lines"):
                computed = find_quote_lines(c.get("quote", ""), transcript)
                if computed:
                    c["lines"] = computed
        if citation:
            await _log(f"      [{name}] attempt {attempt}: LLM claims it found a mention — checking the quote is actually in the transcript")
        else:
            await _log(f"      [{name}] attempt {attempt}: LLM confirmed no mention in the transcript")
        ok, failures = verify_citations(cits, {call_id: transcript})
        if ok:
            return {**result, "needs_manual_review": False}
        logger.warning("⚠️ [verify_not_discussed] citation verify failed on attempt %d: %s", attempt, failures)
        await _log(f"      [{name}] attempt {attempt}: the quote LLM cited is NOT in the transcript — retrying")
        prompt = (
            f"{prompt}\n\nPREVIOUS ATTEMPT FAILED citation verification:\n"
            f"{json.dumps(failures, indent=2)}\nRedo with a verbatim quote."
        )

    return {**result, "needs_manual_review": True, "failed_citations": failures}


def _build_extract_updates_prompt(topic_anchor: dict, transcripts: dict[str, str]) -> str:
    transcripts_block = "\n\n".join(
        f"--- CALL {cid} ---\n{body}" for cid, body in transcripts.items()
    )
    anchor = json.dumps({"name": topic_anchor.get("name"), "key_terms": topic_anchor.get("key_terms", [])}, indent=2)
    return (
        f"{EXTRACT_TOPIC_UPDATES_PROMPT}\n\n"
        f"TOPIC ANCHOR:\n{anchor}\n\n"
        f"TRANSCRIPTS (chronological):\n{transcripts_block}"
    )


def _collect_citations(snapshot: dict, trail: list[dict]) -> list[dict]:
    """Flatten every citation referenced from the snapshot + trail for post-verify."""
    out: list[dict] = []
    for task in snapshot.get("tasks", []) or []:
        if task.get("primary_citation"):
            out.append(task["primary_citation"])
        for c in task.get("supporting_citations") or []:
            out.append(c)
    for oq in snapshot.get("open_questions", []) or []:
        if oq.get("primary_citation"):
            out.append(oq["primary_citation"])
    for d in snapshot.get("decisions", []) or []:
        if d.get("primary_citation"):
            out.append(d["primary_citation"])
        for c in d.get("supporting_citations") or []:
            out.append(c)
    for e in trail or []:
        if e.get("citation"):
            out.append(e["citation"])
    return out


async def run_extract_topic_updates(
    topic_anchor: dict, transcripts: dict[str, str], *, llm: str, model: str | None, log_fn=None,
) -> dict:
    """Pass ③ — full re-extraction of a topic from raw transcripts.

    Returns the LLM output augmented with `needs_manual_review=True` if any
    citation in the snapshot or evidence_trail couldn't be verified after one retry.

    log_fn (optional): async callable(str) — emits per-attempt progress.
    """
    name = topic_anchor.get("name", "?")

    async def _log(msg: str) -> None:
        if log_fn:
            await log_fn(msg)

    prompt = _build_extract_updates_prompt(topic_anchor, transcripts)
    result: dict = {}
    failures: list[str] = []

    for attempt in (1, 2):
        await _log(f"      [{name}] attempt {attempt}: asking LLM to re-extract from {len(transcripts)} transcript(s) (chronological)")
        result = await _call_llm(prompt, llm, model=model)
        if not isinstance(result, dict):
            logger.warning("⚠️ [extract_updates] LLM returned non-dict on attempt %d", attempt)
            await _log(f"      [{name}] attempt {attempt}: LLM response invalid — retrying")
            failures = ["LLM returned non-dict"]
            continue
        snapshot = result.get("extracted_snapshot") or {}
        trail = result.get("evidence_trail") or []
        all_cits = _collect_citations(snapshot, trail)
        for c in all_cits:
            if not c.get("lines"):
                body = transcripts.get(c.get("call_id"), "")
                computed = find_quote_lines(c.get("quote", ""), body)
                if computed:
                    c["lines"] = computed
        await _log(f"      [{name}] attempt {attempt}: LLM responded with snapshot + {len(all_cits)} supporting quote(s) — checking each is actually in the transcripts")
        ok, failures = verify_citations(all_cits, transcripts)
        if ok:
            await _log(f"      [{name}] all {len(all_cits)} quote(s) found in the transcripts ✓")
            return {**result, "needs_manual_review": False}
        logger.warning("⚠️ [extract_updates] citation verify failed on attempt %d: %s", attempt, failures)
        await _log(f"      [{name}] attempt {attempt}: {len(failures)} of {len(all_cits)} quote(s) NOT found in the transcripts — retrying")
        prompt = (
            f"{prompt}\n\nPREVIOUS ATTEMPT FAILED citation verification:\n"
            f"{json.dumps(failures, indent=2)}\nRedo with verbatim quotes."
        )

    return {**result, "needs_manual_review": True, "failed_citations": failures}
