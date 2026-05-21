# Known Errors & Investigation Methodology

## TL;DR
1. **Check the Error Registry below** — has this been solved before?
2. **Simplify before complexifying** — minimal fix first, test, then add complexity
3. **Compare with existing code** — copy working patterns, don't invent new ones
4. **Test after every change** — one change at a time, verify each
5. **If stuck** — STOP, restore to working state, restart simpler
6. **After fixing** — add an entry to the Error Registry immediately

---

## 🔍 Investigation Methodology

> **Read this BEFORE attempting to fix ANY error.**

### Fundamental Principles

#### 1. Simplify BEFORE Complexifying
- ❌ **BAD:** Add complex solutions
- ✅ **GOOD:** Create a minimal working version first

#### 2. Compare With Existing Code
- ❌ **BAD:** Create new code without looking at how it's done elsewhere
- ✅ **GOOD:** Find similar examples in the codebase, copy the working pattern

#### 3. Test Progressively
- ❌ **BAD:** Create everything at once, test only at the end
- ✅ **GOOD:** Create one thing at a time, test after each addition

#### 4. Isolate the Problem
- ❌ **BAD:** Modify several things at the same time
- ✅ **GOOD:** Test if the problem existed before your changes

#### 5. Don't Break the Application
- ❌ **BAD:** Keep modifying even if the app no longer works
- ✅ **GOOD:** Restore immediately if the app is broken

### Checklist Before Modifying Code
- [ ] I've read the existing code to understand the pattern
- [ ] I've found similar examples in the codebase
- [ ] I will create a minimal version first
- [ ] I will test after each modification
- [ ] I know how to restore if it breaks
- [ ] I will NOT add unnecessary complexity

---

## Error Registry

## Error Index
| ID | Category | Short Description | Status | First Seen | Epic |
|---|---|---|---|---|---|
| ERR-001 | INTEGRATION | Frontend API client missing `/api` prefix on backend paths | Resolved | 2026-04-09 | EPIC-2 |
| ERR-002 | DEPENDENCY | Tailwind v4 installed but configured with v3 syntax | Resolved | 2026-04-09 | EPIC-2 |
| ERR-003 | INFRA | Transcription server fails on first run — venv never created | Resolved | 2026-04-09 | EPIC-4 |

---

## Error Categories
- **DATA** — ingestion, parsing, schema, quality issues
- **CONFIG** — missing env vars, bad config values
- **INTEGRATION** — API failures, DB connection errors
- **LOGIC** — incorrect calculations, wrong business logic
- **PERFORMANCE** — timeouts, memory issues, slow queries
- **DEPENDENCY** — package conflicts, version mismatches
- **INFRA** — deployment, environment, path issues
- **UI** — frontend rendering, state management

---

## Error Entries

### ERR-001: Frontend API client missing `/api` prefix on backend paths
**Category:** INTEGRATION
**Status:** `Resolved`
**First seen:** 2026-04-09 — EPIC-2 / Story 2.3

#### Symptoms
```
"Not Found" error when creating/listing projects in browser
```

#### Root Cause
`frontend/src/api/client.ts` used paths like `/projects` but the FastAPI backend registers all routers with prefix `/api`, so endpoints live at `/api/projects`. The proxy passes paths through verbatim, so `/projects` → `http://localhost:8000/projects` → 404.

#### Fix Applied
**Date fixed:** 2026-04-09
**Commit:** next commit
Updated all `projectsAPI` paths from `/projects` → `/api/projects`.

#### Prevention Rule
> 🔒 **RULE ERR-001:** All `proxyFetch()` paths in `client.ts` must include the full backend path including `/api` prefix (e.g. `/api/projects`, `/api/calls`). The proxy is transparent — it does not add any prefix.

---

### ERR-002: Tailwind v4 installed but configured with v3 syntax
**Category:** DEPENDENCY
**Status:** `Resolved`
**First seen:** 2026-04-09 — EPIC-2 / Story 2.3

#### Symptoms
```
All Tailwind CSS classes ignored — page renders as unstyled HTML
```

#### Root Cause
`tailwindcss@^4` was installed but the project used v3 configuration: `@tailwind base/components/utilities` in CSS and no PostCSS config. Tailwind v4 requires `@import "tailwindcss"` in CSS and `@tailwindcss/postcss` as a PostCSS plugin.

