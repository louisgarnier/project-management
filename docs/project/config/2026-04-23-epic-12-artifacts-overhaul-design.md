# EPIC-12 — Artifacts Overhaul — Design

**Date:** 2026-04-23
**Status:** Draft — pending user review
**Relates to:** [EPIC-11 design](./2026-04-22-call-topics-extraction-overhaul-design.md), [`ArtifactTypeCard.tsx`](../../../frontend/src/components/ArtifactTypeCard.tsx), [`routers/artifacts.py`](../../../backend/routers/artifacts.py), [`routers/artifact_types.py`](../../../backend/routers/artifact_types.py)

---

## 1. Problem

The artifact generation system has five tangled pain points:

- **Re-extraction waste.** Today every artifact is an LLM call. "Next Steps & Action Items" and "Questions for Stakeholders" re-extract content the user already reviewed on the Call Topics tiles — lossy, costly, potentially inconsistent ("Nick: run benchmark" vs *"Nick should run a benchmark"*).
- **Pre-populated bloat.** New projects auto-seed 6 artifact types. Projects that don't need emails or agendas still get them, forcing manual deletion.
- **`is_default` conflation.** The column conflates "system-owned, can't delete" with "auto-added to new projects". Splitting them unlocks a curated library.
- **Reset-to-default gap.** EPIC-11 added `GET /api/artifact-types/defaults/{category}` but only for workflow categories (`call_topics` etc.). Individual artifact types (Executive Summary, Next Steps…) have no per-name canonical, so the Reset button was UI-wrapped to only show on `call_topics` cards. The rest can't be reset.
- **Cost opacity.** Users have no visibility into per-artifact cost; a 6-artifact generation with Sonnet is ~$0.60 with no forewarning.

## 2. Goals

- **Three artifact kinds** — *Template* (deterministic, no LLM), *LLM* (prompt + structured topics), *Hybrid* (template scaffold + LLM prose wrapper) — each fits its job.
- **Curated library** of canonical artifact types, separated from "auto-seeded on project creation".
- **New projects seed a minimal 3** (Executive Summary, Next Steps, Questions for Stakeholders). Other library types are opt-in via "Add from library".
- **Reset-to-default works for every artifact type**, including kind conversion (existing LLM Next Steps → Template on reset).
- **Diff-vs-canonical indicator** shows when a user has edited a prompt from its library default.
- **Cost preview** surfaces per-artifact expected cost at config time.

## 3. Non-goals

- **No user-editable template logic.** Templates are Python renderers. Users who need custom behavior create a custom **LLM** artifact (existing mechanism). Deferred indefinitely; ship A.
- **No retroactive migration.** Existing projects' 6 types stay as-is until the user clicks Reset per type. No bulk migrate-all button.
- **No live pricing API.** Cost preview uses hardcoded per-1M-token rates from a frontend constant, refreshed manually when rates shift.
- **No versioned prompt history.** Out of scope for EPIC-12. Users have Reset if they want the canonical back.
- **No per-user or per-org library scoping.** Library is a single system-wide canonical registry in code.
- **No streaming for template artifacts.** Templates render synchronously (~ms); no SSE needed. Existing `/stream` endpoint keeps its shape — it just skips LLM for template artifacts.

## 4. Design

### 4.1 Artifact `kind` — three values

```
kind ∈ {'llm', 'template', 'hybrid'}
```

- **`llm`** — current behavior. Prompt + transcript (+ structured topics for project scope) → LLM call via `generate_artifact`. Output is the LLM response.
- **`template`** — zero LLM. A Python renderer function takes `list_call_topics(call_id)` (or `list_project_topics` for project scope) and returns markdown. Output is the renderer's return value.
- **`hybrid`** — template skeleton + LLM intro/closing. Renderer produces the structural bulk (topic list, statuses); two short LLM calls produce intro and closing prose. Output is `intro + template_body + closing` concatenated.

### 4.2 Database: new `kind` column

Migration 021:
```sql
ALTER TABLE artifact_types
  ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'llm';

-- CHECK constraint for safety
ALTER TABLE artifact_types
  ADD CONSTRAINT IF NOT EXISTS artifact_types_kind_check
  CHECK (kind IN ('llm', 'template', 'hybrid'));
```

No migration on existing rows — they all stay `kind='llm'` until the user clicks Reset per-type (which may flip the value).

### 4.3 Library registry — `backend/library/artifacts.py`

