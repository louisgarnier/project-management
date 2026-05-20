# EPIC-16 — Project Updates RAG Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace auto-LLM merge in `project_updates` with 3 user-driven, citation-grounded verification passes against raw transcripts.

**Architecture:** Save & Continue out of `project_matching` becomes a pure DB advance. `project_updates` ships a 3-section layout (New / Not in call / Merged) with sequenced buttons (`① Verify new` → `② Verify not discussed` → `③ Extract updates`). Each button triggers a backend pass that reads raw transcripts (single source of truth), produces JSON with verbatim quote citations, and is post-verified before persistence. `needs_manual_review` flag handles unverifiable claims. `evidence_trail` JSONB carries the chronological audit per topic_update.

**Tech Stack:** Python/FastAPI backend, Supabase Postgres, Next.js/React frontend (TS). LLM via existing `_call_llm` infra (Claude Sonnet 4.6 1M context recommended for passes ① + ③).

**Reference spec:** `docs/project/config/2026-05-20-project-updates-rag-rework-design.md`

---

## File Structure

**Backend created:**
- `backend/database/migrations/030_epic16_rag_passes.sql` — schema + library seeds
- `backend/prompts/verify_new_topic.py` — Pass ① prompt body
- `backend/prompts/verify_not_discussed.py` — Pass ② prompt body (rewrites the old one)
- `backend/prompts/extract_topic_updates.py` — Pass ③ prompt body
- `backend/services/citation_verify.py` — verbatim-quote post-verifier
- `backend/services/topic_verification.py` — orchestration for the 3 passes (LLM call + verify + retry)
- `backend/tests/test_citation_verify.py`
- `backend/tests/test_topic_verification.py`

**Backend modified:**
- `backend/library/seed.py` — add 3 new system entries; soft-deprecate `project_topics`, `merge_verification`, `not_discussed_check`
- `backend/routers/topics.py` — add 3 endpoints; remove `merge-preview`; drop `BackgroundTask` from `save-matches`
- `backend/services/topics_service.py` — remove `run_merge_preview`, `_verify_merged_topics`, `run_verification_background`, `verify_not_discussed_topics` (old); update `save_topics` to persist `citations` + `evidence_trail`; update `validate_project_updates` to consume the 3 caches
- `backend/services/topic_lineage.py` — no change planned (existing helper still useful for prompt context but not source of truth)

**Frontend created:**
- `frontend/src/components/EvidenceTrail.tsx`
- `frontend/src/components/TopicCitationBadge.tsx`

**Frontend modified:**
- `frontend/src/components/ProjectUpdatesStage.tsx` — full rewrite to 3-section layout
- `frontend/src/components/ProjectMatchingStage.tsx` — minor: no more wait on background
- `frontend/src/components/TopicEvidenceDrawer.tsx` — enrich with evidence_trail rendering when present
- `frontend/src/components/TopicsTimeline.tsx` — small ⚠️ badge for `needs_manual_review`
- `frontend/src/api/client.ts` — add `verifyNew`, `verifyNotDiscussed`, `extractUpdates`; remove `mergePreview`
- `frontend/src/types/index.ts` — add `Citation`, `EvidenceTrailEntry`, `VerifyNewResult`, `VerifyNotDiscussedResult`, `ExtractedUpdateResult`

---

## Phase 1 — Backend foundation (DB + prompts + verify util)

### Task 1 — Migration #030: schema + library seeds

**Files:**
- Create: `backend/database/migrations/030_epic16_rag_passes.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
-- 030_epic16_rag_passes.sql
-- EPIC-16: Project Updates RAG rework
-- Manual application required via Supabase dashboard before backend restart.

-- 1. New status/cache columns on calls (6 total)
ALTER TABLE calls
  ADD COLUMN IF NOT EXISTS verify_new_status TEXT NOT NULL DEFAULT 'idle',
  ADD COLUMN IF NOT EXISTS verify_new_cache JSONB,
  ADD COLUMN IF NOT EXISTS verify_not_discussed_status TEXT NOT NULL DEFAULT 'idle',
  ADD COLUMN IF NOT EXISTS verify_not_discussed_cache JSONB,
  ADD COLUMN IF NOT EXISTS extract_updates_status TEXT NOT NULL DEFAULT 'idle',
  ADD COLUMN IF NOT EXISTS extract_updates_cache JSONB;

-- 2. Citation + evidence_trail + needs_manual_review on topic_updates
ALTER TABLE topic_updates
  ADD COLUMN IF NOT EXISTS citations JSONB,
  ADD COLUMN IF NOT EXISTS evidence_trail JSONB,
  ADD COLUMN IF NOT EXISTS needs_manual_review BOOLEAN NOT NULL DEFAULT false;

-- 3. Soft-deprecate the 3 old workflow prompt library entries
UPDATE artifact_library
SET seeded_by_default = false, is_system = false
WHERE category IN ('project_topics', 'merge_verification', 'not_discussed_check')
  AND is_system = true;
```

- [ ] **Step 2: Manual application**

Apply via Supabase Dashboard → SQL Editor → paste contents → Run. Verify columns exist:
```sql
SELECT column_name FROM information_schema.columns WHERE table_name = 'calls'
  AND column_name LIKE 'verify_%' OR column_name LIKE 'extract_%';
SELECT column_name FROM information_schema.columns WHERE table_name = 'topic_updates'
  AND column_name IN ('citations', 'evidence_trail', 'needs_manual_review');
```

Expected: 6 + 3 rows.

- [ ] **Step 3: Commit**

```bash
python3 scripts/git_ops.py commit \
  --files backend/database/migrations/030_epic16_rag_passes.sql \
  --message "[EPIC-16] migration 030: schema for RAG verification passes + soft-deprecate old workflow prompts"
```

---

### Task 2 — Workflow prompt bodies (3 files)

**Files:**
- Create: `backend/prompts/verify_new_topic.py`
- Create: `backend/prompts/verify_not_discussed.py` (overwrite the existing — old body becomes the new lean one)
- Create: `backend/prompts/extract_topic_updates.py`

- [ ] **Step 1: Write `verify_new_topic.py`**

```python
"""Pass ① — verify_new_topic prompt body."""

VERIFY_NEW_TOPIC_PROMPT: str = """\
You are a forensic transcript analyst. Your ONLY source of truth is the
transcripts provided below. NEVER invent claims.

TASK: For the candidate new topic provided, determine:
  (a) Is this topic genuinely new (not discussed in any previous call) OR
      should it be merged into an existing project topic?
  (b) Are the tasks/open_questions/decisions extracted at the call_topics
      stage actually grounded in the current call's transcript?

RULES:
1. Every claim or verdict MUST be supported by a verbatim quote from one of
   the supplied transcripts. No paraphrasing.
2. Quotes are copy-paste from transcript body — exact text.
3. If you cannot find a supporting quote, say "NOT FOUND" — do not guess.
4. Citation format: {"call_id": "<uuid>", "lines": "X-Y", "quote": "<verbatim>"}

OUTPUT (strict JSON):
{
  "verdict": "truly_new" | "should_be_merged_with",
  "matched_topic_id": "<uuid or null>",
  "matched_topic_name": "<string or null>",
  "extraction_grounded": true | false,
  "ungrounded_items": [
    {"type": "task|open_question|decision", "text": "<the unrelated item>"}
  ],
  "citations": [
    {"call_id": "...", "lines": "...", "quote": "...", "for": "verdict|extraction"}
  ]
}
"""
```

- [ ] **Step 2: Overwrite `verify_not_discussed.py`** (replaces existing `not_discussed_check.py` content; keep filename for diff continuity OR create new and delete old — pick create-new)

Create `backend/prompts/verify_not_discussed.py`:
```python
"""Pass ② — verify_not_discussed prompt body."""

VERIFY_NOT_DISCUSSED_PROMPT: str = """\
You are a forensic transcript analyst. Your ONLY source of truth is the
transcript provided below. NEVER invent.

TASK: Determine whether the topic identified by its name + key_terms was
discussed in this call's transcript.

RULES:
1. Verdict must be backed by a verbatim quote if "actually_discussed".
2. Quote is copy-paste. No paraphrasing.
3. If you cannot find any mention, return "not_discussed". Do not over-claim.

OUTPUT (strict JSON):
{
  "verdict": "not_discussed" | "actually_discussed",
  "citation": {"call_id": "<uuid>", "lines": "X-Y", "quote": "<verbatim>"} | null
}
"""
```

- [ ] **Step 3: Write `extract_topic_updates.py`**

```python
"""Pass ③ — extract_topic_updates prompt body."""

EXTRACT_TOPIC_UPDATES_PROMPT: str = """\
You are a forensic transcript analyst. Your ONLY source of truth is the
transcripts provided below. NEVER invent.

TASK: For the topic identified by its name + key_terms, re-read ALL the
provided transcripts (chronologically across calls 1..N) and produce a
complete snapshot of the topic's current state as of the latest call.

Output two things:
  1. extracted_snapshot — the current state (summary, status, tasks, OQ,
     decisions). Each task/OQ/decision MUST have a primary_citation pointing
     to the transcript passage that introduced it (or last meaningfully
     updated it). Supporting citations are optional.
  2. evidence_trail — chronological list of every passage across all calls
     where this topic was mentioned, with a short action_label describing
     what happened there.

RULES:
1. Use ONLY the topic name + key_terms to anchor your search. Ignore any
   prior summaries you may have seen in past sessions.
2. Verbatim quotes only. Copy-paste from transcript body.
3. Distinguish carefully between different tasks and their follow-ups. Do
   NOT merge unrelated tasks. Each task is one discrete action.
4. status rollup: "open" if any task open, else "in_progress" if any
   in_progress, else "resolved".
5. action_label vocabulary: "first raised", "task added", "next step
   added", "decision recorded", "open question raised", "OQ resolved",
   "status change", "owner reassigned", "scope expanded", "follow-up
   noted". Pick the most specific.

OUTPUT (strict JSON):
{
  "extracted_snapshot": {
    "summary": "<2-4 sentences synthesising the topic state>",
    "status": "open" | "in_progress" | "resolved",
    "tasks": [
      {
        "task_id": "<uuid or null for new>",
        "task": "<task description>",
        "next_step": "<next action>",
        "owner": "<owner name or empty>",
        "status": "open|in_progress|resolved",
        "primary_citation": {...},
        "supporting_citations": [...]
      }
    ],
    "open_questions": [
      {"id": "<uuid or null>", "text": "...", "owner": "...", "status": "...", "primary_citation": {...}}
    ],
    "decisions": [
      {"id": "<uuid or null>", "text": "...", "primary_citation": {...}, "supporting_citations": [...]}
    ]
  },
  "evidence_trail": [
    {"call_id": "...", "citation": {...}, "action_label": "..."}
    // ordered chronologically across all calls
  ]
}
"""
```

