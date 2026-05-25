"""EPIC-16 — Orchestration for the 3 RAG verification passes."""

import asyncio
import datetime as _dt
import json
import logging
import math as _math
import re as _re

from backend.prompts.verify_new_topic import VERIFY_NEW_TOPIC_PROMPT
from backend.prompts.verify_not_discussed import VERIFY_NOT_DISCUSSED_PROMPT
from backend.prompts.extract_topic_updates import EXTRACT_TOPIC_UPDATES_PROMPT
from backend.services.citation_verify import verify_citations, find_quote_lines, verify_evidence_lines
from backend.services.topic_similarity import (
    effective_token_set, compute_idf, weighted_jaccard_tokens, weighted_jaccard, _STOPWORDS,
)

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

    def __init__(self, db, call_id: str, cache_field: str, flush_interval_s: float = 0.5):
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
        # Force immediate flush for snappier UI — run sync DB write in a
        # thread so we don't block the event loop. The flusher_loop still
        # runs for safety net but most updates ship instantly.
        try:
            await asyncio.to_thread(self._flush_sync)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"⚠️ [progress] immediate flush failed: {e}")

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


# ── Layer 1 — Mechanical pre-filter with IDF-weighted scoring ─────────────────


def _transcript_body(transcript_or_ingested) -> str:
    """EPIC-18: accept either a raw string (legacy) or an ingested dict {line_count, lines}.
    Returns plain text suitable for term-count / lexical scoring.
    """
    if isinstance(transcript_or_ingested, dict):
        lines = transcript_or_ingested.get("lines", [])
        return " ".join(ln.get("text", "") for ln in lines if isinstance(ln, dict))
    return transcript_or_ingested or ""


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




def extract_task_subjects(tasks: list[dict]) -> set[str]:
    """Extract subject tokens from a list of tasks (lowercased, stopword-filtered)."""
    tokens: set[str] = set()
    for t in tasks or []:
        for field in ("task", "next_step"):
            text = (t.get(field) or "").lower()
            for word in _re.findall(r"\b[a-z][a-z0-9_-]+\b", text):
                if len(word) > 2 and word not in _STOPWORDS:
                    tokens.add(word)
    return tokens


def score_existing_topic(
    candidate: dict, existing: dict, transcripts: dict[str, str], idf: dict[str, float],
    *, rare_idf_threshold: float = 1.0,
) -> dict:
    """Combined 0.0-1.0 mechanical match score for one existing topic.

    Composition:
      0.5 × IDF-weighted Jaccard on key_terms
      0.3 × task-subject Jaccard
      0.2 × normalised mention count of candidate's RARE key_terms in transcripts
    """
    cand_tokens = effective_token_set(candidate)
    exist_tokens = effective_token_set(existing)

    score_a = weighted_jaccard_tokens(cand_tokens, exist_tokens, idf)

    cand_subj = extract_task_subjects(candidate.get("tasks") or [])
    exist_subj = extract_task_subjects(existing.get("tasks") or [])
    union_subj = cand_subj | exist_subj
    score_b = (len(cand_subj & exist_subj) / len(union_subj)) if union_subj else 0.0

    rare_tokens = [t for t in cand_tokens if idf.get(t, 1.0) >= rare_idf_threshold]
    total_mentions = 0
    for transcript_val in transcripts.values():
        body = _transcript_body(transcript_val)
        if not body:
            continue
        total_mentions += sum(_count_term_occurrences(body, rare_tokens).values())
    score_c = min(total_mentions, 10) / 10.0

    combined = 0.5 * score_a + 0.3 * score_b + 0.2 * score_c

    rare_shared = sorted(
        t for t in (cand_tokens & exist_tokens)
        if idf.get(t, 1.0) >= rare_idf_threshold
    )
    return {
        "topic_id": existing.get("topic_id"),
        "name": existing.get("name"),
        "score_idf_jaccard": round(score_a, 3),
        "score_task_subject": round(score_b, 3),
        "score_transcript_mentions": round(score_c, 3),
        "combined_score": round(combined, 3),
        "shared_terms_rare": rare_shared,
        "rare_term_total_mentions": total_mentions,
    }