Single source of truth for canonical artifact types. Python module exports:

```python
from typing import TypedDict

class LibraryEntry(TypedDict):
    name: str
    kind: str            # 'llm' | 'template' | 'hybrid'
    category: str        # always 'artifacts' for this epic
    description: str     # shown in library browser
    prompt: str | None   # LLM prompt text (for llm/hybrid kinds; None for pure template)
    template_id: str | None  # key into backend/templates/registry.py (for template/hybrid)
    llm: str | None      # default provider ('openrouter' or None)
    model: str | None    # default model slug
    context_scope: str   # 'call' | 'project'
    seeded_by_default: bool  # True → auto-added to new projects
```

Initial library (8 entries):

| name | kind | seeded | template_id | description |
|---|---|---|---|---|
| Executive Summary | `llm` | ✓ | — | Prose recap of the call for quick scan. |
| Next Steps & Action Items | `template` | ✓ | `next_steps` | Every action item across topics, grouped by topic, owner bolded. |
| Questions for Stakeholders | `template` | ✓ | `questions_list` | Every open question across topics, grouped by topic. |
| Email Summary (1-pager) | `llm` | ✗ | — | Professional email to the client summarising the call. |
| Email Follow-up (pre-next-call) | `llm` | ✗ | — | Short email sent between calls recapping agreed work. |
| Next Call Agenda | `hybrid` | ✗ | `agenda_skeleton` | Open/in-progress topics as agenda; LLM writes intro + closing. |
| Risk Register | `template` | ✗ | `risk_register` | Topics with `sentiment=concern` or `is_parked=true`, with excerpts. |
| Decisions Digest | `template` | ✗ | `decisions_digest` | All `decisions[]` across topics, call-scoped or project-scoped. |

### 4.4 Template registry — `backend/templates/`

Each template is a Python module exporting a single render function:

```python
# backend/templates/next_steps.py
def render(topics: list[dict], *, scope: str = "call") -> str:
    """Render action items grouped by topic. Returns markdown string."""
    if not topics:
        return "_No action items captured._"
    lines = ["# Next Steps & Action Items\n"]
    for t in topics:
        actions = t.get("follow_up_items") or []
        if not actions:
            continue
        lines.append(f"## {t['name']}")
        for a in actions:
            # Bold owner prefix if pattern matches "Name: rest"
            import re
            m = re.match(r"^([A-Z][a-z]+(?:\s[A-Z][a-z]+)?):\s*(.*)$", a)
            if m:
                lines.append(f"- **{m.group(1)}:** {m.group(2)}")
            else:
                lines.append(f"- {a}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
```

Five initial templates:
- `backend/templates/next_steps.py` — renders `follow_up_items[]` grouped by topic
- `backend/templates/questions_list.py` — renders `open_questions[]` grouped by topic
- `backend/templates/agenda_skeleton.py` — renders open/in_progress topics as agenda bullets (for Hybrid kind; the intro/closing come from LLM)
- `backend/templates/risk_register.py` — filters topics where `sentiment=concern OR is_parked=true`, renders with transcript excerpts
- `backend/templates/decisions_digest.py` — renders `decisions[]` across all topics

Registry module `backend/templates/registry.py`:
```python
from backend.templates import next_steps, questions_list, agenda_skeleton, risk_register, decisions_digest

TEMPLATE_REGISTRY = {
    "next_steps":       next_steps.render,
    "questions_list":   questions_list.render,
    "agenda_skeleton":  agenda_skeleton.render,
    "risk_register":    risk_register.render,
    "decisions_digest": decisions_digest.render,
}
```

### 4.5 Generation flow — fork on kind

`backend/routers/artifacts.py` generation path (SSE stream handler):

```python
for artifact_row in artifacts_to_generate:
    kind = artifact_row.get("kind", "llm")
    if kind == "template":
        content = render_template(artifact_row, call_id, scope)
        update_artifact(artifact_row["id"], content=content, status="done")
    elif kind == "hybrid":
        intro = await generate_llm_snippet(artifact_row["prompt_intro"], topics)
        body = render_template(artifact_row, call_id, scope)
        closing = await generate_llm_snippet(artifact_row["prompt_closing"], topics)
        content = f"{intro}\n\n{body}\n\n{closing}"
        update_artifact(artifact_row["id"], content=content, status="done")
    else:  # 'llm' — existing path
        content = await generate_artifact(prompt, transcript, llm, topics=topics, model=model)
        update_artifact(artifact_row["id"], content=content, status="done")
```

