# Call Topics Extraction Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite Call Topics extraction — new rubric-driven prompt, enriched schema (open_questions, is_parked, importance, rationale), OpenRouter as a 4th provider, and rich per-tile UI with decisions / actions / open-questions inline.

**Architecture:** Single-pass LLM extraction with a multi-section prompt (ROLE / RUBRIC / ANCHORS / FEW-SHOT / PROCESS) stored once in a Python constant — seed for new projects, fallback for missing rows, source for the "Reset to default" endpoint. OpenRouter added alongside Groq/Claude/OpenAI/DeepSeek using the existing `AsyncOpenAI` client pattern. Topic tile rewritten to show all three anchor sections inline; artifact type card gains provider + model pickers and an expandable prompt editor.

**Tech Stack:** Python 3.11 + FastAPI + Supabase (backend), Next.js 15 + React (frontend), pytest, ruff + black, eslint + prettier. All git via `python3 scripts/git_ops.py commit "[EPIC-11] <type>: <msg>"`.

**Spec:** [`docs/project/config/2026-04-22-call-topics-extraction-overhaul-design.md`](./2026-04-22-call-topics-extraction-overhaul-design.md)

---

## Task 1: DB migration 019 — new columns

**Files:**
- Create: `backend/database/migrations/019_call_topics_overhaul.sql`

- [ ] **Step 1: Write the migration SQL**

File `backend/database/migrations/019_call_topics_overhaul.sql`:
```sql
-- 019_call_topics_overhaul.sql
-- EPIC-11: Call Topics Extraction Overhaul — schema additions
-- Run in Supabase Dashboard → SQL Editor → New query
SET search_path = public;

-- 1. topic_updates: four new columns for the richer schema
ALTER TABLE public.topic_updates
  ADD COLUMN IF NOT EXISTS open_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS is_parked BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS importance TEXT NOT NULL DEFAULT 'medium',
  ADD COLUMN IF NOT EXISTS rationale TEXT NOT NULL DEFAULT '';

-- 2. artifact_types: model column for OpenRouter slugs
ALTER TABLE public.artifact_types
  ADD COLUMN IF NOT EXISTS model TEXT DEFAULT NULL;

-- 3. projects: default_model column for project-level OpenRouter default
ALTER TABLE public.projects
  ADD COLUMN IF NOT EXISTS default_model TEXT DEFAULT NULL;
```

- [ ] **Step 2: Run migration in Supabase dashboard**

Per project convention (see build-log 2026-04-13), DB migrations are run manually. Open Supabase dashboard → SQL Editor → paste the file contents → Run.

Expected: "Success. No rows returned."

- [ ] **Step 3: Verify schema**

In Supabase SQL editor:
```sql
SELECT column_name, data_type, column_default, is_nullable
FROM information_schema.columns
WHERE table_name = 'topic_updates' AND column_name IN ('open_questions', 'is_parked', 'importance', 'rationale');

SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'artifact_types' AND column_name = 'model';

SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'projects' AND column_name = 'default_model';
```

Expected: 4 rows for topic_updates, 1 row for artifact_types.model, 1 row for projects.default_model.

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-11] db: migration 019 — new topic columns + artifact_types.model + projects.default_model"
```

---

## Task 2: Prompt constants module — `backend/prompts/call_topics.py`

**Files:**
- Create: `backend/prompts/__init__.py` (empty module file)
- Create: `backend/prompts/call_topics.py`
- Test: `backend/tests/test_call_topics_prompt.py`

- [ ] **Step 1: Write the failing test**

File `backend/tests/test_call_topics_prompt.py`:
```python
from backend.prompts.call_topics import (
    CALL_TOPICS_DEFAULT_PROMPT,
    OLD_DEFAULT_PROMPT_STRING,
)


def test_prompt_has_all_five_blocks():
    """The new prompt must contain the 5 named blocks: ROLE, RUBRIC, ANCHORS, FEW-SHOT, PROCESS."""
    for block in ("[ROLE]", "[RUBRIC]", "[ANCHORS]", "[FEW-SHOT]", "[PROCESS]"):
        assert block in CALL_TOPICS_DEFAULT_PROMPT, f"Missing block: {block}"


def test_prompt_encodes_3_of_4_rubric():
    """The rubric must mention the 3-of-4 threshold and the 4 criteria by name."""
    p = CALL_TOPICS_DEFAULT_PROMPT
    assert "3 of" in p or "at least 3" in p.lower()
    for word in ("FORWARD LIFE", "ANCHOR", "SPECIFICITY", "DIALOGUE DEPTH"):
        assert word in p, f"Missing rubric criterion: {word}"


def test_prompt_encodes_three_anchor_types():
    """The prompt must distinguish decisions, follow_up_items, and open_questions."""
    for field in ("decisions", "follow_up_items", "open_questions"):
        assert field in CALL_TOPICS_DEFAULT_PROMPT, f"Missing anchor field: {field}"


def test_prompt_includes_parked_instruction():
    """Parked-item handling must be documented in the prompt."""
    assert "is_parked" in CALL_TOPICS_DEFAULT_PROMPT


def test_old_prompt_string_is_frozen_snapshot():
    """The old default must start with the pre-migration text for migration matching."""
    assert OLD_DEFAULT_PROMPT_STRING.startswith(
        "You are an expert at analysing business call transcripts. Extract every distinct topic discussed"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_call_topics_prompt.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.prompts'`.

- [ ] **Step 3: Create the package directory**

File `backend/prompts/__init__.py`: empty file (just creates the package).

- [ ] **Step 4: Write the constants module**

File `backend/prompts/call_topics.py`:
```python
"""
Single source of truth for the call_topics extraction prompt.

Consumed in three places — all reference the same constant:
1. Seed for new projects — DEFAULT_CALL_TOPICS_PROMPT in routers/artifact_types.py
2. Fallback in extract_call_topics — topics_service.py
3. GET /api/artifact-types/defaults/{category} — for the "Reset to default" button

OLD_DEFAULT_PROMPT_STRING is a frozen snapshot of the pre-migration prompt;
used by migration 020 to identify unedited rows that should be migrated.
"""

CALL_TOPICS_DEFAULT_PROMPT: str = """[ROLE]
You are an expert analyst of business call transcripts. Your output shapes a living project tracker that must be reliable enough to ship without cleanup. Precision and discipline matter more than coverage.

[RUBRIC]
A candidate is a topic worth extracting only when it meets AT LEAST 3 of these 4 criteria:

1. FORWARD LIFE — will this need attention after this call? Something uttered and complete the moment it was spoken (a greeting, a clarification, a one-line acknowledgement) does NOT qualify.

2. ANCHOR TYPE — has at least one of:
   - a decision pending (someone needs to decide something)
   - an action outstanding (someone needs to do something)
   - an open question or uncertainty (needs investigation)

3. SPECIFICITY — references named systems, metrics, people, frequencies, deadlines, or other concrete parameters. Vague statements like "we need to think about efficiency" only qualify if they got grounded in specifics later in the same discussion.

4. DIALOGUE DEPTH — at least 2 substantive turns (raised + responded to with information, pushback, question, or commitment). A single statement with no reaction is not a topic yet.

Candidates meeting only 1-2 criteria are filler or nested action items under a real topic — do NOT extract them as separate topics.

SPLITTING RULES — break into separate topics when sub-items have different owners, different timelines, or could be decided independently. Keep together when sub-items are inputs to one decision.

FILTERS — DO NOT extract:
- Re-explanations or onboarding narration. Test: "did anything new get decided or raised?" If no, skip.
- Pure logistics resolved in-call (meeting reschedules, CC lists, access provisioning) unless they remain open or depend on something technical.
- Pleasantries, tangents, and single-statement mentions with no reaction.

PARKED ITEMS — items flagged for later but with no current action ("we'll look at fat-tail modeling later"): EXTRACT these with is_parked=true. No actions, no decisions — just the open question and a summary.

[ANCHORS]
Every topic distributes its content across EXACTLY THREE distinct fields — do NOT merge:
- decisions[] — anything explicitly agreed or concluded in this call. Terse, declarative sentences.
- follow_up_items[] — concrete actions. When the owner is named, inline as prefix: "Nick: run benchmark", "Hassan: share EDS+ evidence". Strings only — no object structure.
- open_questions[] — unresolved uncertainties needing investigation. Phrase as questions.

If a thread has none of these three, it is not a topic.

[FEW-SHOT]

GOOD extraction (shape and discipline to mirror):
[
  {
    "name": "Risk model selection — LMAC vs MC Mac",
    "summary": "Nick raised that LMAC's composite handling may not scale to the full book of private assets. MC Mac was proposed as a fallback but has a documented 40GB-memory ceiling the EDS+ team already hit on a similar load. A benchmark run is required before committing — the outcome gates Phase 2 kickoff.",
    "transcript_excerpt": "Nick: I'm not convinced LMAC handles composites at full scale... Hassan: we hit the 40GB ceiling on MC Mac with the EDS+ load last quarter... Charlie: so we need the benchmark before we can move to Phase 2.",
    "decisions": ["Phase 2 kickoff gated on benchmark outcome."],
    "follow_up_items": ["Nick: run LMAC vs MC Mac benchmark on full book", "Hassan: share EDS+ memory-ceiling evidence with team"],
    "open_questions": ["Does MC Mac's 40GB ceiling apply with EDS+'s caching layer in front?", "Can FV Mac handle the private-markets piece separately if split?"],
    "status": "open",
    "owner": "Us",
    "sentiment": "concern",
    "is_parked": false,
    "importance": "high",
    "rationale": "All 4 criteria met — named systems (LMAC/MC Mac/FV Mac), named people, explicit decision gate, 5+ substantive turns."
  }
]

BAD extraction (fragmentation — do NOT produce output shaped like this):
[
  {"name": "LMAC feasibility"},
  {"name": "MC Mac memory issue"},
  {"name": "Phase 2 timeline"},
  {"name": "FV Mac caching"}
]
Correction: these are all inputs to one decision (risk model selection) with shared owners and one timeline. Merge into a single topic per the SPLITTING RULES.

[PROCESS]
Work in five internal steps (do not expose the steps — just return the final JSON array):

Step 1 — List every candidate thread in the transcript. Do not yet filter.
Step 2 — Cluster near-duplicates by shared subject AND shared commitments. Apply the SPLITTING RULES.
Step 3 — Apply the 3-of-4 RUBRIC to each cluster. Drop clusters meeting only 1-2 criteria.
Step 4 — For each surviving cluster:
  - Write a 3-6 sentence summary covering EVERY concrete detail (numbers, names, frequencies, deadlines, commitments). Do not compress. Completeness beats brevity.
  - Classify each anchor into decisions / follow_up_items / open_questions — NEVER merge them.
  - Copy the verbatim transcript excerpt covering the discussion (2-8 sentences). Use exact words.
  - Set importance: "high" if all 4 rubric criteria met, "medium" if exactly 3 of 4, "low" for parked items or weak edge cases.
  - Write a one-line rationale explaining which criteria were met (shown to the user as a tooltip).
Step 5 — For clusters with future life but no current decision/action/substantive turn, set is_parked=true. Leave follow_up_items empty; open_questions may hold the "what for later" hint.

Return ONLY a valid JSON array matching the schema. No markdown, no explanation."""


OLD_DEFAULT_PROMPT_STRING: str = (
    "You are an expert at analysing business call transcripts. Extract every distinct topic discussed — "
    "be exhaustive, do not merge separate topics into one.\n\n"
    "For each topic:\n"
    "- name: short label (3–6 words)\n"
    "- summary: 1–2 sentence recap of what was said\n"
    "- follow_up_items: concrete next steps or open questions (empty array if none)\n"
    "- decisions: anything explicitly agreed or decided (empty array if none)\n"
    "- status: open (unresolved), in_progress (being worked on), resolved (closed/agreed)\n"
    "- owner: Us (our team owns it), Client (client owns it), Both (shared)\n"
    "- sentiment: positive (good news/progress), neutral (informational), concern (risk/problem/blocker)\n\n"
    "Return ONLY a JSON array. No markdown, no explanation."
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_call_topics_prompt.py -v`
Expected: 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-11] backend: prompt constants module — CALL_TOPICS_DEFAULT_PROMPT + old snapshot"
```

---

## Task 3: Update Pydantic models + `_TOPIC_SCHEMA` + wire new fallback

**Files:**
- Modify: `backend/services/topics_service.py` (TopicIn/TopicUpdate/TopicOut, _TOPIC_SCHEMA, _normalize_topic, extract_call_topics)
- Test: `backend/tests/test_topics.py` (extend)

- [ ] **Step 1: Write failing tests for new schema fields**

Append to `backend/tests/test_topics.py`:
```python
def test_topic_in_accepts_new_fields():
    t = TopicIn(
        name="Risk model selection",
        summary="Benchmark gates Phase 2 kickoff.",
        follow_up_items=["Nick: run benchmark"],
        decisions=["Phase 2 gated on benchmark."],
        open_questions=["Does MC Mac's ceiling apply with caching?"],
        status="open", owner="Us", sentiment="concern",
        is_parked=False,
        importance="high",
        rationale="All 4 criteria met.",
    )
    assert t.open_questions == ["Does MC Mac's ceiling apply with caching?"]
    assert t.is_parked is False
    assert t.importance == "high"
    assert t.rationale == "All 4 criteria met."


