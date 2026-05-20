# Project Matching & Project Updates — Flow Reference

**Date:** 2026-05-20
**Scope:** how the two middle stages of the call pipeline work — what data enters, what processing happens (manual + LLM), and what gets persisted.
**Pipeline position:**

```
transcript → call_topics → project_matching → project_updates → artifacts → done
                              ▲                    ▲
                              └── covered here ────┘
```

> **Note:** Call 1 of a project SKIPS both stages. `aggregate_topics` auto-advances directly from `call_topics` to `artifacts` because there are no previous project topics to match against.

---

## Walked example — Acme Migration project

Three calls in sequence, illustrating the typical flows.

### Call 1 — "Kickoff with Acme"

Transcript discusses: data migration timeline, security audit, legacy DB sunset.

| Stage | What happens |
|---|---|
| `call_topics` | LLM extracts 3 topics: *Data migration timeline*, *Security audit*, *Legacy DB sunset* |
| Save & Continue | `aggregate_topics` sees no prior topics → **auto-advance** to `artifacts`. Calls `save_topics` directly which inserts 3 rows in `topics` + 3 in `topic_updates`. |
| `project_matching` | **SKIPPED** |
| `project_updates` | **SKIPPED** |

DB state after Call 1:
```
topics:        3 rows  (data migration, security audit, legacy DB sunset)
topic_updates: 3 rows  (one per topic, all linked to Call 1)
```

---

### Call 2 — "Acme weekly sync"

Transcript discusses: migration progress, audit findings, plus a new performance testing topic.

#### Step 1: `call_topics`

LLM extracts 3 new call topics:
- *Migration timeline update*
- *Security audit findings*
- *Performance testing kickoff*

Save & Continue → `aggregate_topics` sees prior topics exist → writes them to `calls.pending_topics`, advances to `project_matching`.

#### Step 2: `project_matching`

**INPUT (loaded on mount):**

| Source | Endpoint | What it returns |
|---|---|---|
| Existing project topics | `GET /api/projects/{pid}/topics/prior-to-call/{cid}` | 3 topics from Call 1 (latest update for each: tasks, OQ, decisions, summary) |
| This call's pending topics | `GET /api/calls/{cid}/topics/pending` | The 3 just extracted (from `calls.pending_topics`) |
| Previous match groups | `GET /api/calls/{cid}/topics/match-groups` | `[]` (first visit) |

**UI (left column = project, right column = this call):**

```
   PROJECT TOPICS                  THIS CALL'S TOPICS
   ─────────────────────────       ─────────────────────────────
   ● Data migration timeline       ● Migration timeline update
   ● Security audit                ● Security audit findings
   ● Legacy DB sunset              ● Performance testing kickoff
```

**Manual actions (no LLM):**
- Click `Data migration timeline` (left) + `Migration timeline update` (right) → **Link** → group #1
- Click `Security audit` (left) + `Security audit findings` (right) → **Link** → group #2
- Click `Performance testing kickoff` (right) only → **New** → group #3
- `Legacy DB sunset` not selected anywhere → will be classified as *not-discussed*

Local React state ends with:
```
groups = [
  { project_topic_ids: [<migration-id>], call_topic_names: ["Migration timeline update"] },
  { project_topic_ids: [<security-id>],  call_topic_names: ["Security audit findings"] },
  { project_topic_ids: [],               call_topic_names: ["Performance testing kickoff"] },
]
```

Click Save & Continue → `POST /api/calls/{cid}/topics/save-matches`.

**Backend (`save_match_groups`):**
1. `DELETE topic_match_groups WHERE call_id=cid` (idempotent)
2. `INSERT` one row per group (note: `call_topic_names` is lowercased on write)
3. `UPDATE calls.kanban_stage = 'project_updates'`
4. `UPDATE calls.verification_status = 'processing'`
5. Spawns `BackgroundTask` → `run_verification_background(call_id)`

**Background: `verify_not_discussed_topics`**

For each project topic NOT in any match_group (here: `Legacy DB sunset`):
```
LLM call ← not_discussed_check prompt
           + topic name = "Legacy DB sunset"
           + topic summary = "..."
           + FULL TRANSCRIPT of Call 2

→ { discussed: bool, transcript_excerpt, reasoning }
```

Result written to `calls.verification_cache` (JSONB keyed by topic_id).
`calls.verification_status = 'done'`.

