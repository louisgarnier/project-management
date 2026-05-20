# Pipeline Reorder: Topics → Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorder the call pipeline from Transcript → Artifacts → Topics → Done to Transcript → **Topics** → **Artifacts** → Done, and inject extracted topics as context into artifact generation so every artifact (summary, next steps, email) is grounded in both the transcript and the structured topics.

**Architecture:** Three coordinated changes: (1) flip `STAGE_ORDER` in the backend and fix the two hardcoded stage transitions (`submit_transcript` → "topics", `validate_call` → "artifacts"); (2) add an optional `topics` parameter to `generate_artifact` in `llm_service` and fetch those topics in the streaming SSE endpoint before calling the LLM; (3) update the frontend STAGES array, stage rendering order, button labels, and default artifact prompts. No DB migrations needed — only code changes.

**Tech Stack:** FastAPI + Pydantic v2, Python unittest.mock, Next.js 15 App Router, TypeScript, inline styles.

---

## File Map

| Action | File | What changes |
|---|---|---|
| Modify | `backend/routers/calls.py` | `STAGE_ORDER` flip; `submit_transcript` hardcoded stage "artifacts" → "topics" |
| Modify | `backend/services/topics_service.py` | `validate_call` hardcoded stage "done" → "artifacts" |
| Modify | `backend/services/llm_service.py` | `generate_artifact` gains optional `topics: list[dict] \| None` param; context block updated |
| Modify | `backend/routers/artifacts.py` | `stream_artifacts`: fetch call's topics before generating; pass to `generate_artifact` |
| Modify | `backend/routers/artifact_types.py` | `DEFAULT_ARTIFACT_TYPES` prompts updated to reference topics |
| Modify | `backend/tests/test_calls.py` | `STAGE_ORDER` assertions, `submit_transcript` stage assertion |
| Modify | `backend/tests/test_topics.py` | `validate_call` now advances to "artifacts" not "done" |
| Modify | `backend/tests/test_artifacts.py` | `generate_artifact` call updated to pass `topics=` param |
| Modify | `frontend/src/components/KanbanBoard.tsx` | `STAGES` and `STAGE_ORDER` arrays reordered; lock logic updated |
| Modify | `frontend/app/projects/[id]/calls/[call_id]/page.tsx` | Stage rendering order flipped; topics before artifacts |
| Modify | `frontend/src/components/ArtifactsStage.tsx` | Button label "Proceed to Topics →" → "Complete Call →" |
| Modify | `frontend/src/components/TopicsStage.tsx` | Button label "Validate & Complete Call →" → "Save Topics & Proceed to Artifacts →" |

---

## Task 1: Flip STAGE_ORDER and fix hardcoded stage transitions

**Files:**
- Modify: `backend/routers/calls.py`
- Modify: `backend/services/topics_service.py`
- Test: `backend/tests/test_calls.py`
- Test: `backend/tests/test_topics.py`

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_calls.py`, find `test_patch_stage_valid_transition` — it mocks `kanban_stage: "transcript"` and expects the result to be `"artifacts"`. Change the expected next stage to `"topics"`.

Also find (or add) a test for `submit_transcript` stage result. Add this test:

```python
def test_submit_transcript_advances_to_topics():
    mc = _mock_client()
    # select: call exists at transcript stage
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[{"kanban_stage": "transcript"}])
    )
    # update: returns call at topics stage
    mc.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[{**MOCK_CALL, "kanban_stage": "topics", "transcript": "Hello world"}])
    )
    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.post(
            f"/api/calls/{CALL_ID}/transcript",
            json={"transcript": "Hello world"},
        )
    assert r.status_code == 200
    assert r.json()["kanban_stage"] == "topics"