def lexical_precheck(
    candidate: dict,
    project_topics: list[dict],
    transcripts: dict[str, str],
    *,
    top_k: int = 3,
    threshold: float = 0.15,
) -> dict:
    """Layer 1 — mechanical scoring + pre-filter.

    Returns enriched result containing:
      - candidate_terms
      - idf summary (top 10 rare terms)
      - scored_topics (sorted desc by combined_score, each annotated with qualified=bool)
      - qualified_topic_ids (top_k with score >= threshold)
      - transcript_hits (kept for back-compat with the old UI panel)
      - verdict_hint: "mechanical_truly_new" | "needs_llm_eval" | "high_confidence_match"
    """
    candidate_terms = list(candidate.get("key_terms") or [])
    idf = compute_idf(project_topics)

    scored = [score_existing_topic(candidate, t, transcripts, idf) for t in project_topics]
    scored.sort(key=lambda s: -s["combined_score"])

    qualified_ids: set[str] = set()
    for s in scored[:top_k]:
        if s["combined_score"] >= threshold:
            qualified_ids.add(s["topic_id"])
    for s in scored:
        s["qualified"] = s["topic_id"] in qualified_ids

    # Back-compat transcript hits (used by older UI elements)
    transcript_hits: dict[str, dict] = {}
    for cid, transcript_val in transcripts.items():
        body = _transcript_body(transcript_val)
        by_term = _count_term_occurrences(body, candidate_terms)
        transcript_hits[cid] = {"total": sum(by_term.values()), "by_term": by_term}

    if not qualified_ids:
        verdict_hint = "mechanical_truly_new"
    elif scored and scored[0]["combined_score"] >= 0.5:
        verdict_hint = "high_confidence_match"
    else:
        verdict_hint = "needs_llm_eval"

    idf_top = sorted(idf.items(), key=lambda kv: -kv[1])[:10]

    return {
        "candidate_terms": candidate_terms,
        "idf_top_terms": [{"term": t, "idf": round(v, 3)} for t, v in idf_top],
        "scored_topics": scored,
        "qualified_topic_ids": sorted(qualified_ids),
        "threshold": threshold,
        "top_k": top_k,
        "transcript_hits": transcript_hits,
        "verdict_hint": verdict_hint,
        # IDF is needed by post-LLM rarity check; cached here as a flat list.
        "_idf_for_rarity_check": idf,
    }


# ── Post-LLM mechanical checks (defense-in-depth) ─────────────────────────────