- [ ] **Step 4: Run a quick import-sanity check**

Run: `python3 -c "from backend.prompts.verify_new_topic import VERIFY_NEW_TOPIC_PROMPT; from backend.prompts.verify_not_discussed import VERIFY_NOT_DISCUSSED_PROMPT; from backend.prompts.extract_topic_updates import EXTRACT_TOPIC_UPDATES_PROMPT; print('ok', len(VERIFY_NEW_TOPIC_PROMPT), len(VERIFY_NOT_DISCUSSED_PROMPT), len(EXTRACT_TOPIC_UPDATES_PROMPT))"`

Expected: `ok <n1> <n2> <n3>` — three nonzero integers.

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit \
  --files backend/prompts/verify_new_topic.py backend/prompts/verify_not_discussed.py backend/prompts/extract_topic_updates.py \
  --message "[EPIC-16] feat: add 3 RAG verification prompt bodies (verify_new_topic, verify_not_discussed, extract_topic_updates)"
```

---

### Task 3 — Library seed: register 3 new entries

**Files:**
- Modify: `backend/library/seed.py`
- Modify: `backend/tests/test_library_seed.py` (relax/update assertion for v3 entry — already failing pre-existing)

- [ ] **Step 1: Write the failing test first**

In `backend/tests/test_library_seed.py`, add:

```python
def test_three_new_rag_workflow_entries_seeded():
    """EPIC-16: verify_new_topic, verify_not_discussed, extract_topic_updates exist as system seeded_by_default entries."""
    from backend.library.seed import SYSTEM_LIBRARY
    cats = {e["category"] for e in SYSTEM_LIBRARY if e.get("is_system") and e.get("seeded_by_default")}
    assert "verify_new_topic" in cats
    assert "verify_not_discussed" in cats
    assert "extract_topic_updates" in cats


def test_old_workflow_prompts_not_seeded_by_default():
    """EPIC-16: project_topics / merge_verification / not_discussed_check (old) must no longer be seeded_by_default=True."""
    from backend.library.seed import SYSTEM_LIBRARY
    for e in SYSTEM_LIBRARY:
        if e["category"] in ("project_topics", "merge_verification", "not_discussed_check"):
            assert e.get("seeded_by_default") is False, f"{e['category']} should no longer be seeded by default"
```

- [ ] **Step 2: Run tests — expect fail**

Run: `python3 -m pytest backend/tests/test_library_seed.py::test_three_new_rag_workflow_entries_seeded -v`
Expected: FAIL (3 categories missing in SYSTEM_LIBRARY).

- [ ] **Step 3: Update `backend/library/seed.py`**

At top of file, add imports:
```python
from backend.prompts.verify_new_topic import VERIFY_NEW_TOPIC_PROMPT
from backend.prompts.verify_not_discussed import VERIFY_NOT_DISCUSSED_PROMPT
from backend.prompts.extract_topic_updates import EXTRACT_TOPIC_UPDATES_PROMPT
```

In `SYSTEM_LIBRARY` list, add 3 new entries (after existing workflow prompts, before artifacts tier):
```python
    {
        "name": "Verify New Topic (RAG)",
        "description": "Pass ① of project_updates. For each topic classified as new by matching, checks all prior transcripts to confirm it isn't a missed match, and verifies the call_topics extraction is grounded.",
        "kind": "llm",
        "prompt": VERIFY_NEW_TOPIC_PROMPT,
        "template_id": None,
        "llm": "openrouter",
        "model": "anthropic/claude-sonnet-4-6",
        "context_scope": "project",
        "category": "verify_new_topic",
        "is_system": True,
        "seeded_by_default": True,
    },
    {
        "name": "Verify Not Discussed (RAG)",
        "description": "Pass ② of project_updates. For each old topic absent from match groups, checks the current call's transcript only to confirm it wasn't actually mentioned.",
        "kind": "llm",
        "prompt": VERIFY_NOT_DISCUSSED_PROMPT,
        "template_id": None,
        "llm": "openrouter",
        "model": "anthropic/claude-sonnet-4-6",
        "context_scope": "call",
        "category": "verify_not_discussed",
        "is_system": True,
        "seeded_by_default": True,
    },
    {
        "name": "Extract Topic Updates (RAG)",
        "description": "Pass ③ of project_updates. Re-extracts each merged topic from raw transcripts (calls 1..N) and produces a citation-grounded snapshot + chronological evidence_trail. Replaces the old auto-merge prompt.",
        "kind": "llm",
        "prompt": EXTRACT_TOPIC_UPDATES_PROMPT,
        "template_id": None,
        "llm": "openrouter",
        "model": "anthropic/claude-sonnet-4-6",
        "context_scope": "project",
        "category": "extract_topic_updates",
        "is_system": True,
        "seeded_by_default": True,
    },
```

Update the 3 deprecated entries inline (find them in the same file and change `seeded_by_default: True → False`, `is_system: True → False`):
- `project_topics` entry
- `merge_verification` entry
- `not_discussed_check` entry

- [ ] **Step 4: Run tests — expect pass**

Run: `python3 -m pytest backend/tests/test_library_seed.py -v`
Expected: all pass (including the previously-failing pre-existing v2 test which now reflects v3 + new RAG entries).

Note: the pre-existing `test_v2_call_topics_entry_exists_and_is_default` may need updating to assert against `"v3"` instead of `"v2"` — fix it inline if it still fails.

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit \
  --files backend/library/seed.py backend/tests/test_library_seed.py \
  --message "[EPIC-16] feat: register 3 RAG workflow prompts in library seed + soft-deprecate old workflow prompts"
```

---

### Task 4 — Citation post-verifier utility

**Files:**
- Create: `backend/services/citation_verify.py`
- Create: `backend/tests/test_citation_verify.py`

- [ ] **Step 1: Write the failing tests first**

Create `backend/tests/test_citation_verify.py`:

```python
"""Tests for citation_verify — verbatim quote post-verifier."""

from backend.services.citation_verify import verify_citations, find_quote_lines


def test_verify_citations_all_pass():
    transcripts = {"call-1": "Hello world. This is a transcript.\nLine two here."}
    cits = [{"call_id": "call-1", "quote": "Hello world", "lines": ""}]
    ok, fails = verify_citations(cits, transcripts)
    assert ok is True
    assert fails == []


def test_verify_citations_missing_quote():
    transcripts = {"call-1": "Hello world."}
    cits = [{"call_id": "call-1", "quote": "Not present here", "lines": ""}]
    ok, fails = verify_citations(cits, transcripts)
    assert ok is False
    assert len(fails) == 1
    assert "not found" in fails[0].lower()


def test_verify_citations_missing_call_id():
    transcripts = {"call-1": "Hello"}
    cits = [{"call_id": "call-99", "quote": "Hello", "lines": ""}]
    ok, fails = verify_citations(cits, transcripts)
    assert ok is False
    assert "call-99" in fails[0]


def test_verify_citations_empty_list_passes():
    ok, fails = verify_citations([], {"call-1": "anything"})
    assert ok is True
    assert fails == []


def test_find_quote_lines_returns_range():
    body = "Line one\nLine two\nLine three\n"
    rng = find_quote_lines("Line two", body)
    assert rng == "2-2"


def test_find_quote_lines_returns_multi_line_range():
    body = "Line one\nQuote starts\ncontinues here\nLine four"
    rng = find_quote_lines("Quote starts\ncontinues here", body)
    assert rng == "2-3"


def test_find_quote_lines_returns_none_when_not_found():
    assert find_quote_lines("nope", "abc") is None
```

- [ ] **Step 2: Run tests — expect fail**

Run: `python3 -m pytest backend/tests/test_citation_verify.py -v`
Expected: FAIL (module not yet imported).

- [ ] **Step 3: Implement `backend/services/citation_verify.py`**

```python
"""Verbatim-quote post-verifier for RAG citations."""


def verify_citations(citations: list[dict], transcripts_by_call: dict[str, str]) -> tuple[bool, list[str]]:
    """For each citation, check the quote appears verbatim in the cited call's transcript.

    Args:
        citations: list of {"call_id": str, "quote": str, ...} dicts.
        transcripts_by_call: {call_id: transcript_body} map.

    Returns:
        (all_ok, list_of_failure_messages). Empty failures => all_ok=True.
    """
    failed: list[str] = []
    for i, c in enumerate(citations):
        call_id = c.get("call_id")
        quote = c.get("quote", "")
        if not call_id:
            failed.append(f"citation #{i}: missing call_id")
            continue
        body = transcripts_by_call.get(call_id)
        if body is None:
            failed.append(f"citation #{i}: call_id {call_id!r} not in supplied transcripts")
            continue
        if not quote:
            failed.append(f"citation #{i}: empty quote")
            continue
        if quote not in body:
            failed.append(
                f"citation #{i}: quote not found verbatim in call {call_id} transcript"
            )
    return (len(failed) == 0, failed)


def find_quote_lines(quote: str, transcript_body: str) -> str | None:
    """Find a verbatim quote in transcript_body and return the line range as 'X-Y'.

    Lines are 1-indexed. Returns None if the quote is not found.
    """
    idx = transcript_body.find(quote)
    if idx == -1:
        return None
    before = transcript_body[:idx]
    start_line = before.count("\n") + 1
    end_line = start_line + quote.count("\n")
    return f"{start_line}-{end_line}"
```

- [ ] **Step 4: Run tests — expect pass**

Run: `python3 -m pytest backend/tests/test_citation_verify.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit \
  --files backend/services/citation_verify.py backend/tests/test_citation_verify.py \
  --message "[EPIC-16] feat: citation verifier — verbatim quote check + line-range computation"
```