```

In `backend/tests/test_topics.py`, find any test that checks `validate_call` sets `kanban_stage` to `"done"`. If none exists, add:

```python
@patch("backend.services.topics_service.get_client")
def test_validate_call_advances_to_artifacts(mock_gc):
    """validate_call must advance the call to 'artifacts', not 'done'."""
    import asyncio
    from backend.services.topics_service import validate_call

    mock_db = MagicMock()
    # topic_updates exist for this call
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"topic_id": "topic-1"}
    ]
    # calls table: project_id lookup
    call_row_mock = MagicMock()
    call_row_mock.data = [{"project_id": "proj-1"}]
    # _get_previous_topics returns empty (no open topics to acknowledge)
    topics_mock = MagicMock()
    topics_mock.data = []

    def table_side(name):
        m = MagicMock()
        if name == "topic_updates":
            m.select.return_value.eq.return_value.execute.return_value.data = [{"topic_id": "topic-1"}]
        elif name == "calls":
            m.select.return_value.eq.return_value.execute.return_value.data = [{"project_id": "proj-1"}]
            m.update.return_value.eq.return_value.execute.return_value.data = [{"kanban_stage": "artifacts"}]
        elif name == "topics":
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        return m

    mock_db.table.side_effect = table_side
    mock_gc.return_value = mock_db

    result = asyncio.run(validate_call("call-1"))
    assert result["kanban_stage"] == "artifacts"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 -m pytest backend/tests/test_calls.py::test_submit_transcript_advances_to_topics backend/tests/test_topics.py::test_validate_call_advances_to_artifacts -v
```

Expected: FAIL — current code still produces "artifacts" and "done" respectively.

- [ ] **Step 3: Flip STAGE_ORDER in `backend/routers/calls.py`**

Find line 11:
```python
STAGE_ORDER = ["transcript", "artifacts", "topics", "done"]
```

Replace with:
```python
STAGE_ORDER = ["transcript", "topics", "artifacts", "done"]
```

Find the `submit_transcript` function. It contains:
```python
update_data: dict = {"transcript": payload.transcript, "kanban_stage": "artifacts"}
```

Replace with:
```python
update_data: dict = {"transcript": payload.transcript, "kanban_stage": "topics"}
```

- [ ] **Step 4: Fix `validate_call` in `backend/services/topics_service.py`**

Find in `validate_call` (around line 353):
```python
    result = (
        db.table("calls")
        .update({"kanban_stage": "done"})
        .eq("id", call_id)
        .execute()
        .data
    )
    logger.info(f"✅ [Topics] Call {call_id} validated → done")
    return result[0]
```

Replace with:
```python
    result = (
        db.table("calls")
        .update({"kanban_stage": "artifacts"})
        .eq("id", call_id)
        .execute()
        .data
    )
    logger.info(f"✅ [Topics] Call {call_id} validated → artifacts")
    return result[0]
```

- [ ] **Step 5: Update the existing stage transition test**

In `backend/tests/test_calls.py`, update `test_patch_stage_valid_transition`:

```python
def test_patch_stage_valid_transition():
    mc = _mock_client()
    # select current stage
    mc.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[{"kanban_stage": "transcript"}])
    )
    # update returns updated call
    mc.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        MagicMock(data=[{**MOCK_CALL, "kanban_stage": "topics"}])
    )
    with patch("backend.routers.calls.get_client", return_value=mc):
        r = client.patch(f"/api/calls/{CALL_ID}/stage")
    assert r.status_code == 200
    assert r.json()["kanban_stage"] == "topics"
```

- [ ] **Step 6: Run full test suite**

```bash
python3 -m pytest backend/tests/ -q 2>&1 | tail -10
```

Expected: all tests pass (or the same 1 pre-existing failure for `test_delete_default_type_forbidden`). Fix any new failures before continuing.

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] feat: reorder pipeline — transcript→topics→artifacts→done"
```

---

## Task 2: Inject topics context into artifact generation

**Files:**
- Modify: `backend/services/llm_service.py`
- Modify: `backend/routers/artifacts.py`
- Test: `backend/tests/test_artifacts.py`

### Context

`generate_artifact(prompt_used, transcript, llm)` currently builds the user message as:
```
Transcript:
[transcript]

Task:
[prompt]
```

After this task it will be:
```
Transcript:
[transcript]

Topics from this call:
[JSON array of topic objects — name, status, owner, sentiment, summary, follow_up_items, decisions]

Task:
[prompt]
```

The `topics` parameter is optional so existing code paths and tests that don't pass it still work.

In `stream_artifacts`, before the `gen_one` coroutines are dispatched, fetch the call's topics by joining `topic_updates` for this call with the `topics` table. Pass that list to `generate_artifact`.