def test_topic_in_defaults_for_new_fields():
    """New fields are optional with sensible defaults — backwards compat for old callers."""
    t = TopicIn(
        name="X", summary="y", follow_up_items=[], decisions=[],
        status="open", owner="Us", sentiment="neutral",
    )
    assert t.open_questions == []
    assert t.is_parked is False
    assert t.importance == "medium"
    assert t.rationale == ""


def test_topic_in_importance_validation():
    """Importance is restricted to high/medium/low."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        TopicIn(
            name="X", summary="y", follow_up_items=[], decisions=[],
            status="open", owner="Us", sentiment="neutral",
            importance="critical",  # invalid — must raise
        )


def test_extract_call_topics_uses_new_default_prompt(monkeypatch):
    """When no stored prompt is set, extract_call_topics uses CALL_TOPICS_DEFAULT_PROMPT."""
    from backend.prompts.call_topics import CALL_TOPICS_DEFAULT_PROMPT
    captured = {}

    async def fake_call_llm(prompt, llm):
        captured["prompt"] = prompt
        return []

    # Stub the DB to return a call with a transcript, project with no stored prompt
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"project_id": "p1", "transcript": "Some call transcript text.", "context": None,
         "default_llm": "groq", "name": "p1"}
    ]
    # Second .table().select().eq().eq().execute() for topics vocabulary — return []
    # Use side_effect on table to distinguish calls if needed — simplest: patch _call_llm + _get_topics_prompt directly
    monkeypatch.setattr("backend.services.topics_service._call_llm", fake_call_llm)
    monkeypatch.setattr(
        "backend.services.topics_service._get_topics_prompt",
        lambda project_id, db, category="call_topics": (None, None),
    )
    monkeypatch.setattr("backend.services.topics_service.get_client", lambda: mock_client)

    asyncio.run(extract_call_topics("call1"))

    assert "[ROLE]" in captured["prompt"]
    assert "[RUBRIC]" in captured["prompt"]
    assert CALL_TOPICS_DEFAULT_PROMPT in captured["prompt"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_topics.py -v -k "new_fields or importance or new_default_prompt"`
Expected: 4 tests FAIL (unexpected keyword 'open_questions', etc.).

- [ ] **Step 3: Update `TopicIn` and subclasses**

Edit `backend/services/topics_service.py` — replace the `TopicIn` class (lines ~38-62) with:
```python
class TopicIn(BaseModel):
    """One topic as submitted by the frontend (save endpoint)."""
    name: str
    summary: str
    follow_up_items: list[str]
    decisions: list[str]
    open_questions: list[str] = []
    status: Literal["open", "in_progress", "resolved"]
    owner: Literal["Us", "Client", "Both"]
    sentiment: Literal["positive", "neutral", "concern"]
    transcript_excerpt: Optional[str] = None
    is_parked: bool = False
    importance: Literal["high", "medium", "low"] = "medium"
    rationale: str = ""

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: object) -> object:
        return _normalize_status(v) if isinstance(v, str) else v

    @field_validator("owner", mode="before")
    @classmethod
    def normalize_owner(cls, v: object) -> object:
        return _normalize_owner(v) if isinstance(v, str) else v

    @field_validator("sentiment", mode="before")
    @classmethod
    def normalize_sentiment(cls, v: object) -> object:
        return _normalize_sentiment(v) if isinstance(v, str) else v
```

- [ ] **Step 4: Update `TopicOut` to surface new fields**

In the same file, replace `TopicOut` (lines ~71-86):
```python
class TopicOut(BaseModel):
    """One topic row as returned from DB queries."""
    id: str
    project_id: str
    name: str
    first_raised_call_id: Optional[str]
    calls_open: int
    archived: bool
    created_at: str
    # Latest update fields (populated from most recent topic_update row)
    summary: Optional[str] = None
    follow_up_items: list[str] = []
    decisions: list[str] = []
    open_questions: list[str] = []
    status: Optional[Literal["open", "in_progress", "resolved"]] = None
    owner: Optional[Literal["Us", "Client", "Both"]] = None
    sentiment: Optional[Literal["positive", "neutral", "concern"]] = None
    is_parked: bool = False
    importance: Literal["high", "medium", "low"] = "medium"
    rationale: str = ""
```

- [ ] **Step 5: Update `_TOPIC_SCHEMA` + `_normalize_topic` defaults**

Replace `_TOPIC_SCHEMA` (lines ~120-125):
```python
_TOPIC_SCHEMA = (
    '{"name":"string",'
    '"summary":"string — 3–6 sentences covering every concrete detail",'
    '"transcript_excerpt":"string — verbatim relevant section of the transcript, 2–8 sentences",'
    '"decisions":["string"],'
    '"follow_up_items":["string — action, with owner as prefix when named"],'
    '"open_questions":["string — phrased as a question"],'
    '"status":"open|in_progress|resolved",'
    '"owner":"Us|Client|Both",'
    '"sentiment":"positive|neutral|concern",'
    '"is_parked":false,'
    '"importance":"high|medium|low",'
    '"rationale":"one sentence — which rubric criteria were met"}'
)
```

In `_normalize_topic` (lines ~162-192), extend the defaults block at the bottom:
```python
    out.setdefault("name", "")
    out.setdefault("summary", "")
    out.setdefault("transcript_excerpt", None)
    out.setdefault("follow_up_items", [])
    out.setdefault("decisions", [])
    out.setdefault("open_questions", [])
    out.setdefault("status", "open")
    out.setdefault("owner", "Us")
    out.setdefault("sentiment", "neutral")
    out.setdefault("is_parked", False)
    out.setdefault("importance", "medium")
    out.setdefault("rationale", "")
    return out
```

- [ ] **Step 6: Wire the new constant into `extract_call_topics`**

At the top of `backend/services/topics_service.py`, in the import block at line ~108-111, add:
```python
from backend.prompts.call_topics import CALL_TOPICS_DEFAULT_PROMPT
```

In `extract_call_topics` (lines ~284-299), replace the inline fallback:
```python
    base_instruction = stored_prompt or CALL_TOPICS_DEFAULT_PROMPT
```

(Delete the entire 15-line inline string that used to follow `stored_prompt or (`.)

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_topics.py -v`
Expected: all topics tests PASS (existing + 4 new).

- [ ] **Step 8: Run ruff + black**

Run: `cd backend && ruff check . && black --check .`
Expected: 0 errors.

- [ ] **Step 9: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-11] backend: enriched TopicIn schema (open_questions, is_parked, importance, rationale) + wire new default prompt"
```

---

## Task 4: Migration 020 — migrate existing `call_topics.prompt` rows

**Files:**
- Create: `backend/database/migrations/020_migrate_call_topics_prompt.sql` — SQL snippet to REPLACE WHERE old-default
- Create: `backend/scripts/migrate_call_topics_prompt.py` — Python script that runs the update (Supabase pg connection doesn't accept huge multi-line string literals easily via SQL editor; safer via script)
- Test: `backend/tests/test_call_topics_prompt_migration.py`

- [ ] **Step 1: Write failing test for migration script**

File `backend/tests/test_call_topics_prompt_migration.py`:
```python
from unittest.mock import MagicMock
from backend.scripts.migrate_call_topics_prompt import migrate_prompts
from backend.prompts.call_topics import CALL_TOPICS_DEFAULT_PROMPT, OLD_DEFAULT_PROMPT_STRING


def test_migrates_only_unedited_rows():
    """Rows whose prompt equals OLD_DEFAULT_PROMPT_STRING should be updated.
    Customized rows should be left alone."""
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "row1", "prompt": OLD_DEFAULT_PROMPT_STRING, "project_id": "p1"},
        {"id": "row2", "prompt": "my custom edited prompt", "project_id": "p2"},
        {"id": "row3", "prompt": OLD_DEFAULT_PROMPT_STRING, "project_id": "p3"},
    ]

    result = migrate_prompts(db)

    assert result == {"migrated": 2, "preserved": 1}
    # Verify update called twice with the new prompt
    update_calls = db.table.return_value.update.call_args_list
    assert len(update_calls) == 2
    for call in update_calls:
        assert call.args[0] == {"prompt": CALL_TOPICS_DEFAULT_PROMPT}


def test_empty_project_list_returns_zero_counts():
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    result = migrate_prompts(db)
    assert result == {"migrated": 0, "preserved": 0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_call_topics_prompt_migration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.scripts'`.

- [ ] **Step 3: Write the migration script**

File `backend/scripts/__init__.py`: empty.

File `backend/scripts/migrate_call_topics_prompt.py`:
```python
"""
Migrate existing unedited call_topics prompts to the new default.
Run once after deploying the new prompt:
    cd backend && python -m scripts.migrate_call_topics_prompt