**Hybrid schema:** the `prompt` column stores a JSON-ish structure for hybrid artifacts (two fields: `intro` and `closing`). Keeping `prompt` as TEXT and storing `{"intro": "...", "closing": "..."}` as JSON-encoded text avoids a new column. Alternative: two new nullable columns `prompt_intro`, `prompt_closing` — cleaner but more migration work. **Chosen: JSON-in-`prompt`** for hybrid kind (non-breaking for llm/template kinds).

**Template SSE behavior:** template artifacts complete near-instantly; still emit `status → generating → done` events on the SSE stream so the frontend's existing state machine is unchanged.

### 4.6 Seeding strategy

`seed_defaults(project_id)` in `routers/artifact_types.py` changes:

```python
def seed_defaults(project_id: str) -> None:
    from backend.library.artifacts import LIBRARY
    for entry in LIBRARY:
        if not entry["seeded_by_default"]:
            continue
        client.table("artifact_types").insert({
            "project_id": project_id,
            "name": entry["name"],
            "prompt": entry["prompt"],
            "is_default": True,
            "category": entry["category"],
            "kind": entry["kind"],
            "template_id": entry.get("template_id"),
            "llm": entry["llm"],
            "model": entry["model"],
            "context_scope": entry["context_scope"],
        }).execute()
    # Also seed workflow prompts (call_topics, project_topics, merge_verification, not_discussed_check)
    # — these keep their existing seeding pattern from EPIC-11.
```

**New DB column:** `artifact_types.template_id TEXT NULL` — carries the registry key for template + hybrid kinds; NULL for llm kind. Migration 021 also adds this column.

### 4.7 Reset-to-default — all artifact types

Extend `GET /api/artifact-types/defaults/{category}` to also accept `?name=<artifact_name>` for per-name lookup within `category='artifacts'`:

```
GET /api/artifact-types/defaults/artifacts?name=Next%20Steps%20%26%20Action%20Items
→ { name, kind, prompt, template_id, llm, model, context_scope }
```

Lookup is a linear scan of the `LIBRARY` list matching by `name` + `category`.

Reset button appears on **every** artifact type card (not just `call_topics` as today). Semantics: calls the endpoint, overwrites the draft state with the canonical record, including `kind`. Saving converts the stored row's `kind`.

**What if a user's artifact type name doesn't match any library entry?** (e.g. custom types they created). Reset button is hidden for those — they have no canonical to reset to.

### 4.8 "Add from library" UX

Extend the existing `AddArtifactTypeModal` with a third tab:

```
┌─────────────────────────────────────────┐
│  Browse library │ Create new │ Import  │    ← tabs
├─────────────────────────────────────────┤
│ Browse library tab (default):           │
│                                         │
│  [x] Email Summary 🤖    [Add]          │
│      Professional email to the client…  │
│                                         │
│  [x] Email Follow-up 🤖  [Add]          │
│      Short email sent between calls…    │
│                                         │
│  [x] Next Call Agenda ⚡  [Add]         │
│      Open topics as agenda; LLM intro…  │
│                                         │
│  [x] Risk Register 🔧    [Add]          │
│      Topics with concern or parked…     │
│                                         │
│  [x] Decisions Digest 🔧 [Add]          │
│      All decisions across topics…       │
└─────────────────────────────────────────┘
```

Filters out library entries already present in the project (match by name, case-insensitive). Click *Add* → POST to a new endpoint `POST /api/projects/{id}/artifact-types/from-library` with `{name: "Risk Register"}` → backend looks up the library entry + inserts the row → modal closes + page refreshes.

### 4.9 Artifact type card UX per kind

**Template kind (🔧):**
```
┌────────────────────────────────────────┐
│ 🔧 Next Steps & Action Items  [badge] │
│                                        │
│ Template — no LLM. Renders your        │
│ follow_up_items grouped by topic.      │
│                                        │
│ [ Preview with recent call ] [ Reset ] │
│                                        │
│ [ Delete ]                              │
└────────────────────────────────────────┘
```

No prompt textarea. No provider/model picker. "Preview with recent call" fetches the latest completed call's data and runs the renderer, showing markdown output in a dialog.