def compute_confidence(result: dict) -> dict:
    """Compute the 0-100 confidence score for a verify_new_topic result,
    along with a step-by-step breakdown of how it was derived.

    Returns: {pct, label, color, rationale: [{step, delta_or_op, value}]}
    The rationale is a list of {step, op, value, running} entries that
    can be displayed in the UI or logged as a single line.
    """
    rationale: list[dict] = []
    running: float = 0

    # ── Base score ──
    mechanical_skip = result.get("mechanical_skip") is True
    verdict = result.get("verdict") or result.get("final_verdict")
    needs_review = bool(result.get("needs_manual_review"))
    if mechanical_skip:
        running = 95
        rationale.append({"step": "Mechanical pre-filter skipped LLM (0 qualified)", "op": "base", "value": 95, "running": 95})
    elif needs_review:
        running = 40
        rationale.append({"step": "Flagged for manual review (needs_manual_review=true)", "op": "base", "value": 40, "running": 40})
    elif verdict == "truly_new":
        running = 85
        rationale.append({"step": "LLM verdict: truly_new", "op": "base", "value": 85, "running": 85})
    elif verdict == "should_be_merged_with":
        running = 85
        rationale.append({"step": "LLM verdict: should_be_merged_with", "op": "base", "value": 85, "running": 85})
    else:
        running = 60
        rationale.append({"step": "LLM verdict: undecided", "op": "base", "value": 60, "running": 60})

    # ── Citation verify pass rate ──
    citations = result.get("citations") or []
    verdict_cits = [c for c in citations if (c.get("for") or "verdict") == "verdict"]
    if verdict_cits:
        failed = len(result.get("failed_citations") or [])
        verified = max(len(verdict_cits) - failed, 0)
        rate = verified / len(verdict_cits)
        multiplier = 0.7 + 0.3 * rate
        new_running = running * multiplier
        rationale.append({
            "step": f"{verified}/{len(verdict_cits)} citation(s) verified verbatim ({int(rate * 100)}%)",
            "op": "× multiplier",
            "value": round(multiplier, 2),
            "running": round(new_running, 1),
        })
        running = new_running

    # ── Pre-filter target score nudge ──
    matched_id = result.get("matched_topic_id")
    precheck = result.get("lexical_precheck") or {}
    if verdict == "should_be_merged_with" and matched_id:
        scored = precheck.get("scored_topics") or []
        target = next((s for s in scored if s.get("topic_id") == matched_id), None)
        if target:
            score = target.get("combined_score", 0)
            if score >= 0.5:
                running += 5
                rationale.append({
                    "step": f"Strong mechanical signal on target (combined_score={score})",
                    "op": "+ bonus",
                    "value": 5,
                    "running": round(running, 1),
                })
            elif score < 0.15:
                running -= 10
                rationale.append({
                    "step": f"Weak mechanical signal on target (combined_score={score} below threshold)",
                    "op": "− penalty",
                    "value": 10,
                    "running": round(running, 1),
                })

    # ── Task-fit YES count ──
    evals = result.get("evaluations") or []
    yes_count = sum(1 for e in evals if e.get("task_fit") == "yes")
    if verdict == "should_be_merged_with" and yes_count > 0:
        running += 5
        rationale.append({
            "step": f"{yes_count} task-fit evaluation(s) confirmed YES",
            "op": "+ bonus",
            "value": 5,
            "running": round(running, 1),
        })

    # ── Clamp + label ──
    pct = max(0, min(100, round(running)))
    if pct >= 80:
        label, color = "High", "#006644"
    elif pct >= 50:
        label, color = "Moderate", "#974f0c"
    else:
        label, color = "Low", "#ae2a19"

    # EPIC-18 STREAM 4: auto-accept truly_new at confidence ≥75%.
    # merge verdicts are NEVER auto-accepted (wrong merge collapses; wrong new is reversible).
    auto_accept_eligible = (
        verdict == "truly_new"
        and pct >= 75
        and not needs_review
    )
    return {
        "pct": pct,
        "label": label,
        "color": color,
        "rationale": rationale,
        "auto_accept_eligible": auto_accept_eligible,  # EPIC-18 STREAM 4
    }


def format_confidence_log_line(conf: dict) -> str:
    """One-liner derivation for the progress log."""
    parts = []
    for r in conf["rationale"]:
        op = r["op"]
        val = r["value"]
        running = r["running"]
        if op == "base":
            parts.append(f"base {val}")
        elif "multiplier" in op:
            parts.append(f"×{val} → {running}")
        elif "+ bonus" in op:
            parts.append(f"+{val} → {running}")
        elif "− penalty" in op:
            parts.append(f"−{val} → {running}")
    return f"Confidence: {' '.join(parts)} = {conf['pct']}% ({conf['label']})"


def sanity_check_llm_vs_lexical(llm_result: dict, precheck: dict) -> str | None:
    """Compare LLM verdict to mechanical scoring. Flag string if they disagree.

    Now operates on the scored_topics list from the new lexical_precheck.
    """
    verdict = (llm_result or {}).get("verdict")
    matched_id = (llm_result or {}).get("matched_topic_id")
    scored = (precheck or {}).get("scored_topics") or []
    hits = (precheck or {}).get("transcript_hits") or {}

    if verdict == "should_be_merged_with" and matched_id:
        target = next((s for s in scored if s.get("topic_id") == matched_id), None)
        total_hits = sum(h["total"] for h in hits.values())
        if (target is None or target.get("combined_score", 0) < 0.05) and total_hits == 0:
            return "llm_recommends_merge_but_no_overlap"

    if verdict == "truly_new":
        # If any topic has very high combined score, LLM may have missed a merge
        for s in scored:
            if s.get("combined_score", 0) >= 0.5:
                return "llm_says_new_but_strong_overlap_exists"

    return None