---

## Phase 2 — Backend passes

### Task 5 — Topic verification service: `run_verify_new` (Pass ①)

**Files:**
- Create: `backend/services/topic_verification.py`
- Modify: `backend/routers/topics.py` (add endpoint at the bottom)
- Create: `backend/tests/test_topic_verification.py`

- [ ] **Step 1: Write failing test for Pass ①**

Create `backend/tests/test_topic_verification.py`:

```python
"""Tests for topic_verification — the 3 RAG passes orchestration."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services import topic_verification as tv


def _llm_returns(payload):
    """Build an AsyncMock returning a fixed JSON-serializable payload."""
    return AsyncMock(return_value=payload)


def test_run_verify_new_truly_new(monkeypatch):
    """Happy path: LLM returns truly_new with one citation, post-verify passes."""
    transcripts = {"call-1": "We talked about onboarding redesign."}
    project_topics = []  # no prior topics → trivially truly new
    candidate = {
        "name": "Customer onboarding redesign",
        "key_terms": ["onboarding"],
        "tasks": [{"task": "Mockup new flow", "next_step": "", "owner": "", "status": "open"}],
        "open_questions": [],
        "decisions": [],
    }
    llm_result = {
        "verdict": "truly_new",
        "matched_topic_id": None,
        "matched_topic_name": None,
        "extraction_grounded": True,
        "ungrounded_items": [],
        "citations": [
            {"call_id": "call-1", "lines": "1-1", "quote": "onboarding redesign", "for": "extraction"}
        ],
    }
    monkeypatch.setattr(tv, "_call_llm", _llm_returns(llm_result))

    out = asyncio.run(tv.run_verify_new(candidate, project_topics, transcripts, llm="claude", model=None))
    assert out["verdict"] == "truly_new"
    assert out["needs_manual_review"] is False
    assert len(out["citations"]) == 1


def test_run_verify_new_retries_then_flags_manual_review(monkeypatch):
    """When LLM citations fail post-verify twice, return needs_manual_review=True."""
    transcripts = {"call-1": "real body text."}
    candidate = {"name": "Foo", "key_terms": ["foo"]}
    llm_result_bad = {
        "verdict": "truly_new",
        "matched_topic_id": None,
        "matched_topic_name": None,
        "extraction_grounded": True,
        "ungrounded_items": [],
        "citations": [{"call_id": "call-1", "lines": "1-1", "quote": "FABRICATED", "for": "extraction"}],
    }
    mock_llm = AsyncMock(side_effect=[llm_result_bad, llm_result_bad])
    monkeypatch.setattr(tv, "_call_llm", mock_llm)

    out = asyncio.run(tv.run_verify_new(candidate, [], transcripts, llm="claude", model=None))
    assert out["needs_manual_review"] is True
    assert mock_llm.call_count == 2  # 1 initial + 1 retry
```

- [ ] **Step 2: Run tests — expect fail (module missing)**

Run: `python3 -m pytest backend/tests/test_topic_verification.py::test_run_verify_new_truly_new -v`
Expected: FAIL — `topic_verification` module not found.

- [ ] **Step 3: Implement `backend/services/topic_verification.py` (Pass ① only for now)**

```python
"""Orchestration for the 3 RAG verification passes (EPIC-16)."""

import json
import logging

from backend.prompts.verify_new_topic import VERIFY_NEW_TOPIC_PROMPT
from backend.services.citation_verify import verify_citations, find_quote_lines

logger = logging.getLogger("calltracker.topic_verification")


# Imported here so tests can monkeypatch a single symbol.
async def _call_llm(prompt: str, llm: str, *, model: str | None) -> dict:
    """Thin shim around the project's existing LLM dispatcher."""
    from backend.services.topics_service import _call_llm as _ts_call_llm
    return await _ts_call_llm(prompt, llm, model=model)


def _build_verify_new_prompt(
    candidate: dict, project_topics: list[dict], transcripts: dict[str, str]
) -> str:
    transcripts_block = "\n\n".join(
        f"--- CALL {cid} ---\n{body}" for cid, body in transcripts.items()
    )
    project_topics_block = json.dumps(
        [{"topic_id": t.get("topic_id"), "name": t.get("name"), "key_terms": t.get("key_terms", [])}
         for t in project_topics],
        indent=2,
    )
    candidate_block = json.dumps({
        "name": candidate.get("name"),
        "key_terms": candidate.get("key_terms", []),
        "tasks": candidate.get("tasks", []),
        "open_questions": candidate.get("open_questions", []),
        "decisions": candidate.get("decisions", []),
    }, indent=2)
    return (
        f"{VERIFY_NEW_TOPIC_PROMPT}\n\n"
        f"CANDIDATE NEW TOPIC:\n{candidate_block}\n\n"
        f"EXISTING PROJECT TOPICS (anchor only, names + key_terms):\n{project_topics_block}\n\n"
        f"TRANSCRIPTS:\n{transcripts_block}"
    )


async def run_verify_new(
    candidate: dict,
    project_topics: list[dict],
    transcripts: dict[str, str],
    *,
    llm: str,
    model: str | None,
) -> dict:
    """Run Pass ① for one candidate new topic. Returns the LLM verdict + grounding +
    needs_manual_review flag if citation verification failed twice.

    Args:
        candidate: the call_topics-stage extraction dict (name, key_terms, tasks, OQ, decs).
        project_topics: list of {topic_id, name, key_terms} dicts (anchors only).
        transcripts: {call_id: transcript_body} for ALL calls 1..N.
        llm, model: passthrough to _call_llm.
    """
    prompt = _build_verify_new_prompt(candidate, project_topics, transcripts)

    for attempt in (1, 2):
        result = await _call_llm(prompt, llm, model=model)
        if not isinstance(result, dict):
            logger.warning("⚠️ [verify_new] LLM returned non-dict on attempt %d", attempt)
            continue
        cits = result.get("citations") or []
        # Backfill missing line ranges using find_quote_lines
        for c in cits:
            if not c.get("lines"):
                body = transcripts.get(c.get("call_id"), "")
                computed = find_quote_lines(c.get("quote", ""), body)
                if computed:
                    c["lines"] = computed
        ok, failures = verify_citations(cits, transcripts)
        if ok:
            return {**result, "needs_manual_review": False}
        logger.warning("⚠️ [verify_new] citation verify failed on attempt %d: %s", attempt, failures)
        # Retry with explicit failure feedback
        prompt = (
            f"{prompt}\n\nPREVIOUS ATTEMPT FAILED citation verification with these errors:\n"
            f"{json.dumps(failures, indent=2)}\nRedo with verbatim quotes copy-pasted from transcripts."
        )

    return {
        **result,
        "needs_manual_review": True,
        "failed_citations": failures,
    }
```

- [ ] **Step 4: Run tests — expect pass**

Run: `python3 -m pytest backend/tests/test_topic_verification.py -v`
Expected: 2 passed.

- [ ] **Step 5: Add the endpoint to `backend/routers/topics.py`**

At the bottom of `backend/routers/topics.py`:

```python
# --------------------------------------------------------------------------- #
# EPIC-16 — Pass ① /verify-new
# --------------------------------------------------------------------------- #


from backend.services.topic_verification import run_verify_new as _run_verify_new


async def _run_verify_new_background(call_id: str) -> None:
    """Run Pass ① for every new topic in this call's pending_topics, persist to verify_new_cache."""
    import asyncio
    from backend.services.topics_service import _resolve_workflow_llm_for_category
    db = get_client()
    try:
        call_row = db.table("calls").select("project_id, pending_topics").eq("id", call_id).execute().data
        if not call_row:
            return
        project_id = call_row[0]["project_id"]
        pending = call_row[0].get("pending_topics") or []

        # Determine which pending topics are "new" (i.e. NOT in any match group)
        groups = db.table("topic_match_groups").select("call_topic_names").eq("call_id", call_id).execute().data
        matched_names = {n.lower().strip() for g in groups for n in (g.get("call_topic_names") or [])}
        new_candidates = [t for t in pending if t["name"].lower().strip() not in matched_names]

        # Load all transcripts in this project (chronological)
        calls = (
            db.table("calls")
            .select("id, transcript")
            .eq("project_id", project_id)
            .order("created_at")
            .execute()
            .data
        )
        transcripts = {c["id"]: (c.get("transcript") or "") for c in calls if c.get("transcript")}

        # Load existing project topics (anchors only)
        project_topics_rows = (
            db.table("topics")
            .select("id, name, key_terms")
            .eq("project_id", project_id)
            .eq("archived", False)
            .execute()
            .data
        )
        project_topics = [{"topic_id": t["id"], "name": t["name"], "key_terms": []} for t in project_topics_rows]

        llm, model = _resolve_workflow_llm_for_category(project_id, "verify_new_topic", db)

        results = await asyncio.gather(*[
            _run_verify_new(c, project_topics, transcripts, llm=llm, model=model)
            for c in new_candidates
        ])
        cache = {c["name"]: r for c, r in zip(new_candidates, results)}

        db.table("calls").update(
            {"verify_new_cache": cache, "verify_new_status": "done"}
        ).eq("id", call_id).execute()
        logger.info(f"✅ [verify_new] done for call {call_id} ({len(results)} candidates)")
    except Exception as e:
        logger.exception(f"❌ [verify_new] failed for call {call_id}: {e}")
        db.table("calls").update({"verify_new_status": "failed"}).eq("id", call_id).execute()


@router.post("/calls/{call_id}/topics/verify-new")
async def verify_new(call_id: str, background_tasks: BackgroundTasks):
    """Trigger Pass ① in background."""
    logger.info(f"📥 [verify_new] requested for call {call_id}")
    db = get_client()
    db.table("calls").update({"verify_new_status": "processing", "verify_new_cache": None}).eq("id", call_id).execute()
    background_tasks.add_task(_run_verify_new_background, call_id)
    return {"status": "processing"}
```

- [ ] **Step 6: Add `_resolve_workflow_llm_for_category` helper to topics_service.py**

In `backend/services/topics_service.py`, add this helper near `_get_topics_prompt`:

