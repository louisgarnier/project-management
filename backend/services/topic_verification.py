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


# ── Layer 1 — Mechanical pre-filter with IDF-weighted scoring ─────────────────


_STOPWORDS = {
    "the", "a", "an", "to", "and", "or", "for", "with", "of", "in", "on", "at",
    "by", "from", "this", "that", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "could", "can", "may", "might", "must", "shall", "their", "our", "us",
    "we", "they", "he", "she", "it", "you", "your", "my", "as", "if",
    "when", "where", "what", "who", "how", "why", "all", "any", "some", "no",
    "not", "more", "less", "very", "just", "also", "than", "then", "but",
    "into", "out", "off", "over", "under", "again", "further", "once",
}


def _norm_terms(terms: list[str]) -> set[str]:
    return {(s or "").lower().strip() for s in (terms or []) if (s or "").strip()}


def effective_token_set(topic_or_candidate: dict) -> set[str]:
    """Build the effective token bag for lexical matching.

    v4 task-centric: also aggregates per-task key_terms across all tasks of
    the topic, in addition to topic.key_terms and topic.name. This way the
    new model and legacy data both feed the same scoring.

    Solves the paraphrase problem: "stress testing" (key_term) vs "stress test"
    (different key_term) now overlap on the tokens {stress, testing} vs
    {stress, test} respectively — at least "stress" is shared.
    """
    tokens: set[str] = set()
    sources: list[str] = []
    # key_terms (may be multi-word)
    for kt in (topic_or_candidate.get("key_terms") or []):
        if kt:
            sources.append(str(kt))
    # name (always single phrase, may be multi-word)
    if topic_or_candidate.get("name"):
        sources.append(str(topic_or_candidate["name"]))
    # v4 per-task aggregation — each task's key_terms feed the parent topic's bag
    for task in (topic_or_candidate.get("tasks") or []):
        if isinstance(task, dict):
            for kt in (task.get("key_terms") or []):
                if kt:
                    sources.append(str(kt))
    for src in sources:
        for word in _re.findall(r"\b[a-z][a-z0-9_-]+\b", src.lower()):
            if len(word) > 2 and word not in _STOPWORDS:
                tokens.add(word)
    return tokens


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


def compute_idf(project_topics: list[dict]) -> dict[str, float]:
    """IDF computed over EFFECTIVE TOKEN SETS (key_terms + name tokenised).

    Common tokens (appear in many topics) get low IDF; rare tokens high IDF.
    Formula: IDF(t) = log((N + 1) / (df + 1)) + 1
    """
    N = max(len(project_topics), 1)
    df: dict[str, int] = {}
    for t in project_topics:
        for tok in effective_token_set(t):
            df[tok] = df.get(tok, 0) + 1
    return {tok: _math.log((N + 1) / (count + 1)) + 1.0 for tok, count in df.items()}


def weighted_jaccard_tokens(a_tokens: set[str], b_tokens: set[str], idf: dict[str, float]) -> float:
    """IDF-weighted Jaccard on pre-computed token sets."""
    inter = a_tokens & b_tokens
    union = a_tokens | b_tokens
    if not union:
        return 0.0
    inter_w = sum(idf.get(t, 1.0) for t in inter)
    union_w = sum(idf.get(t, 1.0) for t in union)
    return inter_w / union_w if union_w > 0 else 0.0


def weighted_jaccard(a_terms: list[str], b_terms: list[str], idf: dict[str, float]) -> float:
    """Legacy entry point: takes raw term lists, builds effective token sets, then scores.
    Kept for tests + external callers."""
    set_a = effective_token_set({"key_terms": a_terms})
    set_b = effective_token_set({"key_terms": b_terms})
    return weighted_jaccard_tokens(set_a, set_b, idf)


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
    for body in transcripts.values():
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
    for cid, body in transcripts.items():
        by_term = _count_term_occurrences(body or "", candidate_terms)
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