The topics fetch: query `topic_updates` where `call_id = call_id`, then for each row join the `topics` row to get `name`. Shape each record into:
```python
{
    "name": topic_name,
    "status": update["status"],
    "owner": update["owner"],
    "sentiment": update["sentiment"],
    "summary": update["summary"],
    "follow_up_items": update["follow_up_items"],
    "decisions": update["decisions"],
}
```

- [ ] **Step 1: Write the failing test for `generate_artifact` with topics**

In `backend/tests/test_artifacts.py`, add:

```python
@pytest.mark.asyncio
async def test_generate_artifact_includes_topics_in_prompt():
    """generate_artifact must include topics JSON in the user message when topics are provided."""
    from backend.services.llm_service import generate_artifact
    from unittest.mock import AsyncMock, patch, MagicMock

    topics = [
        {
            "name": "Pricing",
            "status": "open",
            "owner": "Client",
            "sentiment": "concern",
            "summary": "Client pushed back on annual plan.",
            "follow_up_items": ["Send monthly breakdown"],
            "decisions": [],
        }
    ]

    captured_messages = {}

    async def fake_create(**kwargs):
        captured_messages["messages"] = kwargs.get("messages", [])
        m = MagicMock()
        m.content = [MagicMock(text="result")]
        m.usage = MagicMock(input_tokens=10, output_tokens=5)
        return m

    fake_client = MagicMock()
    fake_client.messages.create = fake_create

    with patch("backend.services.llm_service.anthropic.AsyncAnthropic", return_value=fake_client):
        await generate_artifact("Write a summary.", "The call transcript.", "claude", topics=topics)

    user_content = captured_messages["messages"][0]["content"]
    assert "Pricing" in user_content
    assert "Topics from this call" in user_content
    assert "Write a summary." in user_content
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 -m pytest "backend/tests/test_artifacts.py::test_generate_artifact_includes_topics_in_prompt" -v
```

Expected: FAIL — `generate_artifact` does not currently accept a `topics` keyword argument.

- [ ] **Step 3: Update `generate_artifact` in `backend/services/llm_service.py`**

Find the function signature:
```python
async def generate_artifact(prompt_used: str, transcript: str, llm: str) -> str:
```

Replace the full function body with:

```python
async def generate_artifact(
    prompt_used: str,
    transcript: str,
    llm: str,
    topics: list[dict] | None = None,
) -> str:
    """
    Generate an artifact using the specified LLM provider.
    llm must be one of: "groq", "deepseek", "claude", "openai".
    If topics are provided, they are injected between transcript and task prompt.
    Retries up to 3 times with exponential backoff on rate-limit errors.
    """
    import json as _json

    topics_block = ""
    if topics:
        topics_block = (
            f"\n\nTopics from this call:\n{_json.dumps(topics, indent=2)}"
        )

    user_message = (
        f"Transcript:\n{transcript}"
        f"{topics_block}"
        f"\n\nTask:\n{prompt_used}"
    )

    if llm == "claude":
        return await _generate_claude(user_message)
    elif llm == "groq":
        return await _generate_openai_compat(
            user_message,
            api_key=os.environ.get("GROQ_API_KEY", ""),
            base_url="https://api.groq.com/openai/v1",
            model="llama-3.3-70b-versatile",
            provider="Groq",
        )
    elif llm == "deepseek":
        return await _generate_openai_compat(
            user_message,
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            provider="DeepSeek",
        )
    elif llm == "openai":
        return await _generate_openai_compat(
            user_message,
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            base_url=None,
            model="gpt-4o-mini",
            provider="OpenAI",
        )
    else:
        raise ValueError(f"Unknown LLM provider: {llm!r}. Must be 'groq', 'deepseek', 'claude', or 'openai'.")
```

Now update `_generate_claude` and `_generate_openai_compat` to accept a pre-built `user_message` string instead of constructing it internally. Find `_generate_claude`:

```python
async def _generate_claude(prompt_used: str, transcript: str) -> str:
    client = anthropic.AsyncAnthropic()
    user_message = f"Transcript:\n{transcript}\n\nTask:\n{prompt_used}"
```

Replace signature + message line:

```python
async def _generate_claude(user_message: str) -> str:
    client = anthropic.AsyncAnthropic()
```

Find `_generate_openai_compat`:

```python
async def _generate_openai_compat(
    prompt_used: str,
    transcript: str,
    api_key: str,
    base_url: str | None,
    model: str,
    provider: str,
) -> str:
    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = AsyncOpenAI(**kwargs)
    user_message = f"Transcript:\n{transcript}\n\nTask:\n{prompt_used}"
```

Replace with:

```python
async def _generate_openai_compat(
    user_message: str,
    api_key: str,
    base_url: str | None,
    model: str,
    provider: str,
) -> str:
    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    client = AsyncOpenAI(**kwargs)
```

- [ ] **Step 4: Run the new test to verify it passes**

```bash
python3 -m pytest "backend/tests/test_artifacts.py::test_generate_artifact_includes_topics_in_prompt" -v
```

Expected: PASS.

- [ ] **Step 5: Fetch topics in `stream_artifacts` and pass to `generate_artifact`**

In `backend/routers/artifacts.py`, find `stream_artifacts`. After fetching `transcript` (around line 151), add a topics fetch:

```python
    # Fetch topics for this call to inject as context
    topics_result = (
        supabase.table("topic_updates")
        .select("summary, follow_up_items, decisions, status, owner, sentiment, topic_id")
        .eq("call_id", call_id)
        .execute()
    )
    topic_ids = [r["topic_id"] for r in topics_result.data]
    topic_names: dict[str, str] = {}
    if topic_ids:
        names_result = (
            supabase.table("topics")
            .select("id, name")
            .in_("id", topic_ids)
            .execute()
        )
        topic_names = {r["id"]: r["name"] for r in names_result.data}

    call_topics = [
        {
            "name": topic_names.get(r["topic_id"], "Unknown"),
            "status": r.get("status", "open"),
            "owner": r.get("owner", "Us"),
            "sentiment": r.get("sentiment", "neutral"),
            "summary": r.get("summary", ""),
            "follow_up_items": r.get("follow_up_items") or [],
            "decisions": r.get("decisions") or [],
        }
        for r in topics_result.data
    ] or None
```

Then update the `gen_one` call inside `event_stream`:

Find:
```python
                content = await generate_artifact(prompt_used, transcript, artifact["mode"])
```

Replace:
```python
                content = await generate_artifact(prompt_used, transcript, artifact["mode"], topics=call_topics)
```

- [ ] **Step 6: Run full test suite**

```bash
python3 -m pytest backend/tests/ -q 2>&1 | tail -10
```

Expected: all existing tests pass (topics param is optional so no regressions). Fix any failures before continuing.

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] feat: inject topics context into artifact generation"
```

---

## Task 3: Update default artifact prompts to reference topics

**Files:**
- Modify: `backend/routers/artifact_types.py`

### Context

The default prompts currently say "from this call" without referencing topics. Since topics are now always injected, updating the prompts to explicitly reference them makes the output dramatically better. The LLM will be told to use both layers.

No tests needed — prompt content is not unit-tested. This is a content-only change.

- [ ] **Step 1: Update `DEFAULT_ARTIFACT_TYPES` in `backend/routers/artifact_types.py`**

Replace the entire `DEFAULT_ARTIFACT_TYPES` list:

```python
DEFAULT_ARTIFACT_TYPES: list[dict] = [
    {
        "name": "Executive Summary",
        "prompt": (
            "Write a concise executive summary of this call in 3–5 bullet points. "
            "Use the Topics section to structure your summary around the key themes discussed. "
            "For each bullet: state the topic, what was decided or discussed, and its current status (open/resolved). "
            "Focus on decisions made, key outcomes, and overall direction."
        ),
        "is_default": True,
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
        "is_default": True,
    },
    {
        "name": "Questions for Stakeholders",
        "prompt": (
            "List all open questions that remain unanswered after this call. "
            "Group them by topic (use the Topics section). "
            "For each question: state the topic, the question, and why it is blocking progress. "
            "Prioritise questions from topics that are open or in_progress."
        ),
        "is_default": True,
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
        "is_default": True,
    },
    {
        "name": "Email Follow-up (pre-next-call)",
        "prompt": (
            "Write a short follow-up email to send before the next call. "
            "For each open topic (from the Topics section), summarise: what was agreed, "
            "what each party should have completed before the next session, and what remains open. "
            "End with a proposed agenda for the next call based on in_progress and open topics."
        ),
        "is_default": True,
    },
    {
        "name": "Next Call Meeting Invite Topics",
        "prompt": (
            "Generate a structured agenda for the next call. "
            "Base it on the Topics section: include all open and in_progress topics, "
            "ordered by priority (concern sentiment first, then by calls_open descending). "
            "For each agenda item: topic name, brief context (1 sentence), and the specific question or decision needed."
        ),
        "is_default": True,
    },
]
```

- [ ] **Step 2: Commit**

```bash
python3 scripts/git_ops.py commit "[EPIC-6] feat: update default artifact prompts to reference topics context"
```

---

## Task 4: Frontend — reorder stages, update labels

**Files:**
- Modify: `frontend/src/components/KanbanBoard.tsx`
- Modify: `frontend/app/projects/[id]/calls/[call_id]/page.tsx`
- Modify: `frontend/src/components/ArtifactsStage.tsx`
- Modify: `frontend/src/components/TopicsStage.tsx`

- [ ] **Step 1: Reorder stages in `frontend/src/components/KanbanBoard.tsx`**

Find:
```typescript
const STAGES: { key: KanbanStage; label: string }[] = [
  { key: "transcript", label: "Transcript" },
  { key: "artifacts",  label: "Artifacts"  },
  { key: "topics",     label: "Topics"     },
  { key: "done",       label: "Done"       },
];