```python
def _resolve_workflow_llm_for_category(
    project_id: str, category: str, db
) -> tuple[str, str | None]:
    """Resolve (llm, model) for a workflow category via the existing chain:
    artifact_types per-project → projects.default_llm → system_settings → 'openrouter' fallback."""
    rows = (
        db.table("artifact_types")
        .select("llm, model")
        .eq("project_id", project_id)
        .eq("category", category)
        .limit(1)
        .execute()
        .data
    )
    llm = rows[0].get("llm") if rows else None
    model = rows[0].get("model") if rows else None
    if not llm:
        proj = db.table("projects").select("default_llm, default_model").eq("id", project_id).execute().data
        if proj:
            llm = proj[0].get("default_llm")
            model = model or proj[0].get("default_model")
    if not llm:
        try:
            settings = db.table("system_settings").select("default_llm, default_model").eq("id", 1).execute().data
            if settings:
                llm = settings[0].get("default_llm") or "openrouter"
                model = model or settings[0].get("default_model")
        except Exception:
            llm = "openrouter"
    return llm or "openrouter", model
```

- [ ] **Step 7: Smoke test the endpoint via unit test on a mocked DB**

Add to `backend/tests/test_topic_verification.py`:

```python
def test_resolve_workflow_llm_uses_artifact_types_first():
    """Verify resolution order: artifact_types → projects → system_settings."""
    from backend.services.topics_service import _resolve_workflow_llm_for_category

    class _FakeDB:
        def table(self, name):
            self._t = name
            return self
        def select(self, *_): return self
        def eq(self, *_): return self
        def limit(self, _): return self
        def execute(self):
            class _R: pass
            r = _R()
            if self._t == "artifact_types":
                r.data = [{"llm": "claude", "model": "claude-sonnet-4-6"}]
            else:
                r.data = []
            return r

    llm, model = _resolve_workflow_llm_for_category("proj-1", "verify_new_topic", _FakeDB())
    assert llm == "claude"
    assert model == "claude-sonnet-4-6"
```

Run: `python3 -m pytest backend/tests/test_topic_verification.py -v`
Expected: 3 passed.

- [ ] **Step 8: Commit**

```bash
python3 scripts/git_ops.py commit \
  --files backend/services/topic_verification.py backend/services/topics_service.py backend/routers/topics.py backend/tests/test_topic_verification.py \
  --message "[EPIC-16] feat: Pass ① verify-new endpoint + RAG orchestration with retry-on-citation-fail"
```

---

### Task 6 — Topic verification service: `run_verify_not_discussed` (Pass ②)

**Files:**
- Modify: `backend/services/topic_verification.py` (add new function + prompt builder)
- Modify: `backend/routers/topics.py` (add endpoint)
- Modify: `backend/tests/test_topic_verification.py` (add tests)

- [ ] **Step 1: Write failing tests for Pass ②**

Add to `backend/tests/test_topic_verification.py`:

```python
def test_run_verify_not_discussed_not_found(monkeypatch):
    """Happy path: topic not mentioned, citation=null."""
    transcript = "We only discussed migration timeline today."
    llm_result = {"verdict": "not_discussed", "citation": None}
    monkeypatch.setattr(tv, "_call_llm", _llm_returns(llm_result))
    out = asyncio.run(tv.run_verify_not_discussed(
        {"name": "Performance testing", "key_terms": ["perf"]},
        transcript, call_id="call-3", llm="claude", model=None
    ))
    assert out["verdict"] == "not_discussed"
    assert out["citation"] is None
    assert out["needs_manual_review"] is False


def test_run_verify_not_discussed_found(monkeypatch):
    transcript = "Hassan said the perf test passed."
    llm_result = {"verdict": "actually_discussed",
                  "citation": {"call_id": "call-3", "lines": "1-1", "quote": "the perf test passed"}}
    monkeypatch.setattr(tv, "_call_llm", _llm_returns(llm_result))
    out = asyncio.run(tv.run_verify_not_discussed(
        {"name": "Performance testing", "key_terms": ["perf"]},
        transcript, call_id="call-3", llm="claude", model=None
    ))
    assert out["verdict"] == "actually_discussed"
    assert out["citation"]["quote"] == "the perf test passed"
    assert out["needs_manual_review"] is False
```

- [ ] **Step 2: Run tests — expect fail**

Run: `python3 -m pytest backend/tests/test_topic_verification.py::test_run_verify_not_discussed_not_found -v`
Expected: FAIL.

- [ ] **Step 3: Add function to `backend/services/topic_verification.py`**

Append:
```python
from backend.prompts.verify_not_discussed import VERIFY_NOT_DISCUSSED_PROMPT


def _build_verify_not_discussed_prompt(topic: dict, transcript: str, call_id: str) -> str:
    anchor = json.dumps({"name": topic.get("name"), "key_terms": topic.get("key_terms", [])}, indent=2)
    return (
        f"{VERIFY_NOT_DISCUSSED_PROMPT}\n\n"
        f"TOPIC ANCHOR:\n{anchor}\n\n"
        f"TRANSCRIPT (call_id={call_id}):\n{transcript}"
    )


async def run_verify_not_discussed(
    topic: dict, transcript: str, *, call_id: str, llm: str, model: str | None
) -> dict:
    """Pass ② — verify a topic wasn't discussed in the supplied transcript."""
    prompt = _build_verify_not_discussed_prompt(topic, transcript, call_id)

    for attempt in (1, 2):
        result = await _call_llm(prompt, llm, model=model)
        if not isinstance(result, dict):
            continue
        citation = result.get("citation")
        cits = [citation] if citation else []
        # Backfill lines
        for c in cits:
            if not c.get("lines"):
                computed = find_quote_lines(c.get("quote", ""), transcript)
                if computed:
                    c["lines"] = computed
        ok, failures = verify_citations(cits, {call_id: transcript})
        if ok:
            return {**result, "needs_manual_review": False}
        prompt = (
            f"{prompt}\n\nPREVIOUS ATTEMPT FAILED citation verification:\n"
            f"{json.dumps(failures, indent=2)}\nRedo with a verbatim quote."
        )

    return {**result, "needs_manual_review": True, "failed_citations": failures}
```

- [ ] **Step 4: Run tests — expect pass**

Run: `python3 -m pytest backend/tests/test_topic_verification.py -v`
Expected: 5 passed.

- [ ] **Step 5: Add endpoint to `backend/routers/topics.py`**

```python
# --------------------------------------------------------------------------- #
# EPIC-16 — Pass ② /verify-not-discussed (lean — replaces old version)
# --------------------------------------------------------------------------- #


from backend.services.topic_verification import run_verify_not_discussed as _run_verify_not_discussed


async def _run_verify_not_discussed_background(call_id: str) -> None:
    """Pass ② for every old topic not in any match group."""
    import asyncio
    from backend.services.topics_service import _resolve_workflow_llm_for_category, _get_previous_topics
    db = get_client()
    try:
        call_row = db.table("calls").select("project_id, transcript").eq("id", call_id).execute().data
        if not call_row:
            return
        project_id = call_row[0]["project_id"]
        transcript = call_row[0].get("transcript") or ""

        groups = db.table("topic_match_groups").select("project_topic_ids").eq("call_id", call_id).execute().data
        matched_ids = {pid for g in groups for pid in (g.get("project_topic_ids") or [])}

        previous = _get_previous_topics(project_id, db)
        not_discussed_candidates = [t for t in previous if t["topic_id"] not in matched_ids]

        llm, model = _resolve_workflow_llm_for_category(project_id, "verify_not_discussed", db)

        results = await asyncio.gather(*[
            _run_verify_not_discussed(
                {"name": t["name"], "key_terms": t.get("key_terms", [])},
                transcript, call_id=call_id, llm=llm, model=model,
            )
            for t in not_discussed_candidates
        ])
        cache = {t["topic_id"]: r for t, r in zip(not_discussed_candidates, results)}
        db.table("calls").update(
            {"verify_not_discussed_cache": cache, "verify_not_discussed_status": "done"}
        ).eq("id", call_id).execute()
        logger.info(f"✅ [verify_not_discussed] done for call {call_id} ({len(results)} candidates)")
    except Exception as e:
        logger.exception(f"❌ [verify_not_discussed] failed for call {call_id}: {e}")
        db.table("calls").update({"verify_not_discussed_status": "failed"}).eq("id", call_id).execute()


@router.post("/calls/{call_id}/topics/verify-not-discussed")
async def verify_not_discussed(call_id: str, background_tasks: BackgroundTasks):
    logger.info(f"📥 [verify_not_discussed] requested for call {call_id}")
    db = get_client()
    db.table("calls").update(
        {"verify_not_discussed_status": "processing", "verify_not_discussed_cache": None}
    ).eq("id", call_id).execute()
    background_tasks.add_task(_run_verify_not_discussed_background, call_id)
    return {"status": "processing"}
```

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit \
  --files backend/services/topic_verification.py backend/routers/topics.py backend/tests/test_topic_verification.py \
  --message "[EPIC-16] feat: Pass ② verify-not-discussed (lean transcript-only check, replaces old blast)"
```

---

### Task 7 — Topic verification service: `run_extract_topic_updates` (Pass ③)

**Files:**
- Modify: `backend/services/topic_verification.py` (add Pass ③)
- Modify: `backend/routers/topics.py` (add endpoint)
- Modify: `backend/tests/test_topic_verification.py` (add tests)

- [ ] **Step 1: Write failing test for Pass ③**

Add to `backend/tests/test_topic_verification.py`:

```python
def test_run_extract_topic_updates_returns_snapshot_and_trail(monkeypatch):
    """Pass ③ returns extracted_snapshot + evidence_trail with citations."""
    transcripts = {
        "call-1": "Hassan mentioned MC Mac issue first.",
        "call-2": "Test the boost flag next.",
    }
    topic_anchor = {"name": "MC Mac memory issue", "key_terms": ["MC Mac"]}
    llm_result = {
        "extracted_snapshot": {
            "summary": "MC Mac memory issue under investigation.",
            "status": "in_progress",
            "tasks": [
                {"task_id": None, "task": "Test boost flag", "next_step": "",
                 "owner": "", "status": "open",
                 "primary_citation": {"call_id": "call-2", "lines": "1-1", "quote": "Test the boost flag next"},
                 "supporting_citations": []}
            ],
            "open_questions": [],
            "decisions": [],
        },
        "evidence_trail": [
            {"call_id": "call-1", "citation": {"call_id": "call-1", "lines": "1-1", "quote": "MC Mac issue first"},
             "action_label": "first raised"},
            {"call_id": "call-2", "citation": {"call_id": "call-2", "lines": "1-1", "quote": "Test the boost flag next"},
             "action_label": "task added"},
        ],
    }
    monkeypatch.setattr(tv, "_call_llm", _llm_returns(llm_result))

    out = asyncio.run(tv.run_extract_topic_updates(topic_anchor, transcripts, llm="claude", model=None))
    assert out["needs_manual_review"] is False
    assert len(out["extracted_snapshot"]["tasks"]) == 1
    assert len(out["evidence_trail"]) == 2
