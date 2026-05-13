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
| ERR-005 | LOGIC | K parallel "blind" LLM calls cross-attribute the same output to multiple inputs | Resolved (by rollback) | 2026-05-13 | EPIC-13 |

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

### ERR-005: K parallel "blind" LLM calls cross-attribute the same output to multiple inputs

**Symptom:** During EPIC-13 testing on Call 2 of project WGS07, the differential pipeline marked the same new action ("Mark: send SO1/SO2/SO3 production PA documents") as NEW under three different prior topics simultaneously. Same pattern for "Mark: assemble and send a representative sample composite" — appeared NEW under three different priors. Paraphrased restatements of existing items were also flagged NEW (e.g. "Team: review SO7 doc" marked NEW despite a prior next-step saying the same thing in different words).

**Root Cause:** EPIC-13 Step 2 invokes K parallel LLM calls — one per prior topic — each asking "was I discussed? what's new about me?". Each parallel call receives only its own prior + the full transcript; it is **structurally blind to the K−1 sibling calls**. When a single fact in the transcript plausibly relates to multiple priors, every parallel call independently claims it. Prompt-tightening cannot fix this because the LLM cannot see what its siblings are concluding. The bug is in the design shape, not the prompt.

**Fix Applied**
- **Date fixed:** 2026-05-13
- **Resolution:** Rolled back EPIC-13 in full. Branch parked as `epic-13-pipeline-trust` for archival reference. Future redesign reverses the direction: one global pass extracts topics from the call, then each extracted topic is matched against the prior set with at most one prior target. See ADR-003.

**Prevention Rule**
> 🔒 **RULE ERR-005:** When designing a "for each X, do Y" pipeline step that uses parallel LLM calls, first ask: **can the same Y output legitimately belong to multiple Xs?** If yes — K-parallel-blind is structurally broken. Three acceptable patterns:
> 1. **Single global LLM call** that sees all Xs and emits Ys with explicit attribution to ≤1 X.
> 2. **Inverted direction** — iterate over the OUTPUT space (Ys) instead of the input space (Xs), so each Y has one home by construction. (This is the planned next-iteration direction for this pipeline.)
> 3. **K parallel calls + deterministic post-pass dedup** — only safe when "same output" is detectable with high precision via normalised string comparison. Not safe when paraphrase or semantic equivalence is involved.
>
> **Related rule:** for any LLM pipeline that may exhibit cross-attribution, paraphrase-as-new, or similar quality bugs, golden-transcript regression fixtures are not optional. A 30-minute fixture with overlapping topics would have caught ERR-005 before a single UI line was written. Maintain ≥2 fixtures with hand-verified expected outputs; run them in CI on every pipeline change.

---

## 🔒 Prevention Rules Summary
| Rule ID | Applies To | Rule |
|---|---|---|
| ERR-001 | `frontend/src/api/client.ts` | All `proxyFetch()` paths must include `/api` prefix |
| ERR-002 | `frontend/` CSS + PostCSS | Tailwind v4: use `@import "tailwindcss"` + `@tailwindcss/postcss` |
| ERR-003 | `run_transcription.sh` / any server script | Auto-create venv in launch script; verify server starts on clean checkout before closing story |
| ERR-004 | Any frontend bucket-move action (promote/demote/reclassify) | Must persist to backend — never rely on React local state alone |
| ERR-005 | Any LLM pipeline with "for each X, do Y" parallel calls | Ensure Ys have ≤1 home — use global call, invert direction, or deterministic dedup. Golden fixtures mandatory. |

---

## 📊 Error Patterns
| Pattern | Count | Root Cause Theme | Systemic Fix |
|---|---|---|---|