const STAGE_ORDER: KanbanStage[] = ["transcript", "artifacts", "topics", "done"];
```

Replace with:
```typescript
const STAGES: { key: KanbanStage; label: string }[] = [
  { key: "transcript", label: "Transcript" },
  { key: "topics",     label: "Topics"     },
  { key: "artifacts",  label: "Artifacts"  },
  { key: "done",       label: "Done"       },
];

const STAGE_ORDER: KanbanStage[] = ["transcript", "topics", "artifacts", "done"];
```

Find the lock logic (around line 62):
```typescript
  if (stageKey === "topics" && !prevCallDone) {
```

The lock was protecting topics from being accessed until the previous call was done. In the new order, artifacts should be locked instead. Replace:
```typescript
  if (stageKey === "artifacts" && !prevCallDone) {
```

- [ ] **Step 2: Reorder stage rendering in `frontend/app/projects/[id]/calls/[call_id]/page.tsx`**

Find the stage content section. It currently renders:
1. `transcript` stage
2. `artifacts` stage
3. `topics` stage
4. `done` stage

Swap `artifacts` and `topics` blocks so the order matches the new pipeline. The topics block:
```tsx
        {call.kanban_stage === "topics" && (
          <>
            <TopicsStage call={call} onAdvance={loadCall} />
            <ArtifactsStage call={call} onAdvance={loadCall} hideAdvance />
            {call.transcript && (
              <TranscriptPanel call={call} onSaved={(updated) => setCall(updated)} />
            )}
            <ContextFiles call={call} readonly />
          </>
        )}
```

becomes:
```tsx
        {call.kanban_stage === "topics" && (
          <>
            <TopicsStage call={call} onAdvance={loadCall} />
            {call.transcript && (
              <TranscriptPanel call={call} onSaved={(updated) => setCall(updated)} />
            )}
            <ContextFiles call={call} readonly />
          </>
        )}
```

(Remove the embedded `ArtifactsStage` — it no longer makes sense to show artifacts editing during topics, since artifacts come after topics now.)

The artifacts block:
```tsx
        {call.kanban_stage === "artifacts" && (
          <>
            <ArtifactsStage call={call} onAdvance={loadCall} />
            {call.transcript && (
              <TranscriptPanel
                call={call}
                onSaved={(updated) => setCall(updated)}
              />
            )}
            <ContextFiles call={call} readonly />
            <div className="mt-4 text-right">
              <button
                onClick={() => setShowResetModal(true)}
                className="text-[11px] text-[#97a0af] hover:text-red-500 hover:underline"
              >
                ↩ Reset transcript
              </button>
            </div>
          </>
        )}
```

No change needed to the artifacts block content — it already shows `ArtifactsStage` with transcript below.

The full reordered stage content section should be:
```tsx
      <div className="flex-1 overflow-y-auto p-5">
        {call.kanban_stage === "transcript" && (
          <TranscriptStage call={call} onAdvance={loadCall} />
        )}
        {call.kanban_stage === "topics" && (
          <>
            <TopicsStage call={call} onAdvance={loadCall} />
            {call.transcript && (
              <TranscriptPanel call={call} onSaved={(updated) => setCall(updated)} />
            )}
            <ContextFiles call={call} readonly />
          </>
        )}
        {call.kanban_stage === "artifacts" && (
          <>
            <ArtifactsStage call={call} onAdvance={loadCall} />
            {call.transcript && (
              <TranscriptPanel
                call={call}
                onSaved={(updated) => setCall(updated)}
              />
            )}
            <ContextFiles call={call} readonly />
            <div className="mt-4 text-right">
              <button
                onClick={() => setShowResetModal(true)}
                className="text-[11px] text-[#97a0af] hover:text-red-500 hover:underline"
              >
                ↩ Reset transcript
              </button>
            </div>
          </>
        )}
        {call.kanban_stage === "done" && (
          <>
            <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8,
              padding: "12px 16px", marginBottom: 16, fontSize: 13, color: "#15803d", fontWeight: 600 }}>
              ✓ Call complete — all topics validated and artifacts saved.
            </div>
            <TopicsPanel callId={callId} projectId={projectId} defaultOpen />
            <ArtifactsPanel callId={callId} projectId={projectId} />
            {call.transcript && (
              <TranscriptPanel call={call} onSaved={(updated) => setCall(updated)} />
            )}
            <ContextFiles call={call} readonly />
          </>
        )}
      </div>
