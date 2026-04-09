# Story 1.2 — Logging Foundation

**Epic:** EPIC-1 — Foundation & Logging
**Maps to plan:** Slice 1 (Foundation) + `docs/project/config/logging.md`
**Status:** `done — 2026-04-09`

---

## Goal
Logging is fully wired across all three processes before any feature code is written. Every request, DB operation, SSE event, and error produces a timestamped line in both terminal and log file.

## Acceptance Criteria
- [x] `backend/utils/logger.py` — `get_logger()`, `api_logger`, `db_logger`, `sse_logger`, `claude_logger` all exported
- [x] HTTP request/response middleware active in Railway FastAPI — every request logs `📥 METHOD /path` and `📤 METHOD /path → STATUS (Nms)`
- [x] Supabase client logs `🗄️ [DB] Supabase client initialised` on startup
- [x] `transcription/logger.py` — `get_transcription_logger()` exported, writes to `logs/transcription_YYYY-MM-DD.log`
- [x] `frontend/src/utils/logger.ts` — `logger.info/warn/error/debug/sse` all exported
- [x] `frontend/app/api/proxy/[...path]/route.ts` — logs every proxied call to Next.js terminal
- [x] `logs/` directory auto-created if missing (no crash on cold start)
- [x] Smoke test: start Railway FastAPI, hit `GET /health`, confirm log line appears in `logs/backend_YYYY-MM-DD.log`

## Tasks
- [x] Create `backend/utils/logger.py` — see `docs/project/config/logging.md` §3
- [x] Create `backend/middleware/logging_middleware.py` — HTTP request/response middleware
- [x] Wire middleware into `backend/main.py` via `BaseHTTPMiddleware`
- [x] Update `backend/database/supabase_client.py` to log on init
- [x] Create `transcription/logger.py` — see `docs/project/config/logging.md` §7
- [x] Wire transcription logging middleware into `transcription/main.py`
- [x] Create `frontend/src/utils/logger.ts` — see `docs/project/config/logging.md` §8
- [x] Create `frontend/app/api/proxy/[...path]/route.ts` — GET + POST proxy with terminal logging
- [x] Verify `logs/` auto-creation on startup (both FastAPI instances)
- [x] Run smoke test: hit `/health`, confirm `logs/backend_*.log` has entry

## Reference
Full implementation code: `docs/project/config/logging.md`

## Dev Tests
- `backend/tests/test_logging.py`:
  - Request to `/health` produces a log entry in `logs/backend_*.log`
  - Logger respects `LOG_LEVEL=WARNING` (debug/info entries suppressed)
- No frontend tests needed — verify manually via terminal output
