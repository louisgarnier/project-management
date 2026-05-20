# EPIC-12 — Artifacts Overhaul — Design

**Date:** 2026-04-23
**Status:** Draft — pending user review
**Relates to:** [EPIC-11 design](./2026-04-22-call-topics-extraction-overhaul-design.md), [`ArtifactTypeCard.tsx`](../../../frontend/src/components/ArtifactTypeCard.tsx), [`routers/artifacts.py`](../../../backend/routers/artifacts.py), [`routers/artifact_types.py`](../../../backend/routers/artifact_types.py)

---

## 1. Problem

The artifact generation system has six tangled pain points:

- **Re-extraction waste.** Today every artifact is an LLM call. "Next Steps & Action Items" and "Questions for Stakeholders" re-extract content the user already reviewed on the Call Topics tiles — lossy, costly, potentially inconsistent ("Nick: run benchmark" vs *"Nick should run a benchmark"*).
- **Pre-populated bloat.** New projects auto-seed 6 artifact types. Projects that don't need emails or agendas still get them, forcing manual deletion.
- **Two workflow prompts are invisible.** The Artifacts page filter at [`page.tsx:102-105`](../../../frontend/app/projects/[id]/artifacts/page.tsx#L102-L105) only surfaces `category='call_topics' | 'project_topics' | 'topics'`. `merge_verification` and `not_discussed_check` prompts exist in DB but have no UI — users can't see or edit them.
- **No reusable library across projects.** To reuse a tuned prompt, users have to Import from another project by remembering which project has it. No central pool.
- **Reset-to-default gap.** EPIC-11 added `GET /api/artifact-types/defaults/{category}` but only for workflow categories (`call_topics` etc.). Individual artifact types (Executive Summary, Next Steps…) have no per-name canonical, so the Reset button was UI-wrapped to only show on `call_topics` cards. The rest can't be reset.
- **Cost opacity.** Users have no visibility into per-artifact cost; a 6-artifact generation with Sonnet is ~$0.60 with no forewarning.

## 2. Goals

Establish a **two-tier model** for every project:

### Tier 1 — Workflow Prompts (system-essential, per-project)
Four prompts the extraction/merge/verification pipeline needs to function. Always present on every project, always visible on the Artifacts page, editable per-project, have canonical defaults (EPIC-11 `backend/prompts/*.py` modules), Reset-to-default button works.

The four: `call_topics`, `project_topics`, `merge_verification`, `not_discussed_check`.

### Tier 2 — Artifact Prompts (library-backed, cross-project reusable)
A shared **artifact library** backing every project's artifact list. Users can:
- **Add from library** → copy a library entry into the current project
- **Publish to library** → promote a project's artifact type to the shared pool so other projects can add it
- **Edit library entries** via a management page
- System-canonical library entries seed on first run — users can delete, re-add, edit

Plus:
- **Three artifact kinds** — *Template* (deterministic, no LLM), *LLM* (prompt + structured topics), *Hybrid* (template scaffold + LLM prose wrapper)
- **Minimal seeding on new projects** — 3 library entries flagged `seeded_by_default=true` (Executive Summary, Next Steps, Questions for Stakeholders) auto-added on project create; others opt-in
- **Reset-to-default for every artifact type** including kind conversion
- **Diff-vs-canonical indicator** when a project's prompt diverges from its library source
- **Cost preview** per LLM artifact

## 3. Non-goals

- **No user-editable template logic.** Templates are Python renderers. Users who need custom behavior create a custom **LLM** artifact (existing mechanism).
- **No retroactive migration of existing projects.** Existing projects' 6 types stay as-is until the user clicks Reset per type. No bulk migrate-all button.
- **No live pricing API.** Cost preview uses hardcoded per-1M-token rates from a frontend constant.
- **No versioned prompt history.** Out of scope. Reset button is the "undo".
- **No per-user or per-org library scoping.** Single-user app today → single shared library. Multi-tenancy deferred.
- **No streaming for template artifacts.** Templates render synchronously. SSE keeps its shape; it just skips LLM for template artifacts.
- **No editing workflow prompts from the library.** Tier 1 is strictly per-project, canonical defaults live in code (`backend/prompts/*.py`). The library (Tier 2) contains only artifact prompts.

## 4. Design

### 4.1 Artifact `kind` — three values

```
kind ∈ {'llm', 'template', 'hybrid'}
```

- **`llm`** — current behavior. Prompt + transcript (+ structured topics for project scope) → LLM call via `generate_artifact`. Output is the LLM response.
- **`template`** — zero LLM. A Python renderer function takes `list_call_topics(call_id)` (or `list_project_topics` for project scope) and returns markdown. Output is the renderer's return value.
- **`hybrid`** — template skeleton + LLM intro/closing. Renderer produces the structural bulk (topic list, statuses); two short LLM calls produce intro and closing prose. Output is `intro + template_body + closing` concatenated.

### 4.2 Database: migration 021 — `kind` + `template_id` + library table + ref

```sql
-- Add kind + template_id to artifact_types
ALTER TABLE artifact_types
  ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'llm',
  ADD COLUMN IF NOT EXISTS template_id TEXT DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS library_ref_id UUID DEFAULT NULL;

ALTER TABLE artifact_types
  ADD CONSTRAINT IF NOT EXISTS artifact_types_kind_check
  CHECK (kind IN ('llm', 'template', 'hybrid'));

-- New: artifact library pool
CREATE TABLE IF NOT EXISTS artifact_library (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'llm' CHECK (kind IN ('llm', 'template', 'hybrid')),
  prompt TEXT DEFAULT NULL,                -- nullable for pure templates
  template_id TEXT DEFAULT NULL,            -- registry key for template/hybrid
  llm TEXT DEFAULT NULL,
  model TEXT DEFAULT NULL,
  context_scope TEXT NOT NULL DEFAULT 'call' CHECK (context_scope IN ('call', 'project')),
  is_system BOOLEAN NOT NULL DEFAULT FALSE, -- true = system-canonical (can't hard-delete, Reset restores)
  seeded_by_default BOOLEAN NOT NULL DEFAULT FALSE, -- auto-added on new project create
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (name)  -- library names are unique (case-sensitive)
);

-- Ref back: artifact_types.library_ref_id → artifact_library.id (on delete: NULL so the project type survives)
ALTER TABLE artifact_types
  ADD CONSTRAINT IF NOT EXISTS artifact_types_library_ref_fkey
  FOREIGN KEY (library_ref_id) REFERENCES artifact_library(id) ON DELETE SET NULL;
```

Existing `artifact_types` rows unaffected — they get `kind='llm'`, `template_id=NULL`, `library_ref_id=NULL`. Workflow prompts (`category != 'artifacts'`) stay per-project and are never linked to the library.

### 4.3 Library seeding — system-canonical entries

On application startup (or first migration run), a one-shot seed populates `artifact_library` with 8 system-canonical entries. Implementation: `backend/library/seed.py` exports `SYSTEM_LIBRARY` list; a startup hook runs an upsert-by-name so re-running is idempotent.

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

All 8 start with `is_system=true`. Users can edit the `prompt` / `llm` / `model` / `description` on system entries (edits are their personal overrides). Users can **hide** but not hard-delete system entries — a "Reset library to system defaults" button re-upserts the `SYSTEM_LIBRARY` rows with original values.

User-created library entries have `is_system=false` — fully deletable.

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

### 4.6 Seeding strategy on new project

`seed_defaults(project_id)` in `routers/artifact_types.py` changes to query the `artifact_library` table:

```python
def seed_defaults(project_id: str) -> None:
    client = get_client()

    # Tier 1 — workflow prompts: unchanged from EPIC-11, always all 4 seeded
    for workflow_prompt in (DEFAULT_CALL_TOPICS_PROMPT, DEFAULT_PROJECT_TOPICS_PROMPT,
                            DEFAULT_MERGE_VERIFICATION_PROMPT, DEFAULT_NOT_DISCUSSED_CHECK_PROMPT):
        client.table("artifact_types").insert({"project_id": project_id, **workflow_prompt}).execute()

    # Tier 2 — artifact types: query library for seeded_by_default=true entries, copy each
    seeded = (
        client.table("artifact_library")
        .select("id, name, description, kind, prompt, template_id, llm, model, context_scope")
        .eq("seeded_by_default", True)
        .execute()
        .data
    )
    for entry in seeded:
        client.table("artifact_types").insert({
            "project_id": project_id,
            "name": entry["name"],
            "prompt": entry.get("prompt"),
            "is_default": True,
            "category": "artifacts",
            "kind": entry["kind"],
            "template_id": entry.get("template_id"),
            "library_ref_id": entry["id"],
            "llm": entry.get("llm"),
            "model": entry.get("model"),
            "context_scope": entry.get("context_scope", "call"),
        }).execute()
```

**Result:** a new project ends up with 4 Tier-1 rows + 3 Tier-2 rows (from library `seeded_by_default=true`).

### 4.7 Reset-to-default — works for both tiers

Two sources for the "canonical" version depending on tier:

- **Tier 1 (workflow prompts):** Reset reads from `backend/prompts/*.py` modules via the existing EPIC-11 endpoint `GET /api/artifact-types/defaults/{category}` (category = `call_topics` | `project_topics` | `merge_verification` | `not_discussed_check`). Unchanged.

- **Tier 2 (artifact types):** Reset reads from `artifact_library` via the artifact type's `library_ref_id`. New endpoint:
  ```
  GET /api/artifact-types/{type_id}/library-source
  → { id, name, description, kind, prompt, template_id, llm, model, context_scope }
  ```
  Returns the library entry pointed at by `library_ref_id`. 404 if `library_ref_id IS NULL` (user-created custom types with no library origin can't be reset).

Reset button appears on **every** artifact type card where a canonical exists. Semantics: overwrites the draft state with the source record, including `kind` (so an LLM-mode Next Steps flips to template on reset if the library says so). Saving converts the stored row's `kind`.

**Custom types (no `library_ref_id`):** Reset button hidden. User can still edit or delete as today.

### 4.8 "Add from library" UX

Extend the existing `AddArtifactTypeModal` with a third tab (first/default tab — promoted over "Create new"):

```
┌─────────────────────────────────────────┐
│  Browse library │ Create new │ Import  │    ← tabs
├─────────────────────────────────────────┤
│ Browse library tab (default):           │
│                                         │
│  Email Summary 🤖         [Add]          │
│     Professional email to the client    │
│     🏛 system                            │
│                                         │
│  Email Follow-up 🤖       [Add]          │
│     Short email sent between calls      │
│     🏛 system                            │
│                                         │
│  Next Call Agenda ⚡      [Add]          │
│     Open topics as agenda; LLM intro    │
│     🏛 system                            │
│                                         │
│  Risk Register 🔧         [Add]          │
│     Topics with concern or parked       │
│     🏛 system                            │
│                                         │
│  Decisions Digest 🔧      [Add]          │
│     All decisions across topics         │
│     🏛 system                            │
│                                         │
│  Board Meeting Summary 🤖 [Add]          │
│     My custom type from Project aaaa    │
│     👤 published from aaaa · 2d ago      │
└─────────────────────────────────────────┘
```

Source: `GET /api/library` returns every `artifact_library` row with a small badge — `🏛 system` for `is_system=true` or `👤 published from <project>` for user-published entries. Filters out library entries already present in the current project (match by `library_ref_id` so multiple imports of the same library entry are blocked).

Click *Add* → `POST /api/projects/{id}/artifact-types/from-library` with `{library_id: "<uuid>"}` → backend copies the library entry to a new `artifact_types` row with `library_ref_id` set → modal closes + page refreshes.

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
- `⟲ canonical` (grey) — prompt exactly matches the library/workflow source (char-for-char, after trim)
- `✎ edited` (amber) — user has customized
- *(no badge)* — custom type with no library source

Computed client-side by comparing the stored `prompt` against:
- **Tier 1:** `backend/prompts/*.py` canonical (fetched via existing defaults endpoint)
- **Tier 2 with `library_ref_id`:** `artifact_library.prompt` (fetched via `GET /api/artifact-types/{id}/library-source`)
- **Tier 2 without `library_ref_id`:** skipped — custom type, no source to compare

Save persists the edited prompt. Next visit recomputes the badge.

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

### 4.12 Artifacts page layout — two tiers visible

`/projects/{id}/artifacts` gets two clearly-labeled sections:

```
┌───────────────────────────────────────────────────────────────┐
│  Artifact Types                        [Project default: …]   │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  ⚙️  TIER 1 — WORKFLOW PROMPTS  (system-essential, 4 prompts) │
│  ────────────────────────────────────────────────────         │
│  [Call Topics Extraction   ⟲ canonical]                       │
│  [Project Topics Merge     ✎ edited]                          │
│  [Merge Verification       ⟲ canonical]                       │
│  [Not-Discussed Verification ⟲ canonical]                     │
│                                                               │
│  📝  TIER 2 — ARTIFACT PROMPTS   [+ Add artifact type ▾]      │
│  ────────────────────────────────────────────────────         │
│  [Executive Summary  🤖 OpenRouter · sonnet-4.6  ⟲ canonical] │
│  [Next Steps          🔧 Template  ⟲ canonical]               │
│  [Questions           🔧 Template  ✎ edited]                  │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

**Tier 1 section:**
- Always exactly 4 cards
- No "+ Add" button (the 4 are fixed — you can't add or remove workflow prompts)
- Cards use existing EPIC-11 rich card UX (provider/model picker, expandable textarea, runtime-context disclosure, Reset button)
- Filter fix: `frontend/app/projects/[id]/artifacts/page.tsx` updates the workflow-prompts filter from `category ∈ { 'call_topics' | 'project_topics' | 'topics' }` to `category ∈ { 'call_topics' | 'project_topics' | 'merge_verification' | 'not_discussed_check' }`

**Tier 2 section:**
- 0+ cards (depends on what the user has in this project)
- "+ Add artifact type ▾" button opens the `AddArtifactTypeModal` (Browse library / Create new / Import from another project tabs)
- Each card has Publish-to-library button (§4.14) if not already library-backed, plus Reset / Edit / Delete
- Delete on Tier 2 only removes the project's row — never touches the library entry

### 4.13 Library management page — `/library`

A new top-level page (not project-scoped) for managing the shared pool. Nav entry in the sidebar under "Projects": **"Artifact Library"**.

```
┌────────────────────────────────────────────────────────────┐
│  Artifact Library                 [+ New library entry]    │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  🏛 SYSTEM (8)                     [Reset to defaults]     │
│  [Executive Summary 🤖 🌱 seeded]                           │
│  [Next Steps & Action Items 🔧 🌱 seeded]                   │
│  [Questions for Stakeholders 🔧 🌱 seeded]                  │
│  [Email Summary 🤖]                                         │
│  [Email Follow-up 🤖]                                       │
│  [Next Call Agenda ⚡]                                      │
│  [Risk Register 🔧]                                         │
│  [Decisions Digest 🔧]                                      │
│                                                            │
│  👤 YOURS (2)                                              │
│  [Board Meeting Summary 🤖   published from aaaa · 2d ago] │
│  [Compliance Memo 🤖         published from rammmm · 1d]   │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**Capabilities:**
- Edit any entry inline (name, description, prompt, llm, model, context_scope, seeded_by_default toggle)
- **Templates and hybrids** — name + description + `seeded_by_default` toggle editable; template_id / kind locked (can't change a template to a different renderer)
- Click an entry → opens a detail editor (similar to artifact card but in a wider layout). **Reset button on system entries** restores the original system values (reads from `backend/library/seed.py::SYSTEM_LIBRARY`).
- Hard-delete allowed on `is_system=false` entries. System entries can only be hidden (set `seeded_by_default=false`); "Reset to defaults" button re-seeds.
- Impact on existing projects: editing a library entry does NOT cascade to projects that already imported it (copy semantics). The diff-vs-canonical badge is the only signal.

Routes: `GET /api/library`, `POST /api/library`, `PATCH /api/library/{id}`, `DELETE /api/library/{id}` (blocked on `is_system=true`), `POST /api/library/reset-system`.

### 4.14 Publish to library — button on artifact card

A small **"Publish to library"** button on Tier 2 artifact cards. Clicking it:

1. Opens a confirmation dialog: *"Publish 'Board Meeting Summary' to the library? Other projects will be able to add a copy of it."*
2. Default `name` = the artifact type's name; user can edit in the dialog (to avoid clashing with system entries)
3. Default `description` = empty; user fills in a one-line description
4. POSTs `{name, description, kind, prompt, template_id, llm, model, context_scope}` to `POST /api/library` with `is_system=false`
5. On success, backend sets `artifact_types.library_ref_id = <new library id>` on the source row so Reset works going forward

**Already library-backed (`library_ref_id NOT NULL`):** button hidden; Publish only makes sense for originals.

**Template / hybrid artifacts:** can't be created in-project (they need Python code) so they can never be Published. The button is only visible on LLM-kind cards.

## 5. Implementation plan preview

**Backend — schema (manual in Supabase):**
1. Migration 021 — per §4.2: adds `artifact_types.kind`, `artifact_types.template_id`, `artifact_types.library_ref_id`, creates `artifact_library` table with FK, CHECK constraints

**Backend — template renderers:**
2. `backend/templates/__init__.py` + 5 renderer modules: `next_steps.py`, `questions_list.py`, `agenda_skeleton.py`, `risk_register.py`, `decisions_digest.py`
3. `backend/templates/registry.py` — maps `template_id` → render function
4. Unit tests per template: canned topic list → asserted markdown output

**Backend — library seeding:**
5. `backend/library/__init__.py` + `backend/library/seed.py` — `SYSTEM_LIBRARY: list[dict]` with the 8 canonical entries
6. Startup hook (in `backend/main.py` lifespan) — upsert `SYSTEM_LIBRARY` rows by name on boot; idempotent
7. Tests — startup seeds DB; re-running is a no-op; user edits to prompts are NOT overwritten except by explicit Reset-to-system call

**Backend — library CRUD API:**
8. `routers/library.py` — new router, mounted at `/api/library`:
   - `GET /` — list all library entries
   - `POST /` — create (user-published)
   - `PATCH /{id}` — edit (any non-system field; `is_system` flag-gated on specific fields)
   - `DELETE /{id}` — delete (403 if `is_system=true`)
   - `POST /reset-system` — re-upsert SYSTEM_LIBRARY with original values
9. Tests — CRUD happy paths, delete-system rejected, reset-system restores

**Backend — artifact_types API updates:**
10. `ArtifactTypeCreate`, `ArtifactTypeUpdate`, `ArtifactTypeOut` Pydantic models grow `kind`, `template_id`, `library_ref_id`
11. `POST /api/projects/{id}/artifact-types/from-library` — body `{library_id}` — copies library entry to artifact_types with `library_ref_id` set
12. `GET /api/artifact-types/{id}/library-source` — fetch the library entry this artifact type was copied from, or 404
13. `POST /api/artifact-types/{id}/publish-to-library` — body `{name, description}` — creates library entry from this artifact type, sets `library_ref_id` on the source row, returns library entry
14. `POST /api/artifact-types/{id}/preview` — body `{call_id}` — runs the template renderer (for template / hybrid-skeleton) and returns markdown
15. `seed_defaults(project_id)` rewritten per §4.6 — inserts 4 Tier-1 workflow prompts + library entries where `seeded_by_default=true`

**Backend — generation flow:**
16. `routers/artifacts.py` SSE handler — fork on `kind`:
    - `kind='template'` → call `template_service.render(artifact_row, call_id, scope)`, skip LLM, write content + status=done
    - `kind='hybrid'` → parse `prompt` as JSON `{intro, closing}`, run LLM for each, concat with template render, write content + status=done
    - `kind='llm'` → existing path unchanged
17. `backend/services/template_service.py` — `render(artifact_row, call_id, scope)` dispatches to the renderer via `template_id`
18. Tests — template artifacts complete without LLM mock; hybrid invokes LLM twice then concatenates

**Frontend — types + constants:**
19. `types/index.ts` — add `ArtifactKind = "llm" | "template" | "hybrid"`, extend `ArtifactType` with `kind`, `template_id`, `library_ref_id`; add `LibraryEntry` type
20. `constants/models.ts` — add `MODEL_COSTS` map

**Frontend — Artifacts page two-tier layout:**
21. `app/projects/[id]/artifacts/page.tsx` — split into Tier 1 + Tier 2 sections with labeled headers:
    - Tier 1 filter fix: `category ∈ {'call_topics', 'project_topics', 'merge_verification', 'not_discussed_check'}` — **includes the 2 currently-hidden ones**
    - Tier 2 filter: `category === 'artifacts'`
22. `ArtifactTypeCard.tsx` — per-kind conditional rendering:
    - Template kind: description + Preview button + Reset + Delete + Publish (hidden for templates)
    - LLM kind: existing markup + diff-vs-canonical badge + cost preview + Publish-to-library button
    - Hybrid kind: template-skeleton description (read-only) + two editable prompt textareas (`Intro prompt` / `Closing prompt`) + shared provider/model picker

**Frontend — Add modal + library page:**
23. `AddArtifactTypeModal.tsx` — third tab "Browse library" (new default), fetches `GET /api/library`, filters out types with matching `library_ref_id`, POSTs to `from-library`
24. `app/library/page.tsx` — new top-level page. Lists library entries grouped by System / Yours. Entry cards similar to artifact cards but wider.
25. `components/LibraryEntryCard.tsx` — edit inline, delete (if non-system), system entries show "Reset to system defaults" when edited
26. `components/PublishToLibraryDialog.tsx` — modal triggered from artifact card; fields `name` + `description`; POSTs to `publish-to-library`
27. `components/Sidebar.tsx` — add "Artifact Library" nav entry

**Frontend — API client:**
28. `api/client.ts` — `libraryAPI = { list, create, update, delete, resetSystem }`, `artifactTypesAPI.fromLibrary`, `getLibrarySource`, `publishToLibrary`, `preview`

**Migration / rollout:**
- Existing `artifact_types` rows stay with defaults (`kind='llm'`, `template_id=NULL`, `library_ref_id=NULL`) — existing projects keep working
- First boot after migration 021: startup hook seeds `artifact_library` with 8 system entries (idempotent)
- User clicks Reset on an existing project's Next Steps → endpoint looks up matching library entry by name (if `library_ref_id` is NULL, we match by name to the system library as fallback), flips kind from `llm` to `template`, sets `library_ref_id`
- New projects: 4 Tier-1 + 3 Tier-2 (Exec/NextSteps/Questions) auto-seeded

## 6. Tests

**Backend — templates:**
- `test_templates_next_steps` — canned topic list with owner-prefixed actions → assert markdown structure, bolded owners
- `test_templates_questions_list` — topics with open_questions → assert rendering
- `test_templates_agenda_skeleton` — only open/in_progress, sorted by concern first → verify ordering
- `test_templates_risk_register` — only `sentiment=concern` + `is_parked=true` rendered; neutral topics excluded
- `test_templates_decisions_digest` — all decisions across topics flattened; call-scope vs project-scope both tested

**Backend — library:**
- `test_library_startup_seeds_8_system_entries` — fresh DB + startup hook → 8 rows with `is_system=true`
- `test_library_startup_is_idempotent` — running twice doesn't create duplicates; user edits preserved
- `test_library_reset_system_restores_original` — after user edit, POST reset-system restores the seed row's values
- `test_library_delete_system_returns_403` — system entries cannot be hard-deleted
- `test_library_list_groups_system_and_user` — response includes both `is_system=true` and user-created entries
- `test_library_crud_happy_paths` — POST / PATCH / DELETE for user-created entries

**Backend — artifact_types flow:**
- `test_from_library_creates_row_with_kind_and_ref` — POST with library_id inserts row with `kind` + `template_id` + `library_ref_id` copied
- `test_publish_to_library_creates_entry_and_links` — publishing a custom LLM type creates library row, sets source row's `library_ref_id`
- `test_library_source_endpoint_returns_linked_entry` — GET library-source returns the library row
- `test_library_source_404_when_no_ref` — GET library-source on a type with NULL `library_ref_id` → 404
- `test_seed_defaults_inserts_4_workflow_plus_3_seeded_library` — new project gets 4 Tier-1 + 3 Tier-2 rows
- `test_generation_forks_on_kind` — kind=template artifact completes with renderer output, no LLM mock called
- `test_generation_hybrid_calls_llm_twice_then_concats` — hybrid artifact fires 2 LLM calls + 1 render, content is concatenation

**Frontend:**
- `tsc --noEmit` + `npm run lint` clean after all component changes
- Manual smoke checklist (expanded EPIC-11 manual test doc):
  - Artifacts page shows Tier 1 (4 cards) + Tier 2 sections
  - `merge_verification` and `not_discussed_check` cards now visible in Tier 1
  - "+ Add artifact type" modal has 3 tabs, Browse library default
  - Click library entry → appears in Tier 2
  - Click Publish on a custom LLM artifact → dialog → appears in `/library` under "Yours"
  - Click Reset on a Tier 2 card with library_ref_id → prompt reverts
  - Edit a library entry in `/library` → existing project artifacts get `✎ edited` badge if they diverged
  - Delete a user library entry works; delete a system entry is blocked (button hidden)
  - Reset library to system defaults restores any system entries the user edited

## 7. Open questions

1. **Hybrid prompt storage: JSON-in-`prompt` vs two new columns.** Spec §4.5 picks JSON-in-`prompt` to avoid migration work. Acceptable?
2. **Preview scope.** Preview fetches the latest completed call's topics. Users may want to preview against a specific call. Deferring specific-call preview to follow-up.
3. **Template preview endpoint vs client-side render.** Client-side is cheaper (no API call) but requires porting the Python render logic to TypeScript (duplication). Server-side endpoint is simpler but adds a round-trip. Spec picks server-side for single-source-of-truth.
4. **Import-from-another-project behavior for templates.** If a user imports a template-kind artifact type from another project, do we copy `kind + template_id` (matches source) or force `kind='llm'` for cross-project imports? Recommend: copy as-is.
5. **Library entries with kind=template — can a user publish a template?** Today templates require Python code → user can't create one in a project → nothing to publish. Recommend: Publish button hidden when `kind != 'llm'`.
6. **Library `/library` page access.** Today the sidebar has project list; top-level page pattern exists (there's a project list page). Recommend: add "Artifact Library" link near the top of the sidebar as a peer of "Projects".
7. **Reset on existing projects with NULL `library_ref_id`.** For the 2 existing projects whose artifact types predate EPIC-12, clicking Reset needs a fallback: match by name to system library entries. On success, also set `library_ref_id` so subsequent Resets are fast. Recommend: include this name-fallback in the `library-source` endpoint.

## 8. References

- Spec: `2026-04-22-call-topics-extraction-overhaul-design.md` (EPIC-11)
- Current artifact card: `frontend/src/components/ArtifactTypeCard.tsx`
- Current modal: `frontend/src/components/AddArtifactTypeModal.tsx`
- Current seed: `backend/routers/artifact_types.py::seed_defaults`
- Current generation flow: `backend/routers/artifacts.py::stream_artifacts`
- Library spec derives from EPIC-11 topic schema (`topic_updates` new fields) — templates depend on `follow_up_items`, `open_questions`, `is_parked`, `decisions` being populated