def _looks_like_platform_term(term: str) -> bool:
    """Return True for terms that are vendor/platform/tool names (not subject matter).
    Used in post-LLM validation to detect "shared-platform-only" merges."""
    platform_terms = {
        "snowflake", "aws", "azure", "gcp", "google cloud", "python", "excel",
        "tableau", "power bi", "powerbi", "sql", "postgres", "mysql", "mongodb",
        "kafka", "spark", "airflow", "dbt", "looker", "salesforce", "sap",
        "oracle", "redshift", "databricks", "jira", "confluence", "github",
        "gitlab", "slack", "teams", "outlook", "google sheets", "google drive",
        "docker", "kubernetes", "k8s", "terraform", "ansible",
    }
    return (term or "").lower().strip() in platform_terms


def _build_verify_new_prompt(
    candidate: dict,
    project_topics: list[dict],
    transcripts: dict[str, dict],  # EPIC-18: now {call_id: ingested_dict}, not {call_id: raw_str}
    precheck: dict | None = None,
) -> str:
    """EPIC-18: transcripts are now ingested (line-numbered) dicts from v5 Stage 0.
    LLM sees `0001  <text>` line-prefixed format and cites by line range.
    """
    def _shape_topic_for_llm(t: dict) -> dict:
        return {
            "topic_id": t.get("topic_id"),
            "name": t.get("name"),
            "summary": t.get("summary") or "",
            "tasks": t.get("tasks") or [],
        }
    transcripts_block = "\n\n".join(
        f"--- CALL {cid} ({ing['line_count']} lines) ---\n"
        + "\n".join(f"{ln['idx']}  {ln['text']}" for ln in ing.get("lines", []))
        for cid, ing in transcripts.items()
    )
    project_topics_block = json.dumps([_shape_topic_for_llm(t) for t in project_topics], indent=2)
    candidate_block = json.dumps(_shape_topic_for_llm(candidate), indent=2)
    precheck_block = ""
    if precheck:
        precheck_block = (
            "\n\nLEXICAL PRE-CHECK (deterministic, fyi — your own analysis should be primary):\n"
            f"{json.dumps(precheck, indent=2)}\n"
        )
    return (
        f"{VERIFY_NEW_TOPIC_PROMPT}\n\n"
        f"CANDIDATE NEW TOPIC:\n{candidate_block}\n\n"
        f"EXISTING PROJECT TOPICS:\n{project_topics_block}\n\n"
        f"PAST TRANSCRIPTS (line-numbered):\n{transcripts_block}"
        f"{precheck_block}"
    )


