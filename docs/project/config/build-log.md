# Build Log — Call Tracker

## Current Stage
**EPIC-2 / Story 2.1 — Projects API**
- Status: not started
- Blocked by: nothing

---

## Session History

### 2026-04-09 — EPIC-1 wrap-up + next@15 upgrade
**Completed:** EPIC-1 (Stories 1.1, 1.2, 1.3) verified and closed
**Fixes applied:**
- ruff auto-fixed 10 import-sort errors in backend/
- Recreated `backend/.env.example` (had been deleted)
- Upgraded `next@16.0.3` (CVE) → `next@15.x` (stable, 0 vulnerabilities)
- Upgraded `eslint@8` → `eslint@9` (flat config via `@eslint/eslintrc` FlatCompat)
- Created `frontend/eslint.config.mjs` replacing `.eslintrc.json`
- Fixed `frontend/src/utils/logger.ts` — ternary-as-statement → if/else
- Logged upgrade as ADR-001

**Verification (all passing):**
- 8/8 backend tests pass
- ruff: 0 errors, black: 0 changes
- ESLint (frontend): 0 errors, 0 warnings

**Next session starts at:** EPIC-2 / Story 2.1 — Projects API