> ⚠️ **This is where the Groq 413 errors come from.** The full transcript is sent for EACH not-discussed topic. With Groq llama-3.3-70b free tier at 12000 TPM, ~14k-token transcripts blow the budget. See [Resolution chain](#llm-resolution-chain) below.

#### Step 3: `project_updates`

**INPUT (loaded on mount):**

Same 3 queries as before (match_groups, pending, prior topics) plus reads `calls.merge_cache` and `calls.verification_cache`.

If `merge_cache=null`: triggers `POST /merge-preview` to compute it. UI polls every 3s until `merge_status='done'`.

**Backend (`run_merge_preview`):**

For each match_group, ONE LLM call (`project_topics` merge prompt):

| Group | Type | LLM behavior |
|---|---|---|
| #1 (migration link) | **1:1** | Merge *existing migration topic + lineage evidence + new call topic data* → updated topic. Returns `topic_id` = existing UUID. |
| #2 (security link) | **1:1** | Same pattern. Returns existing UUID. |
| #3 (performance new) | **new** (single call topic) | Pass-through (no LLM). Returns `topic_id=None`. |

After all merges, appends every project topic NOT matched as `{...t, not_discussed: True}` → here `Legacy DB sunset` gets appended.

Result written to `calls.merge_cache`. UI displays 4 sections:
1. **Followed up** (1:1 merges) — Migration timeline + Security audit
2. **Merged** (M:N consolidations) — empty
3. **New** — Performance testing kickoff
4. **Not discussed in this call** — Legacy DB sunset (with verification result inline)

User can:
- Edit any field inline (name, summary, tasks, OQ, decisions)
- Promote a not-discussed topic to followed-up
- Re-run not-discussed check (if it failed — Groq rate limit etc)

Save & Continue → `POST /validate-updates` with the (potentially edited) topics array.

**Backend (`validate_project_updates`):**
1. `DELETE topic_updates WHERE call_id=cid` (idempotent re-save)
2. Orphan cleanup on topics with no remaining updates
3. Filter out `not_discussed` topics (they don't get a `topic_update` row for this call)
4. For each remaining → `TopicUpdate(...)` → `save_topics()`:
   - `topic_id` set → just `INSERT` a new `topic_updates` row
   - `topic_id` is None → `INSERT topics` row first, then `topic_updates`
5. `UPDATE calls.kanban_stage = 'artifacts'`

DB state after Call 2:
```
topics:        4 rows  (3 from Call 1 + Performance testing new)
topic_updates: 6 rows  (3 from Call 1 + migration update + security update + performance new)
topic_match_groups: 3 rows (PRESERVED)
calls.pending_topics, merge_cache, verification_cache: PRESERVED
Legacy DB sunset: NO new topic_update for Call 2 (calls_open stays at previous count)
```

---

### Call 3 — "Mid-project review" (M:N merge scenario)

Transcript reveals that *Data migration timeline* and *Legacy DB sunset* are actually the same effort and should be consolidated.

#### `call_topics`

Extracts 2 topics:
- *Migration & DB sunset consolidation*
- *Security wrap-up*

#### `project_matching`

**UI:**
```
   PROJECT TOPICS                              THIS CALL'S TOPICS
   ─────────────────────────                   ───────────────────────────────────
   ● Data migration timeline   ─┐              ● Migration & DB sunset consolidation
   ● Security audit             │              ● Security wrap-up
   ● Legacy DB sunset          ─┤
   ● Performance testing        │
                                │
   selected ────────────────────┘
```

**Manual actions:**
- Click `Data migration timeline` + `Legacy DB sunset` (left, 2 topics) + `Migration & DB sunset consolidation` (right) → **Merge** → group #1 (M:N)
- Click `Security audit` (left) + `Security wrap-up` (right) → **Link** → group #2 (1:1)
- `Performance testing` left over → will be classified as *not-discussed*

Save & Continue → triggers `verify_not_discussed_topics` for *Performance testing*.

#### `project_updates`

**`run_merge_preview` calls:**

| Group | Type | LLM behavior |
|---|---|---|
| #1 (M:N merge) | **M:N** | Merge *2 existing topics' lineage evidence + 1 new call topic* → new consolidated topic. Returns `topic_id=None` + `_source_topic_ids: [migration-id, sunset-id]`. |
| #2 (security 1:1) | **1:1** | Standard 1:1 merge. Returns existing security UUID. |

UI shows:
1. **Followed up** — Security wrap-up
2. **Merged** — Migration & DB sunset consolidation (badge: "merged from 2 topics")
3. **New** — empty
4. **Not discussed in this call** — Performance testing

User reviews, saves → `validate_project_updates`:

1. For the **M:N entry** (topic_id=None + _source_topic_ids has 2 entries):
   - Inserts a new `topics` row → new UUID `<new-merged-id>`
   - Inserts `topic_update` linked to `<new-merged-id>` for Call 3
   - For each `_source_topic_ids`: `UPDATE topics SET archived=true, merged_into_topic_id=<new-merged-id>`
2. For the **1:1 entry** (topic_id=security-id):
   - Inserts `topic_update` for Call 3 linked to existing security topic
3. *Performance testing* — no topic_update for Call 3 (stays as carry-over)

DB state after Call 3:
```
topics:
  ─ <new-merged-id>           archived=false, name="Migration & DB sunset consolidation"
  ─ <data-migration-id>       archived=true,  merged_into_topic_id=<new-merged-id>
  ─ <legacy-sunset-id>        archived=true,  merged_into_topic_id=<new-merged-id>
  ─ <security-id>             archived=false
  ─ <performance-id>          archived=false

topic_updates: 8 rows total
  ─ Call 1: 3 (one per original topic)
  ─ Call 2: 3 (migration, security, performance — Legacy DB sunset has no Call 2 update)
  ─ Call 3: 2 (new merged topic + security update — Performance has no Call 3 update)
```

`topic_lineage` walks `merged_into_topic_id` backwards, so when you view the new merged topic in the timeline you see evidence from Call 1 (the 2 archived ancestors) + Call 3 (the merge result), not Call 2 (it wasn't a participant in the lineage).

---

## Stage diagrams

### `project_matching`

```
┌─────────────────── INPUT (load on mount) ────────────────────────┐
│                                                                  │
│  GET /api/projects/{pid}/topics/prior-to-call/{cid}              │
│     ↳ list_topics_prior_to_call → existing project topics        │
│        AS OF this call's matching time (tasks, OQ, decs, etc)    │
│                                                                  │
│  GET /api/calls/{cid}/topics/pending                             │
│     ↳ get_pending_topics → calls.pending_topics                  │
│        (= what was extracted in call_topics + your edits)        │
│                                                                  │
│  GET /api/calls/{cid}/topics/match-groups                        │
│     ↳ restore after rollback (empty on first visit)              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────── PROCESS (manual — no LLM) ────────────────────┐
│                                                                  │
│  Two-column UI (left=project, right=this call).                  │
│  Select 1+ topics each side then:                                │
│     • Link  → 1 project ↔ 1 call (followed-up)                   │
│     • Merge → N project ↔ N call (M:N consolidation)             │
│     • New   → 0 project ↔ 1+ call (new topic)                    │
│                                                                  │
│  Local React state:                                              │
│    groups = [                                                    │
│      { project_topic_ids: [...], call_topic_names: [...] },      │
│      ...                                                         │
│    ]                                                             │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                            │
                            ▼  (Save & Continue)
┌─────────────────── OUTPUT (POST /save-matches) ──────────────────┐
│                                                                  │
│  save_match_groups(call_id, groups):                             │
│    1. DELETE topic_match_groups WHERE call_id=cid                │
│    2. INSERT 1 row per group (call_topic_names lowercased)       │
│    3. UPDATE calls.kanban_stage = 'project_updates'              │
│    4. UPDATE calls.verification_status = 'processing'            │
│    5. BackgroundTask → run_verification_background               │
│                                                                  │
│  ─── Background: verify_not_discussed_topics ───                 │
│      For each project topic NOT in any match_group:              │
│        LLM call ← {not_discussed_check prompt,                   │
│                    topic.name, topic.summary,                    │
│                    FULL TRANSCRIPT}                              │
│        → {discussed, transcript_excerpt, reasoning}              │
│      Write to calls.verification_cache (JSONB by topic_id)       │
│      Set calls.verification_status = 'done'                      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### `project_updates`

```
┌─────────────────── INPUT (load on mount) ────────────────────────┐
│                                                                  │
│  Re-fetches match_groups + pending + prior topics for context.   │
│                                                                  │
│  Reads calls.merge_cache + calls.verification_cache.             │
│  If merge_cache=null + merge_status≠'processing':                │
│    POST /merge-preview → run_merge_preview                       │
│  If merge_status='processing': poll every 3s.                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────── PROCESS (LLM pool) ───────────────────────────┐
│                                                                  │
│  run_merge_preview(call_id):                                     │
│                                                                  │
│  Per match_group: ╔═══════════════════════════════════════════╗  │
│                   ║  "new" (0 project topics)                 ║  │
│                   ║    • 1 call topic   → pass-through        ║  │
│                   ║    • N call topics  → 1 LLM merge call    ║  │
│                   ║                                           ║  │
│                   ║  "1:1" (1 project, N call)                ║  │
│                   ║    • LLM merge: existing + RAG lineage    ║  │
│                   ║      evidence + new call data             ║  │
│                   ║                                           ║  │
│                   ║  "M:N" (N project, M call)                ║  │
│                   ║    • LLM merge all into 1 new topic.      ║  │
│                   ║      _source_topic_ids attached for the   ║  │
│                   ║      validate step to archive sources.    ║  │
│                   ╚═══════════════════════════════════════════╝  │
│                                                                  │
│  Append project topics NOT in any group as { ...t,               │
│  not_discussed: True } at the end of the result.                 │
│                                                                  │
│  UI displays 4 sections:                                         │
│    1. Followed up (1:1 merges)                                   │
│    2. Merged (M:N)                                               │
│    3. New                                                        │
│    4. Not discussed in this call (incl. ✕ Check failed badge     │
│       if verify_not_discussed failed)                            │
│                                                                  │
│  User can edit inline, promote not-discussed, re-run check.      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                            │
                            ▼  (Validate)
┌─────────────────── OUTPUT (POST /validate-updates) ──────────────┐
│                                                                  │
│  validate_project_updates(call_id, topics):                      │
│    1. DELETE topic_updates WHERE call_id=cid (idempotent)        │
│    2. Orphan cleanup on topics without remaining updates         │
│    3. Filter out not_discussed (no topic_update created)         │
│    4. For each → TopicUpdate(...) → save_topics():               │
│       • M:N (_source_topic_ids set): after save, UPDATE source   │
│         topics SET archived=true, merged_into_topic_id=<new>     │
│    5. UPDATE calls.kanban_stage = 'artifacts'                    │
│                                                                  │
│  DB state:                                                       │
│    topics: new rows for new topics + archived flags for M:N      │
│    topic_updates: 1 per discussed topic (incl. OQ + decisions)   │
│    topic_match_groups, pending_topics, merge_cache,              │
│      verification_cache: ALL PRESERVED                           │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## LLM resolution chain

The 3 LLM-using endpoints in these 2 stages share the SAME resolution. The library default is NOT consulted at runtime.

```
artifact_types row for this category (per-project)
    ↓ if llm/model is null
projects.default_llm + default_model
    ↓ if null
system_settings.default_llm + default_model
    ↓ if null
"openrouter" hardcoded fallback
```

| Endpoint | Category | When called |
|---|---|---|
| `run_verification_background` | `not_discussed_check` | bg task at end of `project_matching` |
| `run_merge_preview` | `project_topics` | bg task at start of `project_updates` |
| `_verify_merged_topics` | `merge_verification` | optional pass inside `merge_preview` |

> The `artifact_library` rows (the "library" UI) define defaults at project-creation time only — they ARE used by `seed_defaults` to populate `artifact_types`, but never re-consulted afterwards. Edit `artifact_types` rows directly (per-project workflow prompts page) or the project's `default_llm` to change runtime behavior.

---

## Rollback behavior

Each `rollback_to_stage(call_id, target)` keeps the data that defines the target stage and clears everything past it.

| Target stage | match_groups | pending_topics | merge_cache | verification_cache | topic_updates |
|---|---|---|---|---|---|
| `artifacts` | kept | kept | kept | kept | kept |
| `project_updates` | kept | kept (rebuilt if null) | cleared | cleared | DELETED |
| `project_matching` | kept | kept (rebuilt if null) | cleared | cleared | DELETED |
| `call_topics` | DELETED | DELETED (after restore to extraction_cache) | cleared | cleared | preserved |

This is why `GET /match-groups` returns data after a rollback to `project_matching` — the rows survived.