**LLM kind (🤖):**
Same card as EPIC-11 (Provider dropdown, OpenRouter model picker, expandable textarea, runtime context disclosure, Reset button). Unchanged except: diff-vs-canonical badge added, cost preview added.

**Hybrid kind (⚡):**
Template skeleton description (read-only) + two editable LLM prompt fields (`Intro prompt` and `Closing prompt`) + Provider/model picker that applies to both. Reset restores both prompts.

### 4.10 Diff-vs-canonical indicator

Small badge on the artifact card header:
- `⟲ canonical` (grey) — prompt exactly matches the library version (char-for-char, after trim)
- `✎ edited` (amber) — user has customized

Computed client-side by comparing `type.prompt` against the value fetched from `GET /api/artifact-types/defaults/artifacts?name=...`. For non-canonical types (no library match), badge hidden.

Save persists the edited prompt. Next visit recomputes the badge based on the stored text vs library text.

### 4.11 Cost preview

Small hint next to the model picker on LLM + hybrid cards:
```
Cost estimate: ~$0.10 per call
```

Computed from a frontend constant `MODEL_COSTS`:
```typescript
export const MODEL_COSTS: Record<string, { inputPerMillion: number; outputPerMillion: number }> = {
  "anthropic/claude-sonnet-4.6":   { inputPerMillion: 3,    outputPerMillion: 15 },
  "openai/gpt-4o":                  { inputPerMillion: 2.5,  outputPerMillion: 10 },
  "google/gemini-2.5-pro":          { inputPerMillion: 1.25, outputPerMillion: 5  },
  "deepseek/deepseek-chat":         { inputPerMillion: 0.27, outputPerMillion: 1.1 },
  "deepseek/deepseek-v3.2":         { inputPerMillion: 0.27, outputPerMillion: 1.1 },
  "meta-llama/llama-3.3-70b-instruct": { inputPerMillion: 0.59, outputPerMillion: 0.79 },
};
```

Rough estimate assumes ~12k input tokens + ~4k output tokens (representative for a 30-min call). Formula:
```
cost = (12_000 / 1_000_000) * inputPerMillion + (4_000 / 1_000_000) * outputPerMillion
```

Templates show "Cost: $0 (template)". Unknown slugs show "Cost: —".

## 5. Implementation plan preview

**Backend — schema:**
1. Migration 021 — `artifact_types.kind TEXT DEFAULT 'llm'`, `artifact_types.template_id TEXT NULL`, CHECK constraint for kind
2. Pydantic models — `ArtifactTypeCreate`, `ArtifactTypeUpdate`, `ArtifactTypeOut` grow `kind: Literal[...]` and `template_id: str | None`

**Backend — library + templates:**
3. `backend/library/__init__.py` + `backend/library/artifacts.py` — the 8-entry `LIBRARY` list
4. `backend/templates/__init__.py` + 5 renderer modules (`next_steps.py`, `questions_list.py`, `agenda_skeleton.py`, `risk_register.py`, `decisions_digest.py`)
5. `backend/templates/registry.py` — maps `template_id` → render function
6. Unit tests per template: given canned topic data, assert markdown output

**Backend — generation flow:**
7. `routers/artifacts.py` SSE handler — fork on `kind`, call `render_template` or `generate_hybrid` or existing LLM path
8. New helper `backend/services/template_service.py` — `render_template(artifact_row, call_id, scope)` looks up renderer, calls with `list_call_topics` or `list_project_topics`
9. Hybrid generation — parse `prompt` as JSON, extract `intro` + `closing`, run LLM for each, concat with template body
10. Tests — template artifacts complete without LLM mock; hybrid artifacts invoke LLM twice then concatenate

**Backend — library/reset APIs:**
11. `GET /api/artifact-types/defaults/{category}?name=<name>` — per-name lookup within category
12. `GET /api/artifact-types/library` — returns the `LIBRARY` list, JSON-serialised
13. `POST /api/projects/{id}/artifact-types/from-library` — body `{name}`, looks up library entry, inserts row
14. `POST /api/artifact-types/{id}/preview` — body `{call_id}`, returns rendered markdown (template or hybrid-template-only) for the latest completed call. Skips the LLM for hybrid previews (preview is just the skeleton).
15. `seed_defaults` rewrites to iterate LIBRARY with `seeded_by_default=True` filter

**Frontend — types + constants:**
14. `types/index.ts` — `ArtifactKind = "llm" | "template" | "hybrid"`; add `kind`, `template_id` to `ArtifactType`
15. `constants/models.ts` — add `MODEL_COSTS` map