```

- [ ] **Step 2: Run test — expect fail**

Run: `python3 -m pytest backend/tests/test_topic_verification.py::test_run_extract_topic_updates_returns_snapshot_and_trail -v`
Expected: FAIL.

- [ ] **Step 3: Add function to `backend/services/topic_verification.py`**

```python
from backend.prompts.extract_topic_updates import EXTRACT_TOPIC_UPDATES_PROMPT


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
    out: list[dict] = []
    for task in snapshot.get("tasks", []):
        if task.get("primary_citation"):
            out.append(task["primary_citation"])
        for c in task.get("supporting_citations", []) or []:
            out.append(c)
    for oq in snapshot.get("open_questions", []):
        if oq.get("primary_citation"):
            out.append(oq["primary_citation"])
    for d in snapshot.get("decisions", []):
        if d.get("primary_citation"):
            out.append(d["primary_citation"])
        for c in d.get("supporting_citations", []) or []:
            out.append(c)
    for e in trail:
        if e.get("citation"):
            out.append(e["citation"])
    return out


async def run_extract_topic_updates(
    topic_anchor: dict, transcripts: dict[str, str], *, llm: str, model: str | None
) -> dict:
    """Pass ③ — full re-extraction of a topic from raw transcripts."""
    prompt = _build_extract_updates_prompt(topic_anchor, transcripts)

    for attempt in (1, 2):
        result = await _call_llm(prompt, llm, model=model)
        if not isinstance(result, dict):
            continue
        snapshot = result.get("extracted_snapshot") or {}
        trail = result.get("evidence_trail") or []
        all_cits = _collect_citations(snapshot, trail)
        # Backfill missing lines
        for c in all_cits:
            if not c.get("lines"):
                body = transcripts.get(c.get("call_id"), "")
                computed = find_quote_lines(c.get("quote", ""), body)
                if computed:
                    c["lines"] = computed
        ok, failures = verify_citations(all_cits, transcripts)
        if ok:
            return {**result, "needs_manual_review": False}
        prompt = (
            f"{prompt}\n\nPREVIOUS ATTEMPT FAILED citation verification:\n"
            f"{json.dumps(failures, indent=2)}\nRedo with verbatim quotes."
        )

    return {**result, "needs_manual_review": True, "failed_citations": failures}
```

- [ ] **Step 4: Run tests — expect pass**

Run: `python3 -m pytest backend/tests/test_topic_verification.py -v`
Expected: 6 passed.

- [ ] **Step 5: Add endpoint to `backend/routers/topics.py`**

```python
# --------------------------------------------------------------------------- #
# EPIC-16 — Pass ③ /extract-updates
# --------------------------------------------------------------------------- #


from backend.services.topic_verification import run_extract_topic_updates as _run_extract


async def _run_extract_updates_background(call_id: str) -> None:
    """Pass ③ — full re-extraction for every merged topic (incl. ones migrated by Pass ① + ②)."""
    import asyncio
    from backend.services.topics_service import _resolve_workflow_llm_for_category
    db = get_client()
    try:
        call_row = db.table("calls").select(
            "project_id, verify_new_cache, verify_not_discussed_cache"
        ).eq("id", call_id).execute().data
        if not call_row:
            return
        project_id = call_row[0]["project_id"]

        # Collect merged topic anchors:
        # 1. project topics in match_groups
        groups = db.table("topic_match_groups").select("project_topic_ids").eq("call_id", call_id).execute().data
        matched_ids = list({pid for g in groups for pid in (g.get("project_topic_ids") or [])})
        # 2. project topics moved by Pass ② (verdict=actually_discussed)
        nd_cache = call_row[0].get("verify_not_discussed_cache") or {}
        moved_from_nd = [tid for tid, r in nd_cache.items() if r.get("verdict") == "actually_discussed"]
        matched_ids = list(set(matched_ids + moved_from_nd))
        # 3. new topics moved by Pass ① (verdict=should_be_merged_with) → resolve to existing topic
        vn_cache = call_row[0].get("verify_new_cache") or {}
        moved_from_new = [r.get("matched_topic_id") for r in vn_cache.values() if r.get("verdict") == "should_be_merged_with" and r.get("matched_topic_id")]
        matched_ids = list(set(matched_ids + moved_from_new))

        anchors = (
            db.table("topics")
            .select("id, name, key_terms")
            .in_("id", matched_ids)
            .execute()
            .data
        ) if matched_ids else []

        # Load all transcripts in this project
        calls = (
            db.table("calls").select("id, transcript")
            .eq("project_id", project_id).order("created_at").execute().data
        )
        transcripts = {c["id"]: (c.get("transcript") or "") for c in calls if c.get("transcript")}

        llm, model = _resolve_workflow_llm_for_category(project_id, "extract_topic_updates", db)

        results = await asyncio.gather(*[
            _run_extract(
                {"name": t["name"], "key_terms": t.get("key_terms") or []},
                transcripts, llm=llm, model=model,
            )
            for t in anchors
        ])
        cache = {t["id"]: r for t, r in zip(anchors, results)}
        db.table("calls").update(
            {"extract_updates_cache": cache, "extract_updates_status": "done"}
        ).eq("id", call_id).execute()
        logger.info(f"✅ [extract_updates] done for call {call_id} ({len(results)} topics)")
    except Exception as e:
        logger.exception(f"❌ [extract_updates] failed for call {call_id}: {e}")
        db.table("calls").update({"extract_updates_status": "failed"}).eq("id", call_id).execute()


@router.post("/calls/{call_id}/topics/extract-updates")
async def extract_updates(call_id: str, background_tasks: BackgroundTasks):
    logger.info(f"📥 [extract_updates] requested for call {call_id}")
    db = get_client()
    db.table("calls").update(
        {"extract_updates_status": "processing", "extract_updates_cache": None}
    ).eq("id", call_id).execute()
    background_tasks.add_task(_run_extract_updates_background, call_id)
    return {"status": "processing"}
```

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit \
  --files backend/services/topic_verification.py backend/routers/topics.py backend/tests/test_topic_verification.py \
  --message "[EPIC-16] feat: Pass ③ extract-updates — full re-extraction of merged topics from raw transcripts with chronological evidence_trail"
```

---

### Task 8 — Cleanup: remove old auto-trigger flow + update persistence

**Files:**
- Modify: `backend/routers/topics.py`
- Modify: `backend/services/topics_service.py`

- [ ] **Step 1: Find `save_match_groups` in `backend/services/topics_service.py` and remove the BackgroundTask trigger**

Locate the function. Remove these lines:
```python
db.table("calls").update({"verification_status": "processing", "verification_cache": None}).eq("id", call_id).execute()
background_tasks.add_task(run_verification_background, call_id)
```

`save_match_groups` should now only:
1. Delete prior match_groups for this call (idempotent)
2. Insert new match_groups
3. Update kanban_stage='project_updates'

- [ ] **Step 2: Locate `save_matches` router handler in `topics.py` and drop the `BackgroundTasks` parameter passthrough**

Old:
```python
async def save_matches(call_id: str, groups: list[MatchGroupPayload], background_tasks: BackgroundTasks):
    ...
    background_tasks.add_task(run_verification_background, call_id)
```

New (signature change — drop `background_tasks` arg + body):
```python
async def save_matches(call_id: str, groups: list[MatchGroupPayload]):
    logger.info(f"📥 [Topics] Save matches: call={call_id}, groups={len(groups)}")
    try:
        result = await save_match_groups(call_id, [g.model_dump() for g in groups])
        logger.info(f"✅ [Topics] Saved match groups; project_updates stage advanced")
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception(f"❌ [Topics] Save matches failed: {e}")
        raise HTTPException(status_code=500, detail="Save matches failed")
```

- [ ] **Step 3: Delete `run_merge_preview`, `_verify_merged_topics`, `verify_not_discussed_topics`, `run_verification_background` from `topics_service.py`**

These are no longer called. Delete the function bodies + any imports that become dead.

Also delete from `backend/routers/topics.py`:
- The `merge-preview` endpoint
- Any import of the deleted functions

- [ ] **Step 4: Update `validate_project_updates` to consume `extract_updates_cache`**

Locate in `topics_service.py`. The function currently receives a `topics` list from the frontend. Replace the input-processing block so that when a topic has an entry in `calls.extract_updates_cache`, the cache's `extracted_snapshot` is used as the source of truth for tasks/OQ/decisions/summary/status, and `citations` + `evidence_trail` get attached.

Insert at the top of the function, right after fetching `call_row`:
```python
cache_row = db.table("calls").select("extract_updates_cache").eq("id", call_id).execute().data
extract_cache: dict = (cache_row[0].get("extract_updates_cache") or {}) if cache_row else {}
```

When building `model_data` for each topic (existing loop), if `t.get("topic_id")` matches a key in `extract_cache`, override the snapshot fields from the cache. The frontend-edited values still win if the user manually edited; but the citations + evidence_trail always come from the cache.

```python
# Inside the loop "for t in topics_to_save:"
extract_result = extract_cache.get(t.get("topic_id")) or {}
extracted = extract_result.get("extracted_snapshot") or {}
if extracted:
    # Default-fill missing keys from extracted snapshot (frontend edits win)
    for key in ("summary", "status", "tasks", "open_questions", "decisions"):
        if not t.get(key):
            t[key] = extracted.get(key)
    t["citations"] = extract_result.get("citations") or []
    t["evidence_trail"] = extract_result.get("evidence_trail") or []
    t["needs_manual_review"] = extract_result.get("needs_manual_review", False)
```