"""
from backend.database.supabase_client import get_client
from backend.prompts.call_topics import CALL_TOPICS_DEFAULT_PROMPT, OLD_DEFAULT_PROMPT_STRING
from backend.utils.logger import get_logger

logger = get_logger("migrate_call_topics_prompt")


def migrate_prompts(db) -> dict:
    """For each call_topics artifact type row:
    - If prompt == OLD_DEFAULT_PROMPT_STRING → update to CALL_TOPICS_DEFAULT_PROMPT
    - Else → leave untouched (user customized)
    Returns {"migrated": N, "preserved": M}.
    """
    rows = (
        db.table("artifact_types")
        .select("id, prompt, project_id")
        .eq("category", "call_topics")
        .execute()
        .data
    )

    migrated = 0
    preserved = 0
    for row in rows:
        if row["prompt"] == OLD_DEFAULT_PROMPT_STRING:
            db.table("artifact_types").update(
                {"prompt": CALL_TOPICS_DEFAULT_PROMPT}
            ).eq("id", row["id"]).execute()
            migrated += 1
            logger.info(f"🔄 [Migrate] Updated project {row['project_id']} call_topics prompt")
        else:
            preserved += 1

    logger.info(
        f"✅ [Migrate] Migrated {migrated} call_topics prompts; preserved {preserved} customized rows."
    )
    return {"migrated": migrated, "preserved": preserved}


if __name__ == "__main__":
    db = get_client()
    result = migrate_prompts(db)
    print(f"Done. Migrated: {result['migrated']}, Preserved: {result['preserved']}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_call_topics_prompt_migration.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Run the migration against real DB**

Run: `cd backend && python -m scripts.migrate_call_topics_prompt`
Expected output: `Done. Migrated: N, Preserved: M.`

- [ ] **Step 6: Verify via Supabase dashboard**

In SQL editor:
```sql
SELECT project_id, LEFT(prompt, 50) AS prompt_preview
FROM artifact_types
WHERE category = 'call_topics';
```

Expected: rows previously matching the old default now begin with `"[ROLE]\nYou are an expert analyst..."`.

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-11] backend: migrate existing call_topics prompts to new rubric-driven default"
```

---

## Task 5: "Reset to default" endpoint

**Files:**
- Modify: `backend/routers/artifact_types.py` — add GET `/api/artifact-types/defaults/{category}`
- Modify: `backend/main.py` — (router already registered, no change expected; verify only)
- Test: `backend/tests/test_artifact_types.py` — extend

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_artifact_types.py`:
```python
def test_get_defaults_for_call_topics_returns_new_default(client):
    """GET /api/artifact-types/defaults/call_topics returns the canonical default."""
    from backend.prompts.call_topics import CALL_TOPICS_DEFAULT_PROMPT

    resp = client.get("/api/artifact-types/defaults/call_topics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["prompt"] == CALL_TOPICS_DEFAULT_PROMPT
    assert body["name"] == "Call Topics Extraction"
    assert body["category"] == "call_topics"
    assert body["llm"] == "openrouter"
    assert body["model"] == "anthropic/claude-sonnet-4.6"


def test_get_defaults_for_unknown_category_returns_404(client):
    resp = client.get("/api/artifact-types/defaults/nonexistent")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_artifact_types.py::test_get_defaults_for_call_topics_returns_new_default -v`
Expected: FAIL with 404 (route does not exist yet).

- [ ] **Step 3: Add endpoint to `backend/routers/artifact_types.py`**

First, update the top of the file — add import:
```python
from backend.prompts.call_topics import CALL_TOPICS_DEFAULT_PROMPT
```

Then update `DEFAULT_CALL_TOPICS_PROMPT` (around line 76-93) to reference the constant and add llm/model:
```python
DEFAULT_CALL_TOPICS_PROMPT = {
    "name": "Call Topics Extraction",
    "prompt": CALL_TOPICS_DEFAULT_PROMPT,
    "is_default": True,
    "category": "call_topics",
    "llm": "openrouter",
    "model": "anthropic/claude-sonnet-4.6",
}
```

Then append a new endpoint after the existing routes in the same file (end of file, before any final lines):
```python
_DEFAULTS_BY_CATEGORY = {
    "call_topics": DEFAULT_CALL_TOPICS_PROMPT,
    "project_topics": DEFAULT_PROJECT_TOPICS_PROMPT,
    "merge_verification": DEFAULT_MERGE_VERIFICATION_PROMPT,
    "not_discussed_check": DEFAULT_NOT_DISCUSSED_CHECK_PROMPT,
}


@router.get("/artifact-types/defaults/{category}")
def get_default_for_category(category: str):
    """Return the canonical default artifact-type payload for a workflow category.
    Used by the 'Reset to default' button in the UI."""
    if category not in _DEFAULTS_BY_CATEGORY:
        raise HTTPException(status_code=404, detail=f"Unknown category: {category}")
    payload = _DEFAULTS_BY_CATEGORY[category].copy()
    # Ensure llm/model keys always present (some old defaults lacked them)
    payload.setdefault("llm", None)
    payload.setdefault("model", None)
    return payload
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_artifact_types.py -v`
Expected: all artifact_types tests PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-11] backend: GET /api/artifact-types/defaults/{category} endpoint for reset-to-default"
```

---

## Task 6: Parallel prompt modules for the other 3 categories

**Files:**
- Create: `backend/prompts/artifacts.py` (holds per-type defaults)
- Create: `backend/prompts/project_topics.py`
- Create: `backend/prompts/merge_verification.py`
- Create: `backend/prompts/not_discussed_check.py`
- Modify: `backend/routers/artifact_types.py` (reference constants)
- Test: `backend/tests/test_workflow_prompts_ssot.py`

- [ ] **Step 1: Write failing test for single-source-of-truth across categories**

File `backend/tests/test_workflow_prompts_ssot.py`:
```python
from backend.prompts.call_topics import CALL_TOPICS_DEFAULT_PROMPT
from backend.prompts.project_topics import PROJECT_TOPICS_DEFAULT_PROMPT
from backend.prompts.merge_verification import MERGE_VERIFICATION_DEFAULT_PROMPT
from backend.prompts.not_discussed_check import NOT_DISCUSSED_DEFAULT_PROMPT
from backend.routers.artifact_types import (
    DEFAULT_CALL_TOPICS_PROMPT,
    DEFAULT_PROJECT_TOPICS_PROMPT,
    DEFAULT_MERGE_VERIFICATION_PROMPT,
    DEFAULT_NOT_DISCUSSED_CHECK_PROMPT,
)


def test_seeds_reference_constants():
    assert DEFAULT_CALL_TOPICS_PROMPT["prompt"] == CALL_TOPICS_DEFAULT_PROMPT
    assert DEFAULT_PROJECT_TOPICS_PROMPT["prompt"] == PROJECT_TOPICS_DEFAULT_PROMPT
    assert DEFAULT_MERGE_VERIFICATION_PROMPT["prompt"] == MERGE_VERIFICATION_DEFAULT_PROMPT
    assert DEFAULT_NOT_DISCUSSED_CHECK_PROMPT["prompt"] == NOT_DISCUSSED_DEFAULT_PROMPT


def test_defaults_include_openrouter_model_where_recommended():
    """Per §4.4.4 + §7 Q4 resolution — call_topics / artifacts / merge_verification
    default to openrouter + claude-sonnet-4.6 for new projects."""
    assert DEFAULT_CALL_TOPICS_PROMPT["llm"] == "openrouter"
    assert DEFAULT_CALL_TOPICS_PROMPT["model"] == "anthropic/claude-sonnet-4.6"
    assert DEFAULT_MERGE_VERIFICATION_PROMPT["llm"] == "openrouter"
    assert DEFAULT_MERGE_VERIFICATION_PROMPT["model"] == "anthropic/claude-sonnet-4.6"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_workflow_prompts_ssot.py -v`
Expected: FAIL — modules don't exist.

- [ ] **Step 3: Create the 3 new prompt modules**

File `backend/prompts/project_topics.py`:
```python
"""Single source of truth for the project_topics (per-topic merge) prompt."""

PROJECT_TOPICS_DEFAULT_PROMPT: str = (
    "You are an expert at matching client call topics to an existing project topic backlog.\n\n"
    "Given topics extracted from the current call and the existing project topic list, "
    "classify each topic:\n"
    '- "followed_up": call topics that match an existing project topic (same business subject, '
    "possibly different wording). Use the existing topic name exactly. Update summary, status, "
    "follow_up_items, and decisions with new information from this call.\n"
    '- "not_discussed": existing project topics not covered by any call topic.\n'
    '- "new_topics": call topics with no match in the existing project list.\n\n'
    "Be generous with matching — slightly different wording for the same business subject "
    "counts as a match."
)
```

File `backend/prompts/merge_verification.py`:
```python
"""Single source of truth for the merge_verification prompt."""

MERGE_VERIFICATION_DEFAULT_PROMPT: str = (
    "You are a quality reviewer for project topic data. You are given:\n"
    "1. A merged topic (the result of combining existing project data with new call data)\n"
    "2. The full call transcript\n"
    "3. The existing follow-up items and decisions from all source topics\n\n"
    "Your job: verify that the merged topic did NOT lose any important information.\n\n"
    "Check specifically:\n"
    "- Are ALL follow-up items from the sources preserved? If any are missing, add them back.\n"
    "- Are ALL decisions from the sources preserved? If any are missing, add them back.\n"
    "- Does the summary cover all key points discussed in the transcript for this topic?\n"
    "  If anything important was dropped, add it back.\n"
    "- Are specific details (names, dates, numbers, commitments) preserved?\n\n"
    "Return the corrected topic as JSON. If nothing was lost, return the topic unchanged.\n"
    "Do NOT remove or shorten anything. Only ADD back what was lost."
)
```

File `backend/prompts/not_discussed_check.py`:
```python
"""Single source of truth for the not_discussed_check prompt."""

NOT_DISCUSSED_DEFAULT_PROMPT: str = (
    "You are checking whether a project topic was actually discussed in a call transcript.\n"
    "Given the topic name, its latest summary, and the full call transcript, determine:\n"
    "1. Was this topic mentioned or discussed in the call? (yes/no)\n"
    "2. If yes, provide the relevant transcript excerpt.\n\n"
    'Return JSON: {"discussed": true/false, "transcript_excerpt": "..." or null, '
    '"reasoning": "one sentence explanation"}'
)
```

File `backend/prompts/artifacts.py`:
```python
"""Single source of truth for default artifact-type prompts (per-type, per-category='artifacts')."""

DEFAULT_ARTIFACTS: list[dict] = [
    {
        "name": "Executive Summary",
        "prompt": (
            "Write a concise executive summary of this call in 3–5 bullet points. "
            "Use the Topics section to structure your summary around the key themes discussed. "
            "For each bullet: state the topic, what was decided or discussed, and its current status (open/resolved). "
            "Focus on decisions made, key outcomes, and overall direction."
        ),
    },
    {
        "name": "Next Steps & Action Items",
        "prompt": (
            "Extract all action items and next steps from this call. "
            "Group them by topic (use the Topics section as your guide). "
            "For each item state: the topic it belongs to, what needs to be done, "
            "who is responsible (Us / Client / Both), and any deadline discussed. "
            "Prioritise items from topics with sentiment=concern or status=open."
        ),
    },
    {
        "name": "Questions for Stakeholders",
        "prompt": (
            "List all open questions that remain unanswered after this call. "
            "Group them by topic (use the Topics section). "
            "For each question: state the topic, the question, and why it is blocking progress. "
            "Prioritise questions from topics that are open or in_progress."
        ),
    },
    {
        "name": "Email Summary (1-pager)",
        "prompt": (
            "Write a professional 1-page email summarising this call for the client. "
            "Structure it around the topics discussed (use the Topics section). "
            "For each topic: briefly state what was discussed, any decisions made, and follow-up items. "
            "Close with a consolidated next steps section. "
            "Tone: clear and business-professional."
        ),
    },
    {
        "name": "Email Follow-up (pre-next-call)",
        "prompt": (
            "Write a short follow-up email to send before the next call. "
            "For each open topic (from the Topics section), summarise: what was agreed, "
            "what each party should have completed before the next session, and what remains open. "
            "End with a proposed agenda for the next call based on in_progress and open topics."
        ),
    },
    {
        "name": "Next Call Meeting Invite Topics",
        "prompt": (
            "Generate a structured agenda for the next call. "
            "Base it on the Topics section: include all open and in_progress topics, "
            "ordered by priority (concern sentiment first, then by calls_open descending). "
            "For each agenda item: topic name, brief context (1 sentence), and the specific question or decision needed."
        ),
    },
]
```

- [ ] **Step 4: Wire constants into `backend/routers/artifact_types.py`**

Replace the inline `DEFAULT_ARTIFACT_TYPES` list (lines ~11-74) with:
```python
from backend.prompts.artifacts import DEFAULT_ARTIFACTS
from backend.prompts.project_topics import PROJECT_TOPICS_DEFAULT_PROMPT
from backend.prompts.merge_verification import MERGE_VERIFICATION_DEFAULT_PROMPT
from backend.prompts.not_discussed_check import NOT_DISCUSSED_DEFAULT_PROMPT

DEFAULT_ARTIFACT_TYPES: list[dict] = [
    {**t, "is_default": True, "llm": "openrouter", "model": "anthropic/claude-sonnet-4.6"}
    for t in DEFAULT_ARTIFACTS
]
```

Replace `DEFAULT_PROJECT_TOPICS_PROMPT`, `DEFAULT_MERGE_VERIFICATION_PROMPT`, `DEFAULT_NOT_DISCUSSED_CHECK_PROMPT` (lines ~95-146) with:
```python
DEFAULT_PROJECT_TOPICS_PROMPT = {
    "name": "Project Topics Merge",
    "prompt": PROJECT_TOPICS_DEFAULT_PROMPT,
    "is_default": True,
    "category": "project_topics",
    "llm": None,
    "model": None,
}

DEFAULT_MERGE_VERIFICATION_PROMPT = {
    "name": "Merge Verification",
    "prompt": MERGE_VERIFICATION_DEFAULT_PROMPT,
    "is_default": True,
    "category": "merge_verification",
    "llm": "openrouter",
    "model": "anthropic/claude-sonnet-4.6",
}

DEFAULT_NOT_DISCUSSED_CHECK_PROMPT = {
    "name": "Not-Discussed Verification",
    "prompt": NOT_DISCUSSED_DEFAULT_PROMPT,
    "is_default": True,
    "category": "not_discussed_check",
    "llm": "openrouter",
    "model": "google/gemini-2.5-pro",
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_workflow_prompts_ssot.py tests/test_artifact_types.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-11] backend: extract all workflow prompts into backend/prompts/* single-source-of-truth modules"
```

---

## Task 7: Add OpenRouter dispatch to `llm_service.py`

**Files:**
- Modify: `backend/services/llm_service.py`
- Test: `backend/tests/test_llm_service.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_llm_service.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.llm_service import generate_artifact, call_llm_raw


@pytest.mark.asyncio
async def test_openrouter_dispatches_with_base_url_and_model(monkeypatch):
    """generate_artifact(llm='openrouter', model='X') uses OpenRouter base_url + the given model."""
    captured = {}

    class FakeChatCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            class R:
                choices = [type("C", (), {"message": type("M", (), {"content": "result"})()})()]
                usage = type("U", (), {"prompt_tokens": 10, "completion_tokens": 5})()
            return R()

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = type("Chat", (), {"completions": FakeChatCompletions()})()

    monkeypatch.setattr("backend.services.llm_service.AsyncOpenAI", FakeAsyncOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    result = await generate_artifact(
        prompt_used="hello", transcript="t", llm="openrouter",
        model="anthropic/claude-sonnet-4.6",
    )

    assert result == "result"
    assert captured["base_url"] == "https://openrouter.ai/api/v1"
    assert captured["api_key"] == "test-key"
    assert captured["model"] == "anthropic/claude-sonnet-4.6"


@pytest.mark.asyncio
async def test_openrouter_without_model_raises():
    """generate_artifact(llm='openrouter') without model raises ValueError."""
    with pytest.raises(ValueError, match="model"):
        await generate_artifact(
            prompt_used="hello", transcript="t", llm="openrouter", model=None,
        )


@pytest.mark.asyncio
async def test_call_llm_raw_openrouter_branch(monkeypatch):
    """call_llm_raw also supports openrouter."""
    captured = {}

    class FakeChatCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            class R:
                choices = [type("C", (), {"message": type("M", (), {"content": "ok"})()})()]
                usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})()
            return R()

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = type("Chat", (), {"completions": FakeChatCompletions()})()

    monkeypatch.setattr("backend.services.llm_service.AsyncOpenAI", FakeAsyncOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "key2")

    result = await call_llm_raw("sys", "user", "openrouter", model="openai/gpt-4o")
    assert result == "ok"
    assert captured["base_url"] == "https://openrouter.ai/api/v1"
    assert captured["model"] == "openai/gpt-4o"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_llm_service.py -v -k openrouter`
Expected: FAIL — openrouter branch doesn't exist.

- [ ] **Step 3: Add openrouter branch to `generate_artifact`**

In `backend/services/llm_service.py`, update `generate_artifact` signature (line ~86-91):
```python
async def generate_artifact(
    prompt_used: str,
    transcript: str,
    llm: str,
    topics: list[dict] | None = None,
    *,
    model: str | None = None,
) -> str:
    """
    Generate an artifact using the specified LLM provider.
    llm must be one of: "groq", "deepseek", "claude", "openai", "openrouter".
    For llm="openrouter", `model` is required (OpenRouter model slug, e.g. "anthropic/claude-sonnet-4.6").
    If topics are provided, they are injected between transcript and task prompt.
    Retries up to 3 times with exponential backoff on rate-limit errors.
    """
```

Add the `openrouter` branch to the dispatch (after the `openai` branch, around line 135):
```python
    elif llm == "openrouter":
        if not model:
            raise ValueError("llm='openrouter' requires a non-empty `model` slug.")
        return await _generate_openai_compat(
            user_message,
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            base_url="https://openrouter.ai/api/v1",
            model=model,
            provider="OpenRouter",
        )
    else:
        raise ValueError(f"Unknown LLM provider: {llm!r}. Must be 'groq', 'deepseek', 'claude', 'openai', or 'openrouter'.")
```

Update the existing `else:` raise message to include `'openrouter'`.

- [ ] **Step 4: Add openrouter branch to `call_llm_raw`**

Update signature:
```python
async def call_llm_raw(system: str, user_message: str, llm: str, max_tokens: int = 4096, *, model: str | None = None) -> str:
```

Extend the `elif llm in ("groq", "deepseek", "openai")` branch to include openrouter. Simplest: add a new branch before the final `else`:

```python
    elif llm == "openrouter":
        if not model:
            raise ValueError("llm='openrouter' requires a non-empty `model` slug.")
        client_oa = AsyncOpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            base_url="https://openrouter.ai/api/v1",
        )
        for attempt in range(_MAX_RETRIES + 1):
            try:
                logger.info(f"🤖 [OpenRouter/{model}] Calling LLM (attempt {attempt + 1})")
                response = await client_oa.chat.completions.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user_message},
                    ],
                )
                content = response.choices[0].message.content or ""
                logger.info(
                    f"✅ [OpenRouter/{model}] Done — "
                    f"input={response.usage.prompt_tokens} output={response.usage.completion_tokens}"
                )
                return content
            except OpenAIRateLimitError:
                if attempt == _MAX_RETRIES:
                    logger.error(f"❌ [OpenRouter/{model}] Rate limit exhausted after 3 retries")
                    raise
                wait = 2 ** attempt
                logger.warning(f"⚠️ [OpenRouter/{model}] Rate limited — retrying in {wait}s")
                await asyncio.sleep(wait)
        raise RuntimeError("unreachable")  # pragma: no cover
    else:
        raise ValueError(f"Unknown LLM provider: {llm!r}. Must be 'groq', 'deepseek', 'claude', 'openai', or 'openrouter'.")
```

Update the final `raise ValueError` at line 83 to mention `'openrouter'`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_llm_service.py -v`
Expected: all PASS (existing + 3 new).

- [ ] **Step 6: Add OPENROUTER_API_KEY to env.example + README**

In `backend/.env.example`, after existing `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` entries, add:
```
OPENROUTER_API_KEY=
```

In project `README.md`, find the env vars section; add a line under the LLM keys:
```
OPENROUTER_API_KEY  # get from https://openrouter.ai/keys — enables per-prompt model selection
```

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-11] backend: OpenRouter as 4th LLM provider in llm_service + OPENROUTER_API_KEY env"
```

---

## Task 8: Propagate `model` field through APIs + call sites

**Files:**
- Modify: `backend/routers/artifact_types.py` (ArtifactTypeCreate/Update, create + update endpoints)
- Modify: `backend/routers/projects.py` (ProjectUpdate + update endpoint)
- Modify: `backend/services/topics_service.py` (extract_call_topics resolves model)
- Modify: `backend/routers/artifacts.py` (generate_artifact call site passes model)
- Test: `backend/tests/test_artifact_types.py`, `backend/tests/test_projects.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_artifact_types.py`:
```python
def test_create_artifact_type_accepts_model(client, seeded_project):
    resp = client.post(
        f"/api/projects/{seeded_project}/artifact-types",
        json={
            "name": "Custom", "prompt": "Do X.",
            "llm": "openrouter", "model": "openai/gpt-4o",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["llm"] == "openrouter"
    assert body["model"] == "openai/gpt-4o"


def test_update_artifact_type_accepts_model(client, seeded_project, existing_artifact_type_id):
    resp = client.patch(
        f"/api/projects/{seeded_project}/artifact-types/{existing_artifact_type_id}",
        json={"llm": "openrouter", "model": "google/gemini-2.5-pro"},
    )
    assert resp.status_code == 200
    assert resp.json()["model"] == "google/gemini-2.5-pro"
```

Append to `backend/tests/test_projects.py`:
```python
def test_patch_project_accepts_default_model(client, seeded_project):
    resp = client.patch(
        f"/api/projects/{seeded_project}",
        json={"default_llm": "openrouter", "default_model": "anthropic/claude-sonnet-4.6"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["default_llm"] == "openrouter"
    assert body["default_model"] == "anthropic/claude-sonnet-4.6"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_artifact_types.py tests/test_projects.py -v -k "model"`
Expected: FAIL — `model` field not in Pydantic schema.

- [ ] **Step 3: Update Pydantic models in `artifact_types.py`**

Find `ArtifactTypeCreate` and `ArtifactTypeUpdate` (lines ~192-205) and replace with:
```python
class ArtifactTypeCreate(BaseModel):
    name: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    llm: Literal["groq", "deepseek", "claude", "openai", "openrouter"] | None = None
    model: str | None = None
    context_scope: Literal["call", "project"] = "call"


class ArtifactTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    prompt: str | None = Field(default=None, min_length=1)
    llm: Literal["groq", "deepseek", "claude", "openai", "openrouter"] | None = Field(default=None)
    model: str | None = Field(default=None)
    context_scope: Literal["call", "project"] | None = Field(default=None)
    is_default: bool | None = Field(default=None)
```

Update `create_artifact_type` (around line 227-244) — add `"model": payload.model,` to the insert dict:
```python
    result = (
        client.table("artifact_types")
        .insert({
            "project_id": project_id,
            "name": payload.name,
            "prompt": payload.prompt,
            "is_default": False,
            "category": "artifacts",
            "llm": payload.llm,
            "model": payload.model,
            "context_scope": payload.context_scope,
        })
        .execute()
    )
```

- [ ] **Step 4: Update Pydantic models in `projects.py`**

Open `backend/routers/projects.py` and find `ProjectUpdate` (grep for `default_llm`). Add `default_model`:
```python
class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    context: str | None = None
    default_llm: Literal["groq", "deepseek", "claude", "openai", "openrouter"] | None = None
    default_model: str | None = None
```

In the project `GET` single-project endpoint response and `PATCH` endpoint, ensure `default_model` is selected (usually `.select("*")` already covers it — no code change needed since the DB migration added the column).

- [ ] **Step 5: Wire model resolution in `topics_service.extract_call_topics`**

Open `backend/services/topics_service.py`. Update `_get_topics_prompt` (lines ~241-255) to also return `model`:
```python
def _get_topics_prompt(project_id: str, db, category: str = "call_topics") -> tuple[str | None, str | None, str | None]:
    """Return (prompt, llm, model) for the given workflow category, or (None, None, None) if not found."""
    rows = (
        db.table("artifact_types")
        .select("prompt, llm, model")
        .eq("project_id", project_id)
        .eq("category", category)
        .order("created_at")
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        return None, None, None
    return rows[0]["prompt"], rows[0].get("llm"), rows[0].get("model")
```

In `extract_call_topics` (lines ~276-341), update the prompt/llm resolution block:
```python
    stored_prompt, stored_llm, stored_model = _get_topics_prompt(project_id, db, category="call_topics")
    proj_rows = db.table("projects").select("default_llm, default_model, context").eq("id", project_id).execute().data
    if stored_llm is None:
        stored_llm = proj_rows[0].get("default_llm") if proj_rows else "groq"
    if stored_model is None:
        stored_model = proj_rows[0].get("default_model") if proj_rows else None
    llm = stored_llm or "groq"
    model = stored_model
    project_context = (proj_rows[0].get("context") or "").strip() if proj_rows else ""
```

Pass `model` through to `_call_llm`:
```python
    raw = await _call_llm(prompt, llm, model=model)
```

Update `_call_llm` signature (line ~128):
```python
async def _call_llm(prompt: str, llm: str, *, model: str | None = None) -> list[dict] | dict:
    logger.info(f"🤖 [{llm}] Extracting topics")
    raw = await call_llm_raw(_EXTRACT_SYSTEM, prompt, llm, model=model)
```

- [ ] **Step 6: Wire model resolution in `routers/artifacts.py`**

Open `backend/routers/artifacts.py`. Find the `generate_artifact` call site (audit doc says ~line 247-255). Before the call, resolve effective model from artifact_type.model → project.default_model → None. Pass as `model=`.

Look for the block assigning `llm` currently; add parallel model resolution. Example pattern:
```python
    # Resolve effective LLM + model: artifact type override → project default
    effective_llm = type_row.get("llm") or project.get("default_llm") or "groq"
    effective_model = type_row.get("model") or project.get("default_model")
    content = await generate_artifact(
        effective_prompt, full_context, effective_llm,
        topics=call_topics,
        model=effective_model,
    )
```

(If the file structure differs, apply the same "add model resolution alongside llm" pattern wherever `generate_artifact` is called.)

- [ ] **Step 7: Run all backend tests**

Run: `cd backend && python -m pytest -v`
Expected: all tests PASS. Ruff: `ruff check . && black --check .` → clean.

- [ ] **Step 8: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-11] backend: propagate model field through artifact_types + projects APIs and extract/artifact call sites"
```

---

## Task 9: Frontend types + `MODEL_RECOMMENDATIONS` constant

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/constants/models.ts`

- [ ] **Step 1: Extend `LLMProvider` and topic/artifact types**

Edit `frontend/src/types/index.ts`. Replace line 4:
```typescript
export type LLMProvider = "groq" | "deepseek" | "claude" | "openai" | "openrouter";
```

Add `default_model` to `Project` (around line 6):
```typescript
export interface Project {
  id: string;
  name: string;
  description: string | null;
  default_llm: LLMProvider;
  default_model: string | null;
  context: string | null;
  created_at: string;
}
```

Add `model` to `ArtifactType` (around line 48):
```typescript
export interface ArtifactType {
  id: string;
  project_id: string;
  name: string;
  prompt: string;
  is_default: boolean;
  category: ArtifactCategory;
  llm: LLMProvider | null;
  model: string | null;
  context_scope: ContextScope;
  created_at: string;
}
```

Extend `ArtifactCategory` to include the extra categories already used in backend:
```typescript
export type ArtifactCategory = "artifacts" | "topics" | "call_topics" | "project_topics" | "merge_verification" | "not_discussed_check";
```

Extend `TopicData` (around line 80) with the four new fields:
```typescript
export interface TopicData {
  topic_id?: string | null;
  name: string;
  summary: string;
  follow_up_items: string[];
  decisions: string[];
  open_questions: string[];
  status: TopicStatus;
  owner: TopicOwner;
  sentiment: TopicSentiment;
  is_parked: boolean;
  importance: "high" | "medium" | "low";
  rationale: string;
  calls_open?: number;
  not_discussed?: boolean;
  pending_merge?: boolean;
  verification_status?: "pending" | "confirmed" | "flagged";
  _source_topic_ids?: string[];
  transcript_excerpt?: string | null;
  archived_later?: boolean;
  merged_into_name?: string | null;
}
```

- [ ] **Step 2: Create `MODEL_RECOMMENDATIONS` constants**

File `frontend/src/constants/models.ts`:
```typescript
import type { ArtifactCategory } from "@/types";

export type ModelTier = "best" | "strong" | "balanced" | "budget" | "fallback";

export interface ModelRecommendation {
  slug: string;
  tier: ModelTier;
  label: string;
  priceHint?: string;   // optional display hint; not authoritative
}

/**
 * Curated per-category model recommendations for the OpenRouter picker.
 * This is a frontend UI affordance — backend does not validate against this list.
 * Users can always enter a custom slug.
 */
export const MODEL_RECOMMENDATIONS: Record<ArtifactCategory, ModelRecommendation[]> = {
  call_topics: [
    { slug: "anthropic/claude-sonnet-4.6",             tier: "best",     label: "Best quality · default", priceHint: "$3 / $15 per 1M tok" },
    { slug: "openai/gpt-4o",                            tier: "strong",   label: "Strong alt",             priceHint: "$2.5 / $10" },
    { slug: "google/gemini-2.5-pro",                    tier: "balanced", label: "Long context",           priceHint: "$1.25 / $5" },
    { slug: "deepseek/deepseek-chat",                   tier: "budget",   label: "Budget",                 priceHint: "$0.27 / $1.10" },
    { slug: "meta-llama/llama-3.3-70b-instruct",        tier: "fallback", label: "Fallback" },
  ],
  artifacts: [
    { slug: "anthropic/claude-sonnet-4.6",             tier: "best",     label: "Best quality · default", priceHint: "$3 / $15 per 1M tok" },
    { slug: "openai/gpt-4o",                            tier: "strong",   label: "Strong alt",             priceHint: "$2.5 / $10" },
    { slug: "google/gemini-2.5-pro",                    tier: "balanced", label: "Long context",           priceHint: "$1.25 / $5" },
    { slug: "deepseek/deepseek-chat",                   tier: "budget",   label: "Budget",                 priceHint: "$0.27 / $1.10" },
  ],
  merge_verification: [
    { slug: "anthropic/claude-sonnet-4.6",             tier: "best",     label: "Best quality · default" },
    { slug: "openai/gpt-4o",                            tier: "strong",   label: "Strong alt" },
    { slug: "google/gemini-2.5-pro",                    tier: "balanced", label: "Balanced" },
  ],
  not_discussed_check: [
    { slug: "google/gemini-2.5-pro",                    tier: "best",     label: "Best — long context, default" },
    { slug: "openai/gpt-4o-mini",                       tier: "strong",   label: "Strong alt" },
    { slug: "deepseek/deepseek-chat",                   tier: "budget",   label: "Budget" },
  ],
  // Legacy categories — empty list (fall back to project default)
  topics: [],
  project_topics: [],
};

export const PROVIDER_LABELS: Record<LLMProvider | "inherit", string> = {
  inherit:    "Inherit project",
  groq:       "Groq (direct)",
  deepseek:   "DeepSeek (direct)",
  claude:     "Claude (direct)",
  openai:     "OpenAI (direct)",
  openrouter: "OpenRouter ⭐",
};

import type { LLMProvider } from "@/types";
```

- [ ] **Step 3: Verify type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors (if errors, fix any broken consumers of `TopicData` or `ArtifactType` by adding the missing fields inline where mock data is constructed).

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-11] frontend: extend types with openrouter + new topic fields + MODEL_RECOMMENDATIONS constants"
```

---

## Task 10: Rewrite `CallTopicsStage` `TopicRow` with 3 sections + parked + importance dot

**Files:**
- Modify: `frontend/src/components/CallTopicsStage.tsx`

- [ ] **Step 1: Replace the `TopicRow` component**

Open `frontend/src/components/CallTopicsStage.tsx`. Replace the entire `TopicRow` function (lines ~43-230) with the following:

```tsx
const IMPORTANCE_COLOR: Record<"high" | "medium" | "low", string> = {
  high:   "#ae2a19",
  medium: "#ff991f",
  low:    "#97a0af",
};

function TopicRow({
  topic,
  onChange,
  onDelete,
  onViewSource,
}: {
  topic: TopicData;
  onChange: (updated: TopicData) => void;
  onDelete: () => void;
  onViewSource?: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const parked = topic.is_parked;
  const dotColor = parked ? "#97a0af" : IMPORTANCE_COLOR[topic.importance] ?? "#ff991f";
  const borderColor = parked ? "#97a0af" : "#0052cc";
  const background = parked ? "#fafbfc" : "white";

  const renderOwnerHighlight = (text: string): React.ReactNode => {
    const m = text.match(/^([A-Z][a-z]+(?:\s[A-Z][a-z]+)?):\s*(.*)$/);
    if (!m) return text;
    return (<>
      <strong>{m[1]}:</strong> {m[2]}
    </>);
  };

  return (
    <div style={{
      borderBottom: "1px solid #f0f1f3",
      padding: "14px 18px",
      borderLeft: `3px solid ${borderColor}`,
      background,
      opacity: parked ? 0.92 : 1,
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flex: 1, minWidth: 0 }}>
          <span
            title={topic.rationale || "No rationale provided"}
            style={{ width: 8, height: 8, borderRadius: "50%", background: dotColor, display: "inline-block", flexShrink: 0 }}
          />
          {editing ? (
            <input
              value={topic.name}
              onChange={(e) => onChange({ ...topic, name: e.target.value })}
              style={{
                fontSize: 13, fontWeight: 600, color: "#172b4d",
                border: "none", borderBottom: "2px solid #0052cc", outline: "none",
                background: "transparent", flex: 1, minWidth: 0, fontFamily: "inherit",
              }}
            />
          ) : (
            <strong style={{ fontSize: 13, color: "#172b4d" }}>{topic.name}</strong>
          )}
          {parked ? (
            <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", background: "#f4f5f7", color: "#5e6c84", borderRadius: 3 }}>
              ⏸ PARKED
            </span>
          ) : (
            <span style={{
              fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 3,
              ...(STATUS_BADGE[topic.status] ?? STATUS_BADGE.open),
            }}>
              {topic.status?.replace("_", " ")}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
          <span style={{ fontSize: 10, color: "#5e6c84" }}>
            {topic.sentiment?.toUpperCase()} · {topic.owner?.toUpperCase()}
          </span>
          <button onClick={() => setEditing((v) => !v)} title={editing ? "Done editing" : "Edit"}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: 13, color: editing ? "#0052cc" : "#97a0af" }}
          >{editing ? "✓" : "✎"}</button>
          <button onClick={onDelete} title="Remove"
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: 13, color: "#bfc5ce" }}
          >✕</button>
        </div>
      </div>

      {/* Summary */}
      {editing ? (
        <textarea
          value={topic.summary}
          onChange={(e) => onChange({ ...topic, summary: e.target.value })}
          placeholder="3–6 sentence summary…"
          rows={5}
          style={{
            width: "100%", margin: "8px 0 10px", fontSize: 12, color: "#172b4d",
            border: "1px solid #dfe1e6", borderRadius: 4, padding: "6px 8px",
            fontFamily: "inherit", resize: "vertical", boxSizing: "border-box",
          }}
        />
      ) : (
        <p style={{ fontSize: 12, color: "#172b4d", margin: "6px 0 10px", lineHeight: 1.5 }}>
          {topic.summary}
        </p>
      )}

      {/* Decisions */}
      {(topic.decisions?.length ?? 0) > 0 && (
        <SectionBlock
          label="Decisions"
          count={topic.decisions.length}
          bg="#f4f5f7" color="#5e6c84"
          items={topic.decisions}
          prefix="✓ "
          editing={editing}
          onChange={(items) => onChange({ ...topic, decisions: items })}
        />
      )}

      {/* Actions (follow_up_items) — hidden for parked topics */}
      {!parked && (topic.follow_up_items?.length ?? 0) > 0 && (
        <SectionBlock
          label="Actions"
          count={topic.follow_up_items.length}
          bg="#fff8e6" color="#974f0c"
          items={topic.follow_up_items}
          prefix="→ "
          renderItem={renderOwnerHighlight}
          editing={editing}
          onChange={(items) => onChange({ ...topic, follow_up_items: items })}
        />
      )}

      {/* Open questions */}
      {(topic.open_questions?.length ?? 0) > 0 && (
        <SectionBlock
          label="Open questions"
          count={topic.open_questions.length}
          bg="#eef5ff" color="#0052cc"
          items={topic.open_questions}
          prefix="? "
          editing={editing}
          onChange={(items) => onChange({ ...topic, open_questions: items })}
        />
      )}

      {/* Footer strip */}
      <div style={{ display: "flex", gap: 10, paddingTop: 8, marginTop: 6, borderTop: "1px dashed #dfe1e6", alignItems: "center" }}>
        {onViewSource && (
          <button onClick={onViewSource} style={{
            background: "none", border: "none", cursor: "pointer",
            fontSize: 11, color: "#0052cc", padding: 0, fontFamily: "inherit", textDecoration: "underline",
          }}>📄 Source excerpt ↗</button>
        )}
        {parked && (
          <button
            onClick={() => onChange({ ...topic, is_parked: false })}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: 11, color: "#5e6c84", textDecoration: "underline" }}
          >Un-park</button>
        )}
        {!parked && editing && (
          <button
            onClick={() => onChange({ ...topic, is_parked: true })}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: 11, color: "#5e6c84", textDecoration: "underline" }}
          >⏸ Park</button>
        )}
        {editing && (
          <div style={{ display: "flex", gap: 6 }}>
            <select value={topic.status} onChange={(e) => onChange({ ...topic, status: e.target.value as TopicStatus })} style={SEL}>
              <option value="open">Open</option>
              <option value="in_progress">In Progress</option>
              <option value="resolved">Resolved</option>
            </select>
            <select value={topic.owner} onChange={(e) => onChange({ ...topic, owner: e.target.value as TopicOwner })} style={SEL}>
              <option value="Us">Us</option>
              <option value="Client">Client</option>
              <option value="Both">Both</option>
            </select>
            <select value={topic.sentiment} onChange={(e) => onChange({ ...topic, sentiment: e.target.value as TopicSentiment })} style={SEL}>
              <option value="positive">Positive</option>
              <option value="neutral">Neutral</option>
              <option value="concern">Concern</option>
            </select>
          </div>
        )}
      </div>
    </div>
  );
}

function SectionBlock({
  label, count, bg, color, items, prefix, editing, onChange, renderItem,
}: {
  label: string;
  count: number;
  bg: string;
  color: string;
  items: string[];
  prefix: string;
  editing: boolean;
  onChange: (items: string[]) => void;
  renderItem?: (item: string) => React.ReactNode;
}) {
  const [newText, setNewText] = useState("");
  return (
    <div style={{ background: bg, borderRadius: 4, padding: "9px 11px", marginBottom: 6 }}>
      <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color, letterSpacing: ".05em", marginBottom: 5 }}>
        {label} ({count})
      </div>
      <div style={{ fontSize: 11.5, color: "#172b4d", lineHeight: 1.55 }}>
        {items.map((item, i) => (
          editing ? (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
              <span style={{ color: "#97a0af", fontSize: 11 }}>{prefix}</span>
              <input
                value={item}
                onChange={(e) => {
                  const next = [...items];
                  next[i] = e.target.value;
                  onChange(next);
                }}
                style={{ flex: 1, fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "3px 6px", fontFamily: "inherit" }}
              />
              <button onClick={() => onChange(items.filter((_, idx) => idx !== i))}
                style={{ background: "none", border: "none", cursor: "pointer", color: "#bfc5ce", fontSize: 11 }}
              >✕</button>
            </div>
          ) : (
            <div key={i}>
              {prefix}{renderItem ? renderItem(item) : item}
            </div>
          )
        ))}
        {editing && (
          <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
            <input
              value={newText}
              onChange={(e) => setNewText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && newText.trim()) {
                  onChange([...items, newText.trim()]);
                  setNewText("");
                }
              }}
              placeholder={`Add ${label.toLowerCase().replace(/s$/, "")}…`}
              style={{ flex: 1, fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "3px 6px", fontFamily: "inherit" }}
            />
            <button onClick={() => {
              if (newText.trim()) { onChange([...items, newText.trim()]); setNewText(""); }
            }} style={{ fontSize: 11, color: "#0052cc", background: "none", border: "1px solid #b3c6e8", borderRadius: 4, padding: "3px 10px", cursor: "pointer" }}>
              Add
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check + lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: 0 errors.

- [ ] **Step 3: Manual smoke check**

Start the dev server: `cd frontend && npm run dev`. Open an existing project's Call Topics stage on a call with extracted topics. Verify:
- Tile renders with 3 sections (Decisions / Actions / Open questions) when populated
- Empty sections are hidden
- Importance dot shows (grey for unseeded data with `importance='medium'` default → will render amber by fallback)
- Edit toggle (✎) opens editable textareas + dropdowns
- Delete (✕) still works
- Source excerpt link still opens TopicEvidenceDrawer

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-11] frontend: rewrite CallTopicsStage TopicRow — 3 anchor sections, parked variant, importance dot + tooltip"
```

---

## Task 11: Ripple new fields to `TopicEditor` / `TopicsDashboard` / `TopicEvidenceDrawer`

**Files:**
- Modify: `frontend/src/components/TopicEditor.tsx`
- Modify: `frontend/src/components/TopicsDashboard.tsx`
- Modify: `frontend/src/components/TopicsPanel.tsx`
- Modify: `frontend/src/components/TopicEvidenceDrawer.tsx`

- [ ] **Step 1: `TopicEditor.tsx` — render Open questions + Parked toggle**

In `frontend/src/components/TopicEditor.tsx`, find the section that renders `follow_up_items`. Immediately below it, add a parallel rendering block for `open_questions` following the same visual pattern (blue background `#eef5ff`, prefix `?`, editable list). Also add a "Parked" checkbox near the status dropdown:
```tsx
<label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#5e6c84" }}>
  <input
    type="checkbox"
    checked={topic.is_parked ?? false}
    onChange={(e) => onChange({ ...topic, is_parked: e.target.checked })}
  />
  Parked
</label>
```

- [ ] **Step 2: `TopicsDashboard.tsx` — show open_questions count + is_parked chip**

In `frontend/src/components/TopicsDashboard.tsx`, find the topic row rendering. Near the existing follow-ups count, add:
```tsx
{(topic.open_questions?.length ?? 0) > 0 && (
  <span style={{ fontSize: 10, color: "#0052cc" }}>
    {topic.open_questions.length} open Q
  </span>
)}
{topic.is_parked && (
  <span style={{ fontSize: 9, fontWeight: 700, padding: "1px 5px", background: "#f4f5f7", color: "#5e6c84", borderRadius: 3 }}>
    ⏸ PARKED
  </span>
)}
```

- [ ] **Step 3: `TopicsPanel.tsx` — ripple (same pattern as Dashboard)**

Same additions as Step 2 in `frontend/src/components/TopicsPanel.tsx`.

- [ ] **Step 4: `TopicEvidenceDrawer.tsx` — render open_questions in the per-call card**

In `frontend/src/components/TopicEvidenceDrawer.tsx`, find where `decisions` and `follow_up_items` are rendered in the per-call cards. Immediately after those, add a rendering block for `open_questions` with blue styling (`#eef5ff` bg, `#0052cc` label color, `?` prefix). Same pattern.

- [ ] **Step 5: Type-check + lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-11] frontend: ripple open_questions + is_parked rendering to TopicEditor / Dashboard / Panel / EvidenceDrawer"
```

---

## Task 12: `ArtifactTypeCard` — provider dropdown, model picker, expandable textarea, runtime preview, reset button

**Files:**
- Modify: `frontend/src/components/ArtifactTypeCard.tsx`
- Modify: `frontend/src/api/client.ts` (add `getDefaults` endpoint)

- [ ] **Step 1: Add `getDefaults` method to `artifactTypesAPI`**

In `frontend/src/api/client.ts`, find `artifactTypesAPI`. Add:
```typescript
  getDefaults: async (category: ArtifactCategory): Promise<{ name: string; prompt: string; llm: LLMProvider | null; model: string | null; category: ArtifactCategory }> => {
    const res = await proxyFetch(`/api/artifact-types/defaults/${category}`);
    if (!res.ok) throw new Error(`Failed to get defaults for ${category}`);
    return res.json();
  },
```

Also extend `create` / `update` signatures to accept `model: string | null` alongside existing fields.

- [ ] **Step 2: Rewrite `ArtifactTypeCard.tsx`**

Open `frontend/src/components/ArtifactTypeCard.tsx`. The file likely has three sections: header (name + badge), prompt textarea, and save/edit controls. Make these changes:

**2a. Import constants:**
```tsx
import { MODEL_RECOMMENDATIONS, PROVIDER_LABELS } from "@/constants/models";
```

**2b. Replace the LLM radio/select with a Provider dropdown + conditional Model dropdown.** Find the existing LLM control (it's probably a `<select>` with options for groq/claude/openai) and replace with:

```tsx
{editing && (
  <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 12 }}>
    <div>
      <label style={{ fontSize: 11, color: "#5e6c84", display: "block", marginBottom: 4 }}>Provider</label>
      <select
        value={draft.llm ?? "inherit"}
        onChange={(e) => {
          const val = e.target.value;
          const next: Partial<ArtifactType> = {
            llm: val === "inherit" ? null : (val as LLMProvider),
          };
          if (val !== "openrouter") next.model = null;
          setDraft((d) => ({ ...d, ...next }));
        }}
        style={{ fontSize: 12, border: "1px solid #dfe1e6", borderRadius: 4, padding: "5px 8px", fontFamily: "inherit" }}
      >
        <option value="inherit">{PROVIDER_LABELS.inherit}</option>
        <option value="groq">{PROVIDER_LABELS.groq}</option>
        <option value="deepseek">{PROVIDER_LABELS.deepseek}</option>
        <option value="claude">{PROVIDER_LABELS.claude}</option>
        <option value="openai">{PROVIDER_LABELS.openai}</option>
        <option value="openrouter">{PROVIDER_LABELS.openrouter}</option>
      </select>
    </div>
    {draft.llm === "openrouter" && (
      <div>
        <label style={{ fontSize: 11, color: "#5e6c84", display: "block", marginBottom: 4 }}>Model (OpenRouter)</label>
        <select
          value={MODEL_RECOMMENDATIONS[type.category]?.some((m) => m.slug === draft.model) ? draft.model! : "custom"}
          onChange={(e) => {
            if (e.target.value === "custom") return;
            setDraft((d) => ({ ...d, model: e.target.value }));
          }}
          style={{ fontSize: 12, border: "1px solid #dfe1e6", borderRadius: 4, padding: "5px 8px", fontFamily: "inherit", width: "100%" }}
        >
          {(MODEL_RECOMMENDATIONS[type.category] ?? []).map((m) => (
            <option key={m.slug} value={m.slug}>
              {m.slug} — {m.label}{m.priceHint ? ` · ${m.priceHint}` : ""}
            </option>
          ))}
          <option value="custom">Custom…</option>
        </select>
        <input
          type="text"
          placeholder="Custom OpenRouter slug (e.g. mistralai/mistral-large)"
          value={draft.model ?? ""}
          onChange={(e) => setDraft((d) => ({ ...d, model: e.target.value }))}
          style={{ fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "4px 6px", fontFamily: "inherit", width: "100%", marginTop: 4 }}
        />
      </div>
    )}
  </div>
)}
```

**2c. Make the prompt textarea expandable.** Wrap the existing `<textarea>` with a container that has an expand button:
```tsx
<div style={{ position: "relative" }}>
  <textarea
    value={draft.prompt}
    onChange={(e) => setDraft((d) => ({ ...d, prompt: e.target.value }))}
    rows={expanded ? 25 : 6}
    style={{
      width: "100%", fontSize: 12, fontFamily: "ui-monospace, Menlo, monospace",
      color: "#172b4d", border: "1px solid #dfe1e6", borderRadius: 4,
      padding: "8px 10px", resize: "vertical", boxSizing: "border-box",
      minHeight: expanded ? 500 : 120,
    }}
  />
  <button
    type="button"
    onClick={() => setExpanded((v) => !v)}
    title={expanded ? "Collapse" : "Expand for easier editing"}
    style={{ position: "absolute", top: 6, right: 6, background: "rgba(255,255,255,.9)", border: "1px solid #dfe1e6", borderRadius: 3, padding: "2px 6px", fontSize: 10, cursor: "pointer" }}
  >
    {expanded ? "⤡ Collapse" : "⤢ Expand"}
  </button>
</div>
```

Add `const [expanded, setExpanded] = useState(false);` at the top of the component.

**2d. Add "Show runtime context" disclosure** below the textarea:
```tsx
<details style={{ marginTop: 8, fontSize: 11 }}>
  <summary style={{ cursor: "pointer", color: "#5e6c84" }}>
    Show runtime context (appended automatically at extraction time)
  </summary>
  <pre style={{ fontSize: 10, background: "#fafbfc", padding: 8, borderRadius: 4, color: "#5e6c84", whiteSpace: "pre-wrap", marginTop: 6 }}>
{`Project context: {projects.context}

Existing project topic names (vocabulary alignment):
  - {name 1}
  - {name 2}
  ...

Response schema: { ... fixed JSON shape ... }

Transcript:
{full transcript}`}
  </pre>
  <p style={{ fontSize: 10, color: "#97a0af", marginTop: 4 }}>
    These blocks are added automatically by the extraction pipeline — they cannot be edited here.
  </p>
</details>
```

**2e. Add "Reset to default" button** in the card's action row (same row as Save / Cancel):
```tsx
<button
  type="button"
  onClick={async () => {
    if (!confirm("Overwrite your current prompt and settings with the latest default? Your edits will be lost.")) return;
    const def = await artifactTypesAPI.getDefaults(type.category);
    setDraft((d) => ({ ...d, prompt: def.prompt, llm: def.llm, model: def.model }));
  }}
  style={{ fontSize: 11, color: "#5e6c84", background: "none", border: "1px solid #dfe1e6", borderRadius: 4, padding: "4px 10px", cursor: "pointer", marginRight: "auto" }}
>
  ⟲ Reset to default
</button>
```

- [ ] **Step 3: Type-check + lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: 0 errors.

- [ ] **Step 4: Manual smoke test**

Dev server running. Open a project's `/projects/{id}/artifacts` page. Expand an artifact type card.
- Provider dropdown shows 6 options including "OpenRouter ⭐"
- Selecting OpenRouter reveals Model dropdown with the curated list + "Custom…"
- Expand button grows the textarea to ~500px
- "Show runtime context" discloses a preview
- "Reset to default" overwrites with the canonical default

- [ ] **Step 5: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-11] frontend: ArtifactTypeCard — provider/model pickers, expandable prompt editor, runtime-context disclosure, reset-to-default"
```

---

## Task 13: Project settings — `default_llm` + `default_model` controls

**Files:**
- Modify: `frontend/app/projects/[id]/artifacts/page.tsx` (or wherever project default LLM is exposed)
- Modify: `frontend/src/api/client.ts` (`projectsAPI.updateDefaultLlm` → extend to pass `default_model`)
- Modify: `frontend/src/components/ArtifactSelector.tsx`

- [ ] **Step 1: Extend `projectsAPI.updateDefaultLlm` to accept model**

In `frontend/src/api/client.ts`, update the method:
```typescript
  updateDefaultLlm: async (projectId: string, llm: LLMProvider, model: string | null = null): Promise<Project> => {
    const res = await proxyFetch(`/api/projects/${projectId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ default_llm: llm, default_model: model }),
    });
    if (!res.ok) throw new Error("Failed to update project default LLM");
    return res.json();
  },
```

- [ ] **Step 2: Update the project-level Provider/Model control**

Find the component where the project's `default_llm` is shown (per build-log this is `frontend/app/projects/[id]/artifacts/page.tsx` around the "apply to all" area). Replace the current dropdown with the same two-control pattern used on `ArtifactTypeCard`:

```tsx
<div style={{ display: "flex", gap: 8, alignItems: "end" }}>
  <div>
    <label style={{ fontSize: 11, color: "#5e6c84", display: "block" }}>Project default provider</label>
    <select
      value={project.default_llm}
      onChange={(e) => {
        const v = e.target.value as LLMProvider;
        projectsAPI.updateDefaultLlm(project.id, v, v === "openrouter" ? project.default_model : null)
          .then(setProject);
      }}
      style={{ fontSize: 12, border: "1px solid #dfe1e6", borderRadius: 4, padding: "5px 8px" }}
    >
      <option value="groq">Groq</option>
      <option value="deepseek">DeepSeek</option>
      <option value="claude">Claude</option>
      <option value="openai">OpenAI</option>
      <option value="openrouter">OpenRouter ⭐</option>
    </select>
  </div>
  {project.default_llm === "openrouter" && (
    <div style={{ flex: 1 }}>
      <label style={{ fontSize: 11, color: "#5e6c84", display: "block" }}>Default model</label>
      <input
        type="text"
        value={project.default_model ?? ""}
        onChange={(e) => setProject({ ...project, default_model: e.target.value })}
        onBlur={() => projectsAPI.updateDefaultLlm(project.id, "openrouter", project.default_model).then(setProject)}
        placeholder="anthropic/claude-sonnet-4.6"
        style={{ fontSize: 12, border: "1px solid #dfe1e6", borderRadius: 4, padding: "5px 8px", fontFamily: "ui-monospace, Menlo, monospace", width: "100%" }}
      />
    </div>
  )}
</div>
```

- [ ] **Step 3: `ArtifactSelector.tsx` — show OpenRouter label where LLM is summarised**

In `frontend/src/components/ArtifactSelector.tsx`, find the LLM label rendering. Update labels to include openrouter:
```tsx
const LLM_LABELS: Record<LLMProvider, string> = {
  groq:       "Groq",
  deepseek:   "DeepSeek",
  claude:     "Claude",
  openai:     "OpenAI",
  openrouter: "OpenRouter",
};
```

Where a specific model is known (artifact type has `model` set and `llm === "openrouter"`), append it:
```tsx
<span>{LLM_LABELS[type.llm ?? project.default_llm]}{type.llm === "openrouter" && type.model ? ` · ${type.model}` : ""}</span>
```

- [ ] **Step 4: Type-check + lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: 0 errors.

- [ ] **Step 5: Manual smoke test**

Dev server. Visit `/projects/{id}/artifacts`. Change project default provider to OpenRouter. Model slug field appears. Enter `anthropic/claude-sonnet-4.6`. Refresh page — selection persists. Trigger an extraction on a test call — verify backend logs show `🤖 [OpenRouter/anthropic/claude-sonnet-4.6] Extracting topics`.

- [ ] **Step 6: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-11] frontend: project-level default_model control + ArtifactSelector label update"
```

---

## Task 14: End-to-end smoke test + close story

**Files:**
- Modify: `docs/project/config/build-log.md`
- Modify: `docs/project/config/epics/ACTIVE.md`
- Modify: `docs/project/config/codebase.md`

- [ ] **Step 1: Full backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: all tests PASS. If any existing tests fail because of new required Pydantic fields, fix by adding the new fields to test fixtures (with defaults).

- [ ] **Step 2: Frontend type-check + lint**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: 0 errors.

- [ ] **Step 3: Live smoke — full extraction flow**

- Set `OPENROUTER_API_KEY` in `backend/.env`.
- Start backend: `cd backend && uvicorn backend.main:app --reload`.
- Start frontend: `cd frontend && npm run dev`.
- Open a test project. Seed a new test call with a real transcript (use one of your RAMMMM project calls).
- On Call Topics stage, click "Extract this call's topics".
- Backend log should show: `🤖 [OpenRouter/anthropic/claude-sonnet-4.6] Extracting topics`.
- Topics render with: 3 sections (Decisions / Actions / Open questions) when populated, importance dot colour, parked chip for any parked items.
- Hover importance dot → tooltip shows `rationale`.
- Click ✎ → textareas appear for summary + each section + dropdowns.
- Click "Save & Continue" → aggregates correctly, advances stage.
- Run on 2-3 representative transcripts and spot-check: is fragmentation reduced? Are summaries richer? Are decisions/actions/open-questions correctly separated?

- [ ] **Step 4: Update build-log.md**

Append new section at the top of `docs/project/config/build-log.md`:
```markdown
### 2026-04-22 — EPIC-11: Call Topics Extraction Overhaul

**Backend — prompt lifecycle:**
- New `backend/prompts/` package with single-source-of-truth constants for all 4 workflow prompts (`call_topics`, `project_topics`, `merge_verification`, `not_discussed_check`) + `artifacts` bundle.
- `CALL_TOPICS_DEFAULT_PROMPT` — new multi-section prompt (ROLE + RUBRIC + ANCHORS + FEW-SHOT + PROCESS) encoding the 3-of-4 rubric, splits/filters, parked items, and 3 anchor types.
- Migration script `backend/scripts/migrate_call_topics_prompt.py` — replaces old-default prompts with new; preserves customized rows.
- `GET /api/artifact-types/defaults/{category}` endpoint powers "Reset to default" button.

**Backend — schema:**
- Migration 019: `topic_updates` gets `open_questions JSONB`, `is_parked BOOL`, `importance TEXT`, `rationale TEXT`. `artifact_types.model TEXT`, `projects.default_model TEXT`.
- `TopicIn` / `TopicOut` Pydantic models carry the 4 new fields with sensible defaults.
- `_TOPIC_SCHEMA` describes the full new payload shape.

**Backend — OpenRouter:**
- 5th LLM provider via `AsyncOpenAI` + `https://openrouter.ai/api/v1`.
- `generate_artifact(llm, *, model=None)` and `call_llm_raw(llm, *, model=None)` — model required when `llm='openrouter'`.
- `artifact_types.model` + `projects.default_model` propagate through create/update APIs and extract/artifact call sites.
- New projects seed `call_topics`, `merge_verification`, `not_discussed_check`, and all artifact types with OpenRouter + recommended model.

**Frontend — tile rewrite:**
- `CallTopicsStage.TopicRow` — 3 colour-coded sections (Decisions=grey, Actions=amber, Open questions=blue), importance dot + rationale tooltip, parked variant (⏸ chip, muted border, Un-park button), expand-to-edit affordances inline.
- `SectionBlock` reusable component used by all three anchor sections.
- Ripple: `TopicEditor`, `TopicsDashboard`, `TopicsPanel`, `TopicEvidenceDrawer` all render `open_questions` + `is_parked` where relevant.

**Frontend — model picker + prompt editor:**
- `MODEL_RECOMMENDATIONS` curated per category.
- `ArtifactTypeCard` — Provider dropdown (6 options), conditional Model dropdown, Custom slug input, expandable textarea (~500px), "Show runtime context" disclosure, "Reset to default" button.
- Project settings page — Provider + Model controls for `default_llm` / `default_model`.

**Commits:** [EPIC-11] across 13 commits.
**Tests:** 10+ new backend tests; frontend validated via `tsc --noEmit` + lint + manual smoke.
**Migration:** 019 (manual, via Supabase dashboard) + migration script for existing prompt rows.
```

- [ ] **Step 5: Update ACTIVE.md + codebase.md**

In `docs/project/config/epics/ACTIVE.md`:
- Change "Next: TBD" to point at EPIC-11 (create `docs/project/config/epics/epic-11/` directory if convention requires a story file).
- Add row to the completed list: `[x] EPIC-11 / Call Topics Extraction Overhaul — 2026-04-22`.

In `docs/project/config/codebase.md`, append entries for the new modules:
```markdown
- `backend/prompts/` — single-source-of-truth workflow prompt constants (call_topics, project_topics, merge_verification, not_discussed_check, artifacts).
- `backend/scripts/migrate_call_topics_prompt.py` — one-shot migration; safely replaces old-default call_topics prompts.
- `frontend/src/constants/models.ts` — `MODEL_RECOMMENDATIONS` per category + `PROVIDER_LABELS`.
```

- [ ] **Step 6: Commit closeout**

```bash
python3 scripts/git_ops.py commit "[EPIC-11] docs: close epic — build-log, ACTIVE, codebase updated"
```

---

## Self-review

**Spec coverage check:**

- §4.1 Rubric → Task 2 (encoded in prompt constant).
- §4.2 Prompt structure (6 blocks) → Task 2 constant + Task 3 injects CONTEXT runtime.
- §4.3 Schema (4 new fields) → Task 1 (DB), Task 3 (Pydantic + `_TOPIC_SCHEMA`), Task 9 (frontend types).
- §4.4 OpenRouter — provider, dispatch, curated list, defaults, env → Task 7 (llm_service), Task 8 (APIs), Task 9 (constants), Task 12 (card picker), Task 13 (project).
- §4.5 UI tile rewrite → Task 10 + Task 11.
- §4.6 Prompt deployment & lifecycle → Task 2 (constant), Task 4 (migration), Task 5 (reset endpoint), Task 6 (parallel modules), Task 12 (UI reset button + runtime disclosure + expandable textarea).
- §5 implementation steps 1–25 → all covered across Tasks 1–13.
- §6 Tests → Tasks 2, 3, 4, 5, 6, 7, 8.
- §7 Open questions (all 5 resolved) → reflected in implementation choices (e.g. Q2 → importance field, Q3 → tooltip, Q4 → all categories seeded with OpenRouter).

**Placeholder scan:** no "TBD" / "TODO" / "implement later". All code steps have complete code blocks.

**Type consistency:** `importance: "high"|"medium"|"low"` used consistently across Pydantic `Literal`, TypeScript union, and prompt schema. `follow_up_items` is the same field name in backend, frontend, and prompt (actions). `model: string | null` consistent across backend Pydantic and TypeScript types. `default_model` consistent on projects.

**Migration safety:** DB migration is `ADD COLUMN IF NOT EXISTS` with defaults — additive only, no data loss. Prompt migration preserves customized rows by exact-string match of `OLD_DEFAULT_PROMPT_STRING`.

---

## Execution handoff

Plan saved to [`docs/project/config/2026-04-22-call-topics-extraction-overhaul-plan.md`](./2026-04-22-call-topics-extraction-overhaul-plan.md).

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints.

Which approach?
