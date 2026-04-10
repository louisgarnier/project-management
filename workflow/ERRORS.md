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

## 🔒 Prevention Rules Summary
| Rule ID | Applies To | Rule |
|---|---|---|
| ERR-001 | `frontend/src/api/client.ts` | All `proxyFetch()` paths must include `/api` prefix |
| ERR-002 | `frontend/` CSS + PostCSS | Tailwind v4: use `@import "tailwindcss"` + `@tailwindcss/postcss` |
| ERR-003 | `run_transcription.sh` / any server script | Auto-create venv in launch script; verify server starts on clean checkout before closing story |

---

## 📊 Error Patterns
| Pattern | Count | Root Cause Theme | Systemic Fix |
|---|---|---|---|