- [ ] **Step 5: Update `save_topics` + `_persist_topic_update` to persist citations + evidence_trail**

In `_persist_topic_update` (`backend/services/topics_service.py:325-363`), extend payload:
```python
payload: dict = {
    "topic_id": topic_id,
    "call_id": call_id,
    "summary": topic.get("summary") or "",
    "importance": topic.get("importance", "medium"),
    "evidence": topic.get("evidence", []),
    "key_terms": topic.get("key_terms", []),
    "tasks": topic.get("tasks", []),
    "open_questions": topic.get("open_questions", []),
    "decisions": topic.get("decisions", []),
    "citations": topic.get("citations") or [],
    "evidence_trail": topic.get("evidence_trail") or [],
    "needs_manual_review": bool(topic.get("needs_manual_review")),
    "status": _status_rollup(topic.get("tasks", [])),
}
```

In `save_topics` (`backend/services/topics_service.py:1681`), extend `topic_dict`:
```python
topic_dict = {
    "name": t.name,
    "importance": t.importance,
    "evidence": t.evidence,
    "key_terms": t.key_terms,
    "tasks": t.tasks,
    "open_questions": t.open_questions,
    "decisions": t.decisions,
    "citations": getattr(t, "citations", None) or [],
    "evidence_trail": getattr(t, "evidence_trail", None) or [],
    "needs_manual_review": bool(getattr(t, "needs_manual_review", False)),
    "summary": t.summary,
    "transcript_excerpt": t.transcript_excerpt,
}
```

Extend the `TopicIn` / `TopicUpdate` Pydantic model (`backend/services/topics_service.py:80-130` area) to accept these fields:
```python
class TopicIn(BaseModel):
    ...  # keep existing
    citations: list = []
    evidence_trail: list = []
    needs_manual_review: bool = False
```

- [ ] **Step 6: Update rollback paths to clear the new caches**

In `rollback_to_stage` (`backend/services/topics_service.py:1907`), find each rollback target and clear the appropriate new fields:

Add to `_clear_extraction_fields()` body the new EPIC-16 cache fields when rolling back to `call_topics`:
```python
def _clear_rag_pass_fields() -> None:
    """Clear the 3 EPIC-16 pass caches/statuses."""
    payload = json.dumps({
        "verify_new_cache": None, "verify_new_status": "idle",
        "verify_not_discussed_cache": None, "verify_not_discussed_status": "idle",
        "extract_updates_cache": None, "extract_updates_status": "idle",
    })
    db.postgrest.session.patch(
        f"/calls?id=eq.{call_id}",
        content=payload,
        headers={"Content-Type": "application/json", "Prefer": "return=representation"},
    )
```

Call `_clear_rag_pass_fields()` from each of the `project_matching` / `call_topics` / `transcript` rollback branches (i.e. whenever we roll back past `project_updates`).

- [ ] **Step 7: Run full backend test suite**

Run: `python3 -m pytest backend/tests/`
Expected: all tests pass except known pre-existing failures (e.g. `test_library_seed::test_v2_call_topics_entry_exists_and_is_default` which is now superseded by EPIC-16 changes; update it if it breaks).

- [ ] **Step 8: Commit**

```bash
python3 scripts/git_ops.py commit \
  --files backend/services/topics_service.py backend/routers/topics.py \
  --message "[EPIC-16] refactor: remove auto-merge + auto-not-discussed flow; persist citations + evidence_trail in topic_updates"
```

---

## Phase 3 — Frontend

### Task 9 — Types + API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add new types to `frontend/src/types/index.ts`**

Append at the end of the file:
```ts
// ── EPIC-16 RAG verification types ──────────────────────────────────────────

export interface Citation {
  call_id: string;
  lines: string;       // e.g. "145-148"
  quote: string;       // verbatim
  for?: string;        // optional tag: "verdict" | "extraction" | etc
}

export interface EvidenceTrailEntry {
  call_id: string;
  citation: Citation;
  action_label: string;  // "first raised" | "task added" | ...
}

export type VerifyNewVerdict = "truly_new" | "should_be_merged_with";

export interface VerifyNewResult {
  verdict: VerifyNewVerdict;
  matched_topic_id: string | null;
  matched_topic_name: string | null;
  extraction_grounded: boolean;
  ungrounded_items: { type: "task" | "open_question" | "decision"; text: string }[];
  citations: Citation[];
  needs_manual_review: boolean;
  failed_citations?: string[];
}

export type VerifyNotDiscussedVerdict = "not_discussed" | "actually_discussed";

export interface VerifyNotDiscussedResult {
  verdict: VerifyNotDiscussedVerdict;
  citation: Citation | null;
  needs_manual_review: boolean;
  failed_citations?: string[];
}

export interface ExtractedTaskItem {
  task_id: string | null;
  task: string;
  next_step: string;
  owner: string;
  status: "open" | "in_progress" | "resolved";
  primary_citation: Citation;
  supporting_citations: Citation[];
}

export interface ExtractedOQ {
  id: string | null;
  text: string;
  owner: string;
  status: "open" | "in_progress" | "resolved";
  primary_citation: Citation;
}

export interface ExtractedDecision {
  id: string | null;
  text: string;
  primary_citation: Citation;
  supporting_citations: Citation[];
}

export interface ExtractedSnapshot {
  summary: string;
  status: "open" | "in_progress" | "resolved";
  tasks: ExtractedTaskItem[];
  open_questions: ExtractedOQ[];
  decisions: ExtractedDecision[];
}

export interface ExtractedUpdateResult {
  extracted_snapshot: ExtractedSnapshot;
  evidence_trail: EvidenceTrailEntry[];
  needs_manual_review: boolean;
  failed_citations?: string[];
}

export type RagPassStatus = "idle" | "processing" | "done" | "failed";
```

Add to the `Call` interface:
```ts
verify_new_status?: RagPassStatus;
verify_new_cache?: Record<string, VerifyNewResult> | null;          // keyed by topic name
verify_not_discussed_status?: RagPassStatus;
verify_not_discussed_cache?: Record<string, VerifyNotDiscussedResult> | null;  // keyed by topic_id
extract_updates_status?: RagPassStatus;
extract_updates_cache?: Record<string, ExtractedUpdateResult> | null;  // keyed by topic_id
```

Add to `TopicData`:
```ts
citations?: Citation[];
evidence_trail?: EvidenceTrailEntry[];
needs_manual_review?: boolean;
```

- [ ] **Step 2: Add API methods + remove old ones in `frontend/src/api/client.ts`**

Locate `topicsAPI` block. Remove the `mergePreview` method. Add:
```ts
verifyNew: (callId: string) =>
  proxyFetch<{ status: string }>(`/api/calls/${callId}/topics/verify-new`, { method: "POST" }),

verifyNotDiscussed: (callId: string) =>
  proxyFetch<{ status: string }>(`/api/calls/${callId}/topics/verify-not-discussed`, { method: "POST" }),

extractUpdates: (callId: string) =>
  proxyFetch<{ status: string }>(`/api/calls/${callId}/topics/extract-updates`, { method: "POST" }),
```

- [ ] **Step 3: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit \
  --files frontend/src/types/index.ts frontend/src/api/client.ts \
  --message "[EPIC-16] feat(fe): add Citation/EvidenceTrail types + 3 RAG verification API methods"
```

---

### Task 10 — `EvidenceTrail` + `TopicCitationBadge` components

**Files:**
- Create: `frontend/src/components/EvidenceTrail.tsx`
- Create: `frontend/src/components/TopicCitationBadge.tsx`

- [ ] **Step 1: Build `EvidenceTrail.tsx`** — renders chronological list of citations grouped by call

```tsx
"use client";

import type { EvidenceTrailEntry, Call } from "@/types";

type Props = {
  entries: EvidenceTrailEntry[];
  callsById: Record<string, Pick<Call, "id" | "title" | "created_at">>;
};