async def run_verify_new(
    candidate: dict,
    project_topics: list[dict],
    transcripts: dict[str, dict],  # EPIC-18: ingested dicts {call_id: {line_count, lines}}
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
        await _log(f"      [{name}] attempt {attempt}: asking LLM (task-fit framing — would candidate's tasks belong on any existing topic's task list?) over {len(project_topics)} existing topic(s), referencing {len(transcripts)} past transcript(s)")
        result = await _call_llm(prompt, llm, model=model)
        # EPIC-18 S2.3: some models wrap the verdict in an outer key.
        # Detect common wrappers and unwrap before the bare-list check.
        if isinstance(result, dict) and "evaluations" not in result and "verdict" not in result and "final_verdict" not in result:
            for k in ("result", "data", "response", "judgement", "judgment", "output"):
                inner = result.get(k)
                if isinstance(inner, dict) and ("verdict" in inner or "final_verdict" in inner or "evaluations" in inner):
                    await _log(f"      [{name}] attempt {attempt}: LLM wrapped response under '{k}' key — unwrapping")
                    result = inner
                    break
        # Recovery: some LLMs (e.g. deepseek) return ONLY the evaluations
        # array instead of the wrapping dict. Detect that shape and wrap it
        # — defaults to truly_new with the evaluations preserved.
        if isinstance(result, list) and result and all(
            isinstance(e, dict) and "task_fit" in e for e in result
        ):
            await _log(f"      [{name}] attempt {attempt}: LLM returned a bare evaluations array — wrapping as truly_new")
            yes_count = sum(1 for e in result if e.get("task_fit") == "yes")
            if yes_count == 1:
                matched = next((e for e in result if e.get("task_fit") == "yes"), {})
                result = {
                    "evaluations": result,
                    "verdict": "should_be_merged_with",
                    "final_verdict": "should_be_merged_with",
                    "matched_topic_id": matched.get("topic_id"),
                    "matched_topic_name": matched.get("topic_name"),
                    "merge_reasoning": matched.get("reason", ""),
                    "citations": [],
                }
            else:
                result = {
                    "evaluations": result,
                    "verdict": "truly_new",
                    "final_verdict": "truly_new",
                    "matched_topic_id": None,
                    "matched_topic_name": None,
                    "merge_reasoning": "No existing topic had task_fit=yes." if yes_count == 0 else f"{yes_count} topics had task_fit=yes (ambiguous) — defaulting to truly_new.",
                    "citations": [],
                }
        if not isinstance(result, dict):
            logger.warning("⚠️ [verify_new] LLM returned non-dict on attempt %d", attempt)
            await _log(f"      [{name}] attempt {attempt}: LLM response invalid — retrying")
            failures = ["LLM returned non-dict"]
            continue
        # Normalise verdict field (new prompt outputs "final_verdict"; old code expects "verdict")
        if "final_verdict" in result and "verdict" not in result:
            result["verdict"] = result["final_verdict"]
        # EPIC-19: normalize verdict names (prompt uses confirmed_new / suggest_merge_with;
        # legacy downstream code may still check truly_new / should_be_merged_with).
        v = result.get("verdict")
        if v == "confirmed_new":
            result["verdict"] = "truly_new"  # legacy alias
        elif v == "suggest_merge_with":
            result["verdict"] = "should_be_merged_with"  # legacy alias
        result["final_verdict"] = result["verdict"]
        # Log per-topic evaluations if present
        evals = result.get("evaluations") or []
        if evals:
            yes_count = sum(1 for e in evals if e.get("task_fit") == "yes")
            await _log(f"      [{name}] attempt {attempt}: LLM evaluated {len(evals)} existing topic(s) — {yes_count} task-fit YES, {len(evals) - yes_count} NO")
            for e in evals:
                if e.get("task_fit") == "yes":
                    await _log(f"          ✓ \"{e.get('topic_name', '?')}\": {e.get('reason', '?')}")
        cits = result.get("citations") or []
        # EPIC-18: evidence_lines are required from the LLM directly (no backfill).
        # verify_evidence_lines checks line-range bounds against ingested dicts.
        await _log(f"      [{name}] attempt {attempt}: LLM responded with {len(cits)} supporting citation(s) — checking evidence_lines bounds")
        ok, failures = verify_evidence_lines(cits, transcripts)
        if ok:
            await _log(f"      [{name}] all {len(cits)} quote(s) found in the transcripts ✓")
            final = {**result, "needs_manual_review": False}

            # EPIC-19: simplified post-LLM check.
            # Only the ≥2 verdict-citation count check is retained.
            # Rarity + reasoning-anchor + sanity-flag stack removed (was producing
            # false-positive penalties on topics with common/code-like terms; see
            # EPIC-19 spec Section 1).
            if final.get("verdict") == "should_be_merged_with":
                verdict_cits = [c for c in cits if (c.get("for") or "verdict") == "verdict"]
                if len(verdict_cits) < 2:
                    final["needs_manual_review"] = True
                    final.setdefault("failed_citations", []).append(
                        f"merge verdict requires ≥2 verdict citations, got {len(verdict_cits)}"
                    )
                    await _log(f"      [{name}] ⚠ merge has {len(verdict_cits)} verdict citation(s) (need ≥2) — needs review")

            # Strip the cached _idf_for_rarity_check from the persisted precheck
            # so it doesn't bloat the cache JSONB unnecessarily.
            if precheck is not None:
                precheck_persisted = {k: v for k, v in precheck.items() if not k.startswith("_")}
                final["lexical_precheck"] = precheck_persisted

            # Compute + persist + log the confidence breakdown
            final["confidence"] = compute_confidence(final)
            await _log(f"      [{name}] {format_confidence_log_line(final['confidence'])}")
            return final
        logger.warning("⚠️ [verify_new] citation verify failed on attempt %d: %s", attempt, failures)
        await _log(f"      [{name}] attempt {attempt}: {len(failures)} of {len(cits)} quote(s) NOT found in the transcripts — retrying")
        prompt = (
            f"{prompt}\n\nPREVIOUS ATTEMPT FAILED citation verification with these errors:\n"
            f"{json.dumps(failures, indent=2)}\nRedo with verbatim quotes copy-pasted from transcripts."
        )

    # If both attempts produced a non-dict (e.g. LLM returned a bare list of
    # evaluations), we can't spread `result` — fall back to a stub verdict.
    base = result if isinstance(result, dict) else {
        "verdict": "truly_new",
        "final_verdict": "truly_new",
        "matched_topic_id": None,
        "matched_topic_name": None,
        "evaluations": result if isinstance(result, list) else [],
        "citations": [],
        "merge_reasoning": "LLM returned a non-dict response on both attempts — defaulting to truly_new pending manual review.",
    }
    final = {
        **base,
        "needs_manual_review": True,
        "failed_citations": failures,
    }
    if precheck is not None:
        final["lexical_precheck"] = {k: v for k, v in precheck.items() if not k.startswith("_")}
        flag = sanity_check_llm_vs_lexical(final, precheck)
        if flag:
            final["sanity_flag"] = flag
    # Confidence on the manual-review fallback path too
    final["confidence"] = compute_confidence(final)
    await _log(f"      [{name}] {format_confidence_log_line(final['confidence'])}")
    return final




async def run_verify_not_discussed(
    topic: dict, ingested_transcript: dict, *,
    call_id: str, llm: str, model: str | None, log_fn=None,
) -> dict:
    """EPIC-19: Pass 2 — verify a topic wasn't discussed in the supplied transcript.

    Args:
        topic: existing project topic with name + tasks anchor
        ingested_transcript: v5 Stage 0 ingest output dict {line_count, lines}
        call_id: id of the current call (used in citation call_id)
    """
    name = topic.get("name", "?")

    async def _log(msg: str) -> None:
        if log_fn:
            await log_fn(msg)

    transcript_block = (
        f"--- CALL {call_id} ({ingested_transcript['line_count']} lines) ---\n"
        + "\n".join(f"{ln['idx']}  {ln['text']}" for ln in ingested_transcript.get("lines", []))
    )
    anchor = json.dumps({
        "topic_name": topic.get("name"),
        "tasks": [
            {"task": t.get("task"), "next_step": t.get("next_step"),
             "key_terms": t.get("key_terms", [])}
            for t in (topic.get("tasks") or [])
        ],
    }, indent=2)
    prompt = (
        f"{VERIFY_NOT_DISCUSSED_PROMPT}\n\n"
        f"TOPIC ANCHOR (existing project topic, from previous call's project_updates):\n{anchor}\n\n"
        f"CURRENT CALL TRANSCRIPT (line-numbered):\n{transcript_block}"
    )
    await _log(f"      [{name}] asking LLM to scan current call for any mention")
    result = await _call_llm(prompt, llm, model=model)
    if not isinstance(result, dict):
        return {
            "verdict": "confirmed_not_discussed",
            "needs_manual_review": True,
            "reasoning": "LLM non-dict response — defaulting to user's decision",
            "citation": None,
        }
    cit = result.get("citation")
    cits = [cit] if cit else []
    ok, failures = verify_evidence_lines(cits, {call_id: ingested_transcript})
    result["needs_manual_review"] = not ok
    if not ok:
        result["failed_citations"] = failures
    return result


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