```

- [ ] **Step 3: Update button labels**

In `frontend/src/components/ArtifactsStage.tsx`, find:
```tsx
            {advancing ? "Advancing…" : "Proceed to Topics →"}
```
Replace with:
```tsx
            {advancing ? "Advancing…" : "Complete Call →"}
```

In `frontend/src/components/TopicsStage.tsx`, find:
```tsx
        {validating ? "Saving…" : "Validate & Complete Call →"}
```
Replace with:
```tsx
        {validating ? "Saving…" : "Save Topics & Proceed to Artifacts →"}
```

- [ ] **Step 4: Compile check**

```bash
cd "/Users/louisgarnier/Claude/Project management/frontend"
npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors. Fix any TypeScript errors before continuing.

- [ ] **Step 5: Commit**

```bash
cd "/Users/louisgarnier/Claude/Project management"
python3 scripts/git_ops.py commit "[EPIC-6] feat: frontend pipeline reorder — topics before artifacts, updated labels"
```

---

## Self-Review

**Spec coverage:**
- ✅ Stage order changed to Transcript → Topics → Artifacts → Done — Task 1
- ✅ `submit_transcript` advances to "topics" — Task 1
- ✅ `validate_call` advances to "artifacts" — Task 1
- ✅ `generate_artifact` accepts topics context — Task 2
- ✅ Topics fetched from DB before streaming artifacts — Task 2
- ✅ Default prompts reference topics — Task 3
- ✅ Kanban board columns reordered — Task 4
- ✅ Call detail page stage rendering reordered — Task 4
- ✅ Button labels updated — Task 4
- ✅ Lock logic: artifacts locked until previous call done (not topics) — Task 4

**Placeholder scan:** None found.

**Type consistency:**
- `generate_artifact(prompt_used, transcript, llm, topics=None)` — defined in Task 2 Step 3, called in Task 2 Step 5. `topics: list[dict] | None` matches both.
- `_generate_claude(user_message)` — redefined in Task 2 Step 3 to accept pre-built message. Called from `generate_artifact` in same task. Consistent.
- `_generate_openai_compat(user_message, api_key, base_url, model, provider)` — redefined in Task 2 Step 3. Called from `generate_artifact`. Consistent.
- `call_topics` variable in `stream_artifacts` — typed as `list[dict] | None`, matches `topics` param type. Consistent.