export default function EvidenceTrail({ entries, callsById }: Props) {
  if (!entries || entries.length === 0) return null;

  // Group by call_id, ordered by call.created_at (chronological)
  const sortedCalls = Object.values(callsById).sort(
    (a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? "")
  );

  return (
    <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid #dfe1e6" }}>
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: ".05em",
          color: "#5e6c84",
          marginBottom: 8,
        }}
      >
        Evidence trail (chronological)
      </div>
      {sortedCalls.map((call) => {
        const callEntries = entries.filter((e) => e.call_id === call.id);
        if (callEntries.length === 0) return null;
        return (
          <div key={call.id} style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#172b4d" }}>
              {call.title ?? "Untitled"} · {(call.created_at ?? "").slice(0, 10)}
            </div>
            {callEntries.map((e, i) => (
              <div
                key={`${call.id}-${i}`}
                id={`cit-${call.id}-${i}`}
                style={{
                  marginLeft: 12,
                  marginTop: 4,
                  fontSize: 12,
                  color: "#42526e",
                }}
              >
                <span style={{ color: "#7a869a", fontSize: 10 }}>
                  lines {e.citation.lines}
                </span>
                <div
                  style={{
                    fontStyle: "italic",
                    background: "#fafbfc",
                    padding: "4px 8px",
                    borderLeft: "2px solid #c1c7d0",
                    marginTop: 2,
                  }}
                >
                  &quot;{e.citation.quote}&quot;
                </div>
                <div style={{ color: "#0052cc", fontSize: 11, marginTop: 2 }}>
                  ↳ {e.action_label}
                </div>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Build `TopicCitationBadge.tsx`** — clickable tag that scrolls to its trail entry

```tsx
"use client";

type Props = {
  callId: string;
  callShortName: string;   // e.g. "Call 1"
  citationIndex: number;
};

export default function TopicCitationBadge({ callId, callShortName, citationIndex }: Props) {
  const onClick = () => {
    const el = document.getElementById(`cit-${callId}-${citationIndex}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        fontSize: 10,
        fontWeight: 600,
        padding: "1px 6px",
        borderRadius: 3,
        background: "#deebff",
        color: "#0052cc",
        border: "1px solid #b3d4ff",
        cursor: "pointer",
        fontFamily: "inherit",
      }}
      title="Scroll to citation"
    >
      → {callShortName} cit-{citationIndex}
    </button>
  );
}
```

- [ ] **Step 3: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit \
  --files frontend/src/components/EvidenceTrail.tsx frontend/src/components/TopicCitationBadge.tsx \
  --message "[EPIC-16] feat(fe): EvidenceTrail + TopicCitationBadge components for citation rendering"
```

---

### Task 11 — Visual mockup approval BEFORE rewriting ProjectUpdatesStage

Per project CLAUDE.md: UI mockup approval is required before frontend code for a new layout. The 3-section sequenced-button layout is already approved in the design doc (section 4.2). This task is a checkpoint:

- [ ] **Step 1: Re-read design doc section 4.2 (3-section layout) and 5.x (per-pass UI effects)**

Open: `docs/project/config/2026-05-20-project-updates-rag-rework-design.md`

- [ ] **Step 2: Confirm with user that the layout is still approved**

Ask in plain text: "Layout 4.2 + per-pass UI effects from 5.x — still approved as the basis for ProjectUpdatesStage rewrite? Any last-minute adjustments before I touch the code?"

If user requests changes → pause and update the design doc, re-confirm, then proceed.

- [ ] **Step 3: No commit (gate task only)**

---

### Task 12 — Rewrite `ProjectUpdatesStage.tsx` (3-section layout)

**Files:**
- Rewrite: `frontend/src/components/ProjectUpdatesStage.tsx`

This is a large rewrite. Break the work into 3 sub-steps: scaffolding, sections rendering, pass triggering + polling.

- [ ] **Step 1: Strip the file to scaffolding + remove auto merge-preview trigger**

Open `frontend/src/components/ProjectUpdatesStage.tsx`. Remove:
- Any call to `topicsAPI.mergePreview` (deleted from client.ts)
- Any polling on `merge_status` / `merge_cache`
- The existing merged-topics review UI body

Replace the component body with the new 3-section scaffold:

```tsx
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { callsAPI, topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type {
  Call,
  TopicData,
  MatchGroup,
  RagPassStatus,
  VerifyNewResult,
  VerifyNotDiscussedResult,
  ExtractedUpdateResult,
} from "@/types";

type Props = {
  call: Call;
  projectId: string;
  onValidateComplete: () => void;
};

export default function ProjectUpdatesStage({ call, projectId, onValidateComplete }: Props) {
  const [projectTopics, setProjectTopics] = useState<TopicData[]>([]);
  const [pending, setPending] = useState<TopicData[]>([]);
  const [groups, setGroups] = useState<MatchGroup[]>([]);
  const [busy, setBusy] = useState<null | "①" | "②" | "③">(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load match groups + pending + project topics on mount
  useEffect(() => {
    Promise.all([
      topicsAPI.getMatchGroups(call.id),
      topicsAPI.getPending(call.id),
      topicsAPI.priorToCall(projectId, call.id),
    ]).then(([g, p, pr]) => {
      setGroups(g.map((x: { project_topic_ids: string[]; call_topic_names: string[] }) => ({
        project_topic_ids: x.project_topic_ids ?? [],
        call_topic_names: x.call_topic_names ?? [],
      })));
      setPending(p);
      setProjectTopics(pr);
    }).catch(() => setError("Failed to load data"));
  }, [call.id, projectId]);

  // Compute the 3 sections from groups + pending + projectTopics
  const sections = useMemo(() => {
    const matchedNames = new Set(groups.flatMap((g) => g.call_topic_names));
    const matchedProjectIds = new Set(groups.flatMap((g) => g.project_topic_ids));

    const newTopics = pending.filter((p) => !matchedNames.has(p.name));
    const notInCall = projectTopics.filter((t) => !matchedProjectIds.has(t.topic_id ?? ""));
    const merged = projectTopics.filter((t) => matchedProjectIds.has(t.topic_id ?? ""));

    return { newTopics, notInCall, merged };
  }, [groups, pending, projectTopics]);

  // Status flags from the call's cache fields
  const stage1Done = call.verify_new_status === "done";
  const stage2Done = call.verify_not_discussed_status === "done";
  const stage3Done = call.extract_updates_status === "done";
  const allDone = stage1Done && stage2Done && stage3Done;

  // TODO Step 2: section rendering
  // TODO Step 3: pass triggers + polling

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <header style={{ padding: "14px 20px", borderBottom: "1px solid #dfe1e6" }}>
        <h2 style={{ margin: 0, fontSize: 15, color: "#172b4d" }}>Project Updates · Call {call.title}</h2>
      </header>
      {error && (
        <div style={{ margin: 16, padding: 12, background: "#fff1f0", color: "#ae2a19", borderRadius: 6 }}>{error}</div>
      )}
      <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
        {/* Sections rendered in Step 2 */}
        Section content TBD next step
      </div>
      <footer style={{ padding: 12, borderTop: "1px solid #dfe1e6", display: "flex", justifyContent: "flex-end" }}>
        <button
          disabled={!allDone || saving}
          onClick={async () => {
            setSaving(true);
            // Compose topics list from caches + raw pending; pass to validate-updates
            // Implementation in Step 3
          }}
          style={{
            padding: "8px 22px", borderRadius: 6, border: "none",
            background: allDone ? "#0052cc" : "#f4f5f7",
            color: allDone ? "white" : "#97a0af", cursor: allDone ? "pointer" : "default",
          }}
        >
          {saving ? "Saving…" : "Save & Continue → Artifacts"}
        </button>
      </footer>
    </div>
  );
}
```

Run typecheck: `cd frontend && npx tsc --noEmit` — Expected: no errors.

- [ ] **Step 2: Implement the 3 sections rendering**

Replace `Section content TBD next step` with three `<Section>` blocks. Each section:
- Has a header with title + count + the button for that pass + a "✓ done" badge if applicable
- Body renders the relevant topic cards
- Section 2 disabled until `stage1Done`; Section 3 disabled until `stage2Done`

Add helper components at the bottom of the file:

```tsx
function SectionHeader({
  title, count, button, done, disabled,
}: {
  title: string; count: number; button: React.ReactNode; done: boolean; disabled: boolean;
}) {
  return (
    <div
      style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "8px 12px", background: disabled ? "#f4f5f7" : "#fafbfc",
        opacity: disabled ? 0.5 : 1, borderRadius: 6, marginBottom: 8,
      }}
    >
      <span style={{ fontSize: 13, fontWeight: 700, color: "#172b4d" }}>
        {title} ({count}) {done && <span style={{ color: "#36b37e", marginLeft: 6 }}>✓ done</span>}
      </span>
      {button}
    </div>
  );
}
```

Add to the body of `ProjectUpdatesStage`:

```tsx
<section style={{ marginBottom: 24 }}>
  <SectionHeader
    title="1. New topics from this call"
    count={sections.newTopics.length}
    button={
      <button
        disabled={busy !== null || sections.newTopics.length === 0}
        onClick={() => triggerPass("①")}
        style={passButton(stage1Done)}
      >
        {busy === "①" ? "Running…" : stage1Done ? "Re-verify ①" : "① Verify new"}
      </button>
    }
    done={stage1Done}
    disabled={false}
  />
  {sections.newTopics.map((t) => (
    <NewTopicCard key={t.name} topic={t} result={(call.verify_new_cache ?? {})[t.name]} />
  ))}
</section>

<section style={{ marginBottom: 24 }}>
  <SectionHeader
    title="2. Old topics not in this call"
    count={sections.notInCall.length}
    button={
      <button
        disabled={!stage1Done || busy !== null || sections.notInCall.length === 0}
        onClick={() => triggerPass("②")}
        style={passButton(stage2Done)}
      >
        {busy === "②" ? "Running…" : stage2Done ? "Re-verify ②" : "② Verify not discussed"}
      </button>
    }
    done={stage2Done}
    disabled={!stage1Done}
  />
  {sections.notInCall.map((t) => (
    <NotInCallCard key={t.topic_id} topic={t} result={(call.verify_not_discussed_cache ?? {})[t.topic_id ?? ""]} />
  ))}
</section>

<section style={{ marginBottom: 24 }}>
  <SectionHeader
    title="3. Merged topics"
    count={sections.merged.length}
    button={
      <button
        disabled={!stage2Done || busy !== null || sections.merged.length === 0}
        onClick={() => triggerPass("③")}
        style={passButton(stage3Done)}
      >
        {busy === "③" ? "Running…" : stage3Done ? "Re-extract ③" : "③ Extract updates"}
      </button>
    }
    done={stage3Done}
    disabled={!stage2Done}
  />
  {sections.merged.map((t) => (
    <MergedTopicCard
      key={t.topic_id}
      projectTopic={t}
      callMatches={pending.filter((p) => groups.find((g) =>
        (g.project_topic_ids ?? []).includes(t.topic_id ?? "") &&
        g.call_topic_names.includes(p.name)
      ))}
      extracted={(call.extract_updates_cache ?? {})[t.topic_id ?? ""]}
    />
  ))}
</section>
```

Define stub card components:

```tsx
function NewTopicCard({ topic, result }: { topic: TopicData; result?: VerifyNewResult }) {
  // body: raw topic data + (if result present) verdict badge + citations
  // implementation in step 3
  return <div style={cardStyle}>{topic.name}{result && <span> · ✓ {result.verdict}</span>}</div>;
}

function NotInCallCard({ topic, result }: { topic: TopicData; result?: VerifyNotDiscussedResult }) {
  return <div style={cardStyle}>{topic.name}{result && <span> · ✓ {result.verdict}</span>}</div>;
}

function MergedTopicCard({ projectTopic, callMatches, extracted }: {
  projectTopic: TopicData;
  callMatches: TopicData[];
  extracted?: ExtractedUpdateResult;
}) {
  // body: side-by-side previous vs this call; extracted snapshot below if present
  // implementation in step 3
  return <div style={cardStyle}>{projectTopic.name} (merged from {callMatches.length} call topics)</div>;
}

const cardStyle: React.CSSProperties = {
  padding: 10, marginBottom: 8, border: "1px solid #dfe1e6", borderRadius: 6, background: "white",
};

const passButton = (done: boolean): React.CSSProperties => ({
  padding: "5px 12px", borderRadius: 4, border: "none", fontFamily: "inherit",
  background: done ? "#36b37e" : "#0052cc", color: "white",
  fontSize: 12, fontWeight: 600,
});
```

Run typecheck: `cd frontend && npx tsc --noEmit` — Expected: no errors.

- [ ] **Step 3: Implement pass triggers + polling + card bodies**

Add inside `ProjectUpdatesStage`:

```tsx
const pollRef = useRef<NodeJS.Timeout | null>(null);

const triggerPass = async (which: "①" | "②" | "③") => {
  setBusy(which);
  setError(null);
  try {
    if (which === "①") await topicsAPI.verifyNew(call.id);
    if (which === "②") await topicsAPI.verifyNotDiscussed(call.id);
    if (which === "③") await topicsAPI.extractUpdates(call.id);
    pollRef.current && clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      const fresh = await callsAPI.getCall(call.id);
      // Bubble up to parent — parent passes updated `call` prop. If the parent
      // doesn't re-fetch, this stage's `call` prop stays stale. The parent
      // page should poll this stage's call between mounts. For now we trigger
      // a router refresh.
      const status = (which === "①") ? fresh.verify_new_status
                   : (which === "②") ? fresh.verify_not_discussed_status
                   : fresh.extract_updates_status;
      if (status === "done" || status === "failed") {
        clearInterval(pollRef.current!);
        pollRef.current = null;
        setBusy(null);
        // Force re-render by reassigning call prop indirectly — parent must re-fetch.
        window.location.reload();  // pragmatic — refresh full page so call data is fresh
      }
    }, 3000);
  } catch (e) {
    setError(e instanceof Error ? e.message : "Failed to trigger pass");
    setBusy(null);
  }
};

useEffect(() => () => { pollRef.current && clearInterval(pollRef.current); }, []);
```

Implement card bodies. Replace the stub `NewTopicCard`:

```tsx
function NewTopicCard({ topic, result }: { topic: TopicData; result?: VerifyNewResult }) {
  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <strong style={{ fontSize: 13, color: "#172b4d" }}>{topic.name}</strong>
        {result && result.verdict === "truly_new" && (
          <span style={badgeGreen}>✓ truly new</span>
        )}
        {result && result.verdict === "should_be_merged_with" && (
          <span style={badgeAmber}>↻ moved to merged → {result.matched_topic_name}</span>
        )}
        {result?.needs_manual_review && (
          <span style={badgeRed}>⚠ needs manual review</span>
        )}
      </div>
      {topic.tasks && topic.tasks.length > 0 && (
        <ul style={{ fontSize: 12, color: "#5e6c84", marginTop: 6 }}>
          {topic.tasks.map((t, i) => (
            <li key={i}>{t.task}{t.next_step && <> → {t.next_step}</>}</li>
          ))}
        </ul>
      )}
      {result && !result.extraction_grounded && result.ungrounded_items.length > 0 && (
        <div style={{ fontSize: 11, color: "#ae2a19", marginTop: 6 }}>
          Ungrounded items flagged: {result.ungrounded_items.map((u) => u.text).join(", ")}
        </div>
      )}
    </div>
  );
}
```

Same level of detail for `NotInCallCard` and `MergedTopicCard`. `MergedTopicCard` includes the side-by-side rendering + the `<EvidenceTrail>` component below when `extracted` is present.

Wire `Save & Continue` to compose the topics array from caches and call `topicsAPI.validateUpdates`. Use the cached `extracted_snapshot` for merged topics, raw `pending_topics` for new topics, omit not-in-call topics from the payload.

- [ ] **Step 4: TypeScript check + lint**

Run: `cd frontend && npx tsc --noEmit && npx eslint src/components/ProjectUpdatesStage.tsx`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit \
  --files frontend/src/components/ProjectUpdatesStage.tsx \
  --message "[EPIC-16] feat(fe): rewrite ProjectUpdatesStage with 3-section sequenced RAG verification flow"
```

---

### Task 13 — Enrich TopicEvidenceDrawer + Timeline badge

**Files:**
- Modify: `frontend/src/components/TopicEvidenceDrawer.tsx`
- Modify: `frontend/src/components/TopicsTimeline.tsx`

- [ ] **Step 1: Drawer enrichment — append `EvidenceTrail` when present**

In `TopicEvidenceDrawer.tsx`, locate the per-call card render section. After the existing fields (tasks, decisions, follow-ups) but before the close of the card, add:

```tsx
{update.evidence_trail && update.evidence_trail.length > 0 && (
  <EvidenceTrail entries={update.evidence_trail} callsById={callsById} />
)}
```

Where `callsById` is built from the existing calls list in the drawer's parent context.

Add import:
```tsx
import EvidenceTrail from "./EvidenceTrail";
```

- [ ] **Step 2: Timeline badge for `needs_manual_review`**

In `TopicsTimeline.tsx`, locate the cell rendering for a call/topic intersection. Where existing badges/icons render, add:

```tsx
{cell.needs_manual_review && (
  <span title="Needs manual review" style={{ color: "#bf2600", marginLeft: 2 }}>⚠️</span>
)}
```

Update the backend `list_topics_timeline` endpoint to return `needs_manual_review` on each cell (low-touch: add it to the SELECT in `backend/services/topics_service.py::list_topics_timeline` and include in cell shape).

- [ ] **Step 3: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit \
  --files frontend/src/components/TopicEvidenceDrawer.tsx frontend/src/components/TopicsTimeline.tsx backend/services/topics_service.py \
  --message "[EPIC-16] feat(fe): TopicEvidenceDrawer renders EvidenceTrail when present; TopicsTimeline shows ⚠️ on needs_manual_review cells"
```

---

## Phase 4 — End-to-end validation

### Task 14 — Manual smoke test + build-log update

**Files:**
- Create: `docs/project/config/2026-05-20-epic-16-manual-tests.md`
- Modify: `docs/project/config/build-log.md`
- Modify: `docs/project/config/codebase.md`

- [ ] **Step 1: Write the manual test script**

Create `docs/project/config/2026-05-20-epic-16-manual-tests.md`:

```markdown
# EPIC-16 Manual Test Plan

## Pre-requisites
- Migration 030 applied to Supabase
- Backend restarted
- Project default LLM set to a model with adequate context (Claude Sonnet 4.6 1M recommended)

## Scenario A — Call 2 (typical link + new + not-discussed)

1. Create a fresh project "EPIC-16 smoke"
2. Upload Call 1 transcript (any 5k-token doc with 3+ distinct topics) — process through call_topics + advance
3. Upload Call 2 transcript that mentions 2 of Call 1's topics + 1 new
4. At project_matching: link 2 + mark 1 as new. Click Save & Continue
5. Verify logs show NO BackgroundTask was spawned. The call's verify_new_status / verify_not_discussed_status / extract_updates_status are 'idle'
6. On project_updates, confirm 3-section layout. ② and ③ are disabled
7. Click ① Verify new — wait for ✓ done on section 1. Verify the new topic's card shows truly_new + extraction_grounded
8. Click ② Verify not discussed — wait for ✓ done
9. Click ③ Extract updates — wait for ✓ done. Verify each merged topic shows snapshot + evidence_trail with citations
10. Save & Continue — advances to artifacts
11. Open Topics tab → click the topic → drawer shows evidence_trail for the call 2 update

## Scenario B — Pass ① promotes a "missed match" to merged

1. At call_topics, deliberately extract a topic with a name that matches an existing one but with slightly different wording ("Mac issue" vs "MC Mac memory issue")
2. At project_matching, mark it as new (don't link)
3. On project_updates, click ① — verify the topic migrates to section 3 with the badge "moved from New"
4. Click ② then ③ — verify the migrated topic gets a full extraction

## Scenario C — Citation failure → needs_manual_review

1. Use a small / quirky transcript that's likely to confuse the LLM citation
2. Run ① — observe whether the retry path triggers. If it does and second attempt also fails, the topic should display ⚠ needs manual review

## Cleanup
- Delete the smoke project
```

- [ ] **Step 2: Run scenario A end-to-end on the dev environment**

Do it. Note failures + edge cases in the markdown file.

- [ ] **Step 3: Update `build-log.md`**

Append a new section dated 2026-05-20 summarising the EPIC-16 ship: files touched (~10), tests added (~10), migration 030 applied, manual test results.

- [ ] **Step 4: Update `codebase.md`**

Add entries for:
- `backend/services/topic_verification.py` — Pass ①/②/③ orchestration
- `backend/services/citation_verify.py` — verbatim post-verify utility
- `backend/prompts/{verify_new_topic, verify_not_discussed, extract_topic_updates}.py` — new workflow prompt bodies
- `frontend/src/components/EvidenceTrail.tsx` — chronological citation strip
- `frontend/src/components/TopicCitationBadge.tsx` — anchor-linked tag

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit \
  --files docs/project/config/2026-05-20-epic-16-manual-tests.md docs/project/config/build-log.md docs/project/config/codebase.md \
  --message "[EPIC-16] docs: manual test plan + build-log + codebase entries for RAG verification passes"
```

---

## Self-review (run after writing this plan)

- **Spec coverage:** ✅ each section of the design doc has at least one task implementing it. Sections 5.1-5.5 ↔ Tasks 5/6/7. Section 6 (anti-hallucination) ↔ Task 4 (citation_verify) + retry logic in Tasks 5-7. Section 7 (backend changes) ↔ Tasks 1-8. Section 8 (UI changes) ↔ Tasks 9-13. Section 10 (downstream impact) is a no-op for implementation but Task 13 enriches the drawer.
- **Placeholder scan:** ✅ no TBDs. The `// implementation in step 3` markers in the ProjectUpdatesStage rewrite are inline references to other steps within the same task — they unfold into actual code in subsequent steps of the same task.
- **Type consistency:** `verify_new_cache` is `Record<string, VerifyNewResult>` keyed by topic NAME (since new topics may not yet have a topic_id). `verify_not_discussed_cache` and `extract_updates_cache` are keyed by topic_id. Backend matches frontend keys throughout.
- **Risk: `window.location.reload()` in pass polling** — pragmatic but a hard reset that loses local state. Acceptable for MVP; consider a proper parent-refresh callback in a follow-up.