#### Fix Applied
**Date fixed:** 2026-04-09
1. `npm install --save-dev @tailwindcss/postcss`
2. Created `frontend/postcss.config.mjs` with `@tailwindcss/postcss` plugin
3. Changed `globals.css` to `@import "tailwindcss"`

#### Prevention Rule
> 🔒 **RULE ERR-002:** This project uses Tailwind v4. CSS entry must use `@import "tailwindcss"`. PostCSS config must include `@tailwindcss/postcss`. No `tailwind.config.ts` needed for basic usage.

---

### ERR-003: Transcription server fails on first run — venv never created
**Category:** INFRA
**Status:** `Resolved`
**First seen:** 2026-04-09 — EPIC-4 / Story 4.1

#### Symptoms
```
ModuleNotFoundError: No module named 'whisper'
ERROR: Application startup failed. Exiting.
```

#### Root Cause
`run_transcription.sh` assumed the venv at `transcription/.venv` already existed. Story 4.1 closed without ever running the server on a real machine — tests ran with mocked models, never with the actual venv.

#### Fix Applied
**Date fixed:** 2026-04-09
**Commit:** `2a77ca8`
Updated `run_transcription.sh` to auto-create the venv and install deps on first run if `transcription/.venv` does not exist.

#### Prevention Rule
> 🔒 **RULE ERR-003:** When closing a story that involves a runnable server, verify it actually starts on a clean checkout before closing. If it requires a venv or any one-time setup, that setup must be automated in the launch script — not left as a manual step.

**2026-04-10 follow-up (Story 4.7):** Replaced openai-whisper+pyannote with mlx-whisper. The old and new venvs are incompatible (different torch/torchaudio stacks). `run_transcription.sh` now checks `import mlx_whisper` and runs `rm -rf "$VENV"` before rebuilding if the check fails — ensures stale venvs are never reused.

---

---

### ERR-004: Promote-not-discussed state lost on re-merge or page refresh

**Symptom:** User clicks "Promote to Updated" on a not-discussed topic at Project Updates. Topic correctly moves to Updated Topics. Then — after re-running merge OR refreshing the page — the topic reverts to not-discussed and any edits made in the interim are discarded.

**Root Cause:** `handlePromote` updated only React local state. The backend's `run_merge_preview` rebuilds topic state from `topic_match_groups`. Since the promoted topic had no match group referencing it, the backend re-marked it as not-discussed on every rebuild.

**Fix Applied**
- **Date fixed:** 2026-04-21
- **Backend:** new endpoint `POST /api/calls/{id}/topics/promote-not-discussed` inserts a ptid-only match group `{project_topic_ids: [topic_id], call_topic_names: []}`. The existing merge logic already handles ptid-only groups (returns the existing topic as an Updated Topic at `topics_service.py:618-619`), so no merge-logic change needed.
- **Frontend:** `handlePromote` now awaits `topicsAPI.promoteNotDiscussed(callId, topic.topic_id)` before updating local state.
- **Tests:** `test_promote_not_discussed_inserts_ptid_only_match_group` + `test_promote_not_discussed_is_idempotent`.

**Prevention Rule**
> 🔒 **RULE ERR-004:** Any UI "bucket move" action that changes how a topic is classified (promote, demote, reclassify) must persist to the backend via a match-group or equivalent durable source of truth — never rely on React local state alone. The backend is the authority for topic classification; frontend-only flips are erased on any rebuild.

---

### ERR-005: Re-extract click doesn't switch UI to "Generating…" — spinner gated behind `!extracted` ternary

**Symptom:** On `CallTopicsStage`, user clicks Re-extract. The button label flips to "Re-extracting…" (so state IS changing), but the body keeps showing the old topic table. User has to refresh the page to see the "Generating…" spinner. First seen + patched in commit `9e4b886` (set polling=true before await + guard the cache-sync useEffect). The fix did NOT survive cleanly into Story 15.5's 3-section restructure — the body branching remained `{!extracted ? (...spinner...) : (...topics...)}`, which meant any race that left `extracted=true` for even one render would mask the spinner.