**Frontend — library modal:**
16. `AddArtifactTypeModal.tsx` — third tab "Browse library", fetches library list via new `GET /api/artifact-types/library`, filters out present types, POST to `from-library` endpoint on click

**Frontend — card per kind:**
17. `ArtifactTypeCard.tsx` — conditional rendering branches on `type.kind`:
    - Template kind: description + Preview button + Reset + Delete
    - LLM kind: existing markup + diff-vs-canonical badge + cost preview
    - Hybrid kind: template description + two prompt textareas (intro/closing) + shared provider/model picker
18. `api/client.ts` — `getDefaults(category, name?)`, `fromLibrary(projectId, name)`, `library()` list endpoint, `previewTemplate(typeId, callId)` endpoint (optional — can render inline without backend roundtrip if data is in browser)

**Frontend — preview:**
19. `TemplatePreviewModal.tsx` — new component; fetches latest completed call's `list_call_topics` via existing API, runs the renderer *server-side* via new endpoint `POST /api/artifact-types/{id}/preview?call_id=<id>`, shows markdown output

**Migration / rollout:**
- Existing artifact_types rows get `kind='llm'`, `template_id=NULL` by default. All existing projects keep working as LLM artifacts.
- When user clicks Reset on a type whose name matches a library entry with `kind='template'`, the row's `kind` flips. Silent but effective.
- New projects seed only 3 types (Exec 🤖, Next Steps 🔧, Questions 🔧).

## 6. Tests

**Backend:**
- `test_templates_next_steps` — canned topic list with owner-prefixed actions → assert markdown structure, bolded owners
- `test_templates_questions_list` — topics with open_questions → assert blue-prefix rendering
- `test_templates_agenda_skeleton` — only open/in_progress, sorted by concern first → verify ordering
- `test_templates_risk_register` — only `sentiment=concern` + `is_parked=true` rendered; neutral topics excluded
- `test_templates_decisions_digest` — all decisions across topics flattened; call-scope vs project-scope both tested
- `test_generation_forks_on_kind` — kind=template artifact completes with renderer output, no LLM mock called
- `test_generation_hybrid_calls_llm_twice_then_concats` — hybrid artifact fires 2 LLM calls + 1 render, content is concatenation
- `test_library_endpoint_returns_8_entries` — GET library returns canonical list
- `test_from_library_creates_row_with_kind` — POST with name="Risk Register" inserts a row with `kind='template'`, `template_id='risk_register'`
- `test_reset_to_default_for_artifact_name` — GET defaults with name param returns library entry including kind
- `test_seed_defaults_inserts_only_three_artifacts` — new project gets 3 types (not 6)

**Frontend:**
- `tsc --noEmit` + `npm run lint` clean after all component changes
- Manual smoke: library modal shows 5 available entries, click Add → row appears on page; reset on existing LLM Next Steps → kind flips to template; template card shows Preview button; preview opens modal with markdown

## 7. Open questions

1. **Hybrid prompt storage: JSON-in-`prompt` vs two new columns.** Spec §4.5 picks JSON-in-`prompt` to avoid migration work. Acceptable?
2. **Preview scope.** Preview fetches the latest completed call's topics. Users may want to preview against a specific call. Deferring specific-call preview to follow-up.
3. **Template preview endpoint vs client-side render.** Client-side is cheaper (no API call) but requires porting the Python render logic to TypeScript (duplication). Server-side endpoint is simpler but adds a round-trip. Spec picks server-side for single-source-of-truth.
4. **Import-from-another-project behavior for templates.** If a user imports a template-kind artifact type from another project, do we copy `kind + template_id` (matches source) or force `kind='llm'` for cross-project imports? Recommend: copy as-is.

## 8. References

- Spec: `2026-04-22-call-topics-extraction-overhaul-design.md` (EPIC-11)
- Current artifact card: `frontend/src/components/ArtifactTypeCard.tsx`
- Current modal: `frontend/src/components/AddArtifactTypeModal.tsx`
- Current seed: `backend/routers/artifact_types.py::seed_defaults`
- Current generation flow: `backend/routers/artifacts.py::stream_artifacts`
- Library spec derives from EPIC-11 topic schema (`topic_updates` new fields) — templates depend on `follow_up_items`, `open_questions`, `is_parked`, `decisions` being populated