def check_citation_rarity(
    citations: list[dict], candidate: dict, idf: dict[str, float],
    *, rare_idf_threshold: float = 1.0,
) -> list[str]:
    """Each verdict citation's quote must contain at least one RARE token
    from the candidate's effective token set (key_terms + name tokens).
    Generic platform terms (low IDF) get filtered out."""
    cand_tokens = effective_token_set(candidate)
    rare = {t for t in cand_tokens if idf.get(t, 1.0) >= rare_idf_threshold}
    if not rare:
        return []
    failures: list[str] = []
    for i, c in enumerate(citations):
        if (c.get("for") or "verdict") != "verdict":
            continue
        quote = (c.get("quote") or "")
        if not any(rt in quote.lower() for rt in rare):
            preview = quote if len(quote) <= 240 else quote[:240] + "…"
            failures.append(
                f"citation #{i}: quote contains no rare candidate term — evidence too weak (only generic shared terms) — \"{preview}\""
            )
    return failures


def check_reasoning_references_tasks(
    reasoning: str, candidate_tasks: list[dict], target_tasks: list[dict],
) -> list[str]:
    """merge_reasoning must reference at least one specific task from candidate AND target.
    Wishy-washy reasoning ('both are about X') gets caught here."""
    failures: list[str] = []
    reasoning_lower = (reasoning or "").lower()
    if not reasoning_lower.strip():
        return ["merge_reasoning is empty"]

    def task_significant_words(tasks: list[dict]) -> set[str]:
        out: set[str] = set()
        for t in tasks or []:
            for field in ("task", "next_step"):
                text = (t.get(field) or "").lower()
                for w in _re.findall(r"\b[a-z][a-z0-9_-]{3,}\b", text):
                    if w not in _STOPWORDS:
                        out.add(w)
        return out

    cand_words = task_significant_words(candidate_tasks)
    target_words = task_significant_words(target_tasks)
    has_cand_ref = any(w in reasoning_lower for w in cand_words) if cand_words else True
    has_target_ref = any(w in reasoning_lower for w in target_words) if target_words else True
    if not has_cand_ref:
        failures.append("merge_reasoning doesn't reference any specific candidate task")
    if not has_target_ref:
        failures.append("merge_reasoning doesn't reference any specific target task")
    return failures


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
    transcripts: dict[str, str],
    precheck: dict | None = None,
) -> str:
    transcripts_block = "\n\n".join(
        f"--- CALL {cid} ---\n{body}" for cid, body in transcripts.items()
    )
    # v3 (task-centric + task-fit): send FULL tasks for each existing topic.
    # If v4 data is present (tasks carry their own key_terms/OQ/decisions),
    # the LLM sees per-task context — granular work-continuity test.
    # Topic-level OQ/decisions still included for legacy v3 data fallback.
    project_topics_block = json.dumps(
        [
            {
                "topic_id": t.get("topic_id"),
                "name": t.get("name"),
                "key_terms": t.get("key_terms") or [],
                "summary": t.get("summary") or "",
                # tasks may carry per-task key_terms/OQ/decisions/citations (v4) or
                # just task/next_step/owner/status (v3) — LLM gets whatever is present.
                "tasks": t.get("tasks") or [],
                # Legacy topic-level OQ/decisions for v3 data
                "open_questions": t.get("open_questions") or [],
                "decisions": t.get("decisions") or [],
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
        await _log(f"      [{name}] attempt {attempt}: asking LLM (task-fit framing — would candidate's tasks belong on any existing topic's task list?) over {len(project_topics)} existing topic(s), referencing {len(transcripts)} past transcript(s)")
        result = await _call_llm(prompt, llm, model=model)
        if not isinstance(result, dict):
            logger.warning("⚠️ [verify_new] LLM returned non-dict on attempt %d", attempt)
            await _log(f"      [{name}] attempt {attempt}: LLM response invalid — retrying")
            failures = ["LLM returned non-dict"]
            continue
        # Normalise verdict field (new prompt outputs "final_verdict"; old code expects "verdict")
        if "final_verdict" in result and "verdict" not in result:
            result["verdict"] = result["final_verdict"]
        # Log per-topic evaluations if present
        evals = result.get("evaluations") or []
        if evals:
            yes_count = sum(1 for e in evals if e.get("task_fit") == "yes")
            await _log(f"      [{name}] attempt {attempt}: LLM evaluated {len(evals)} existing topic(s) — {yes_count} task-fit YES, {len(evals) - yes_count} NO")
            for e in evals:
                if e.get("task_fit") == "yes":
                    await _log(f"          ✓ \"{e.get('topic_name', '?')}\": {e.get('reason', '?')}")
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

            # ── Post-LLM mechanical defense-in-depth ──
            # Order of checks (any fail → downgrade to needs_manual_review):
            #   (a) ≥2 verdict-tagged citations for merge
            #   (b) Each verdict citation contains a RARE candidate key_term
            #   (c) merge_reasoning references both a candidate and a target task
            #   (d) Sanity-check LLM verdict against mechanical scoring
            if final.get("verdict") == "should_be_merged_with":
                verdict_cits = [c for c in cits if (c.get("for") or "verdict") == "verdict"]

                # (a) ≥2 citations
                if len(verdict_cits) < 2:
                    final["needs_manual_review"] = True
                    final["sanity_flag"] = "insufficient_verdict_citations"
                    final.setdefault("failed_citations", []).append(
                        f"merge verdict requires ≥2 verdict citations, got {len(verdict_cits)}"
                    )
                    await _log(f"      [{name}] ⚠ merge has {len(verdict_cits)} verdict citation(s) (need ≥2) — downgrading")

                # (b) Citation rarity check (each verdict citation must contain a rare candidate term)
                if not final.get("needs_manual_review") and precheck:
                    idf = precheck.get("_idf_for_rarity_check") or {}
                    rarity_fails = check_citation_rarity(verdict_cits, candidate, idf)
                    if rarity_fails:
                        final["needs_manual_review"] = True
                        final["sanity_flag"] = "citations_lack_rare_terms"
                        final.setdefault("failed_citations", []).extend(rarity_fails)
                        await _log(f"      [{name}] ⚠ citation rarity check failed: {len(rarity_fails)} citation(s) quote only generic terms — downgrading")

                # (c) Reasoning must reference both sides' tasks (no wishy-washy "both are about X")
                if not final.get("needs_manual_review") and precheck:
                    target_id = final.get("matched_topic_id")
                    target = next((p for p in project_topics if p.get("topic_id") == target_id), None)
                    if target:
                        reasoning_fails = check_reasoning_references_tasks(
                            final.get("merge_reasoning") or "",
                            candidate.get("tasks") or [],
                            target.get("tasks") or [],
                        )
                        if reasoning_fails:
                            final["needs_manual_review"] = True
                            final["sanity_flag"] = "reasoning_lacks_task_anchors"
                            final.setdefault("failed_citations", []).extend(reasoning_fails)
                            await _log(f"      [{name}] ⚠ merge_reasoning is too vague (doesn't name specific tasks): {'; '.join(reasoning_fails)} — downgrading")

            # (d) Sanity flag — LLM vs mechanical scoring (only set if no earlier flag)
            if precheck is not None:
                # Strip the cached _idf_for_rarity_check from the persisted precheck
                # so it doesn't bloat the cache JSONB unnecessarily.
                precheck_persisted = {k: v for k, v in precheck.items() if not k.startswith("_")}
                final["lexical_precheck"] = precheck_persisted
                if not final.get("sanity_flag"):
                    flag = sanity_check_llm_vs_lexical(final, precheck)
                    if flag:
                        final["sanity_flag"] = flag
                        await _log(f"      [{name}] ⚠ sanity flag: {flag} — LLM verdict disagrees with mechanical scoring")
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
        final["lexical_precheck"] = {k: v for k, v in precheck.items() if not k.startswith("_")}
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