**Root Cause:** Two compounding factors:
1. The spinner was nested inside the `!extracted` branch (`{!extracted ? (polling ? spinner : button) : topics}`). So the spinner could only render if `extracted` was already false at render time.
2. Even with `setExtracted(false)` + `setPolling(true)` fired synchronously in `handleReExtract`, the parent `call` prop still carried the stale `extraction_status="done"` + `extraction_cache=[...]`. If anything caused a re-render before the cache-sync useEffect's bail-gate (`if (extracting || polling) return`) caught up, extracted could flip back to true and the spinner branch would never render.

**Fix Applied**
- **Date fixed:** 2026-05-19
- **Frontend:** restructured the body branching in `frontend/src/components/CallTopicsStage.tsx` so the spinner branch takes priority over `extracted`. New order: `{polling || extracting ? <spinner> : !extracted ? <button> : <topics>}`. Now the spinner CANNOT be hidden by any race that leaves `extracted=true` momentarily — as long as `polling` or `extracting` is true, the spinner wins.
- The previous `setPolling(true)` BEFORE await + `if (extracting || polling) return` cache-sync gate from `9e4b886` are still in place — they prevent stale topics from being restored. The new branching is defense-in-depth on the visible side.

**Prevention Rule**
> 🔒 **RULE ERR-005:** When a UI element represents "work in progress" (spinner, loading skeleton, etc.), its render condition must be the FIRST branch in the body ternary — independent of (and taking priority over) any state derived from a prop. Never nest a spinner inside a branch that depends on a prop-derived boolean (like `extracted` here), because any race that flips that boolean back will silently hide the spinner. Pattern: `{busyFlag ? <spinner/> : <normal-content/>}` — not `{!ready ? (busyFlag ? <spinner/> : <call-to-action/>) : <content/>}`.

---

### ERR-006: new SYSTEM_LIBRARY entry uses obsolete `context_scope: "call"` — startup seed fails + downstream side-effects

**Date:** 2026-05-21
**Symptom:** Adding a new entry to `backend/library/seed.py::SYSTEM_LIBRARY` with `context_scope: "call"` causes startup warning `artifact_library_context_scope_check` violation, and later POST /api/projects returns 500 if the seed entry was meant to be `seeded_by_default=True`.

**Root cause:** Phase 2 migration (now removed from the repo but still APPLIED to the live DB) replaced the old `context_scope IN ('call', 'project')` CHECK on `artifact_library` with a 4-value enum. Valid values today: `this_call_transcript`, `all_call_transcripts`, (and 2 more — confirm by checking existing entries). Existing rows with `"call"` are grandfathered; new inserts with `"call"` are rejected.

**Fix:** New entries must use one of the Phase 2 enum values. Use `"this_call_transcript"` for call-bounded analysis, `"all_call_transcripts"` for cross-call.

> 🔒 **RULE ERR-006:** When adding new SYSTEM_LIBRARY entries, NEVER use `context_scope: "call"` or `"project"`. Use the Phase 2 enum (`"this_call_transcript"` / `"all_call_transcripts"` / etc.). If unsure, check existing recently-added entries (Pass ①/②/③) for valid values.

---

## 🔒 Prevention Rules Summary
| Rule ID | Applies To | Rule |
|---|---|---|
| ERR-001 | `frontend/src/api/client.ts` | All `proxyFetch()` paths must include `/api` prefix |
| ERR-002 | `frontend/` CSS + PostCSS | Tailwind v4: use `@import "tailwindcss"` + `@tailwindcss/postcss` |
| ERR-003 | `run_transcription.sh` / any server script | Auto-create venv in launch script; verify server starts on clean checkout before closing story |
| ERR-004 | Any frontend bucket-move action (promote/demote/reclassify) | Must persist to backend — never rely on React local state alone |
| ERR-005 | Any "work-in-progress" UI element (spinner, skeleton) | Spinner branch must be the FIRST ternary, taking priority over prop-derived booleans — never nest behind `!extracted` / `!ready` / etc. |
| ERR-006 | `backend/library/seed.py` new SYSTEM_LIBRARY entries | Use Phase 2 enum for `context_scope` (`this_call_transcript` / `all_call_transcripts` / etc.) — never `"call"` or `"project"` (rejected by DB CHECK). |

---

## 📊 Error Patterns
| Pattern | Count | Root Cause Theme | Systemic Fix |
|---|---|---|---|
