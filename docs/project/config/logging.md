# Logging Setup — Call Tracker
> **Status:** `[ ] Draft` → `[ ] Configured` → `[ ] Tested` → `[x] Locked — 2026-04-09`

---

## 1. Overview

Call Tracker has two backend processes that each need logging:
- **Railway FastAPI** (`backend/`) — main API: projects, calls, artifacts, topics, SSE streaming
- **Local FastAPI** (`transcription/`) — transcription server: Whisper + pyannote, health check

Both share the same logger configuration pattern. The Next.js frontend logs via terminal proxy and browser console.

---

## 2. Log Files

All log files live in `/logs/` at the project root (gitignored).

```
/logs/
├── backend_YYYY-MM-DD.log       # Railway FastAPI — all activity, errors, startup
├── api_YYYY-MM-DD.log           # HTTP requests/responses (both FastAPI instances)
├── database_YYYY-MM-DD.log      # Supabase operations
├── transcription_YYYY-MM-DD.log # Local Whisper/pyannote activity
├── sse_YYYY-MM-DD.log           # SSE streaming events (artifact generation)
└── frontend_YYYY-MM-DD.log      # Proxy-captured frontend → API calls
```

---

## 3. Backend Logging — Railway FastAPI

### `backend/utils/logger.py`

```python
import logging
import sys
import os
from datetime import date
from logging.handlers import TimedRotatingFileHandler

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = os.path.join(os.path.dirname(__file__), "../../logs")

def _file_handler(name: str) -> TimedRotatingFileHandler:
    os.makedirs(LOG_DIR, exist_ok=True)
    today = date.today().isoformat()
    path = os.path.join(LOG_DIR, f"{name}_{today}.log")
    handler = TimedRotatingFileHandler(path, when="midnight", backupCount=30)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    return handler

def get_logger(module: str) -> logging.Logger:
    logger = logging.getLogger(f"calltracker.{module}")
    if not logger.handlers:
        logger.setLevel(getattr(logging, LOG_LEVEL))
        logger.addHandler(logging.StreamHandler(sys.stdout))
        logger.addHandler(_file_handler("backend"))
    return logger

# Module-specific loggers
api_logger = get_logger("api")
db_logger = get_logger("database")
sse_logger = get_logger("sse")
claude_logger = get_logger("claude")
```

### `backend/middleware/logging_middleware.py`

```python
import time
import logging
from fastapi import Request

request_logger = logging.getLogger("calltracker.api.requests")

async def log_requests(request: Request, call_next):
    start = time.time()
    request_logger.info(f"📥 {request.method} {request.url.path}")
    response = await call_next(request)
    ms = (time.time() - start) * 1000
    request_logger.info(
        f"📤 {request.method} {request.url.path} → {response.status_code} ({ms:.0f}ms)"
    )
    return response
```

### `backend/main.py` — startup hook

```python
from starlette.middleware.base import BaseHTTPMiddleware
from backend.middleware.logging_middleware import log_requests
from backend.utils.logger import get_logger

logger = get_logger("startup")

@app.on_event("startup")
async def startup():
    logger.info("🚀 [Railway] Call Tracker API starting")
```

---

## 4. Supabase Database Logging

Supabase uses the Python client (not SQLAlchemy). Log at the operation level.

```python
# Pattern used in every router that touches Supabase
from backend.utils.logger import db_logger

# Before query
db_logger.debug(f"🗄️ [DB] SELECT calls WHERE project_id={project_id}")

# After query
db_logger.info(f"✅ [DB] {len(result.data)} calls fetched for project {project_id}")

# On error
db_logger.error(f"❌ [DB] Supabase error: {e}")
```

Connection singleton logs at init:

```python
# backend/database/supabase_client.py
from backend.utils.logger import db_logger

def get_client():
    db_logger.info("🗄️ [DB] Supabase client initialised")
    return create_client(SUPABASE_URL, SUPABASE_KEY)
```

---

## 5. SSE Streaming Logging

Artifact generation streams events over SSE. Each event must be logged.

```python
from backend.utils.logger import sse_logger

async def event_stream(call_id: str):
    sse_logger.info(f"🔄 [SSE] Stream opened for call {call_id}")
    try:
        for coro in asyncio.as_completed(tasks):
            event = await coro
            sse_logger.info(
                f"📤 [SSE] artifact_id={event['artifact_id']} status={event['status']}"
            )
            yield f"data: {json.dumps(event)}\n\n"
        sse_logger.info(f"✅ [SSE] Stream complete for call {call_id}")
        yield 'data: {"type":"done"}\n\n'
    except Exception as e:
        sse_logger.error(f"❌ [SSE] Stream error for call {call_id}: {e}")
        yield f'data: {{"type":"error","message":"{str(e)}"}}\n\n'
```

---

## 6. Claude API Logging

```python
from backend.utils.logger import claude_logger

async def generate_artifact(artifact_id: str, prompt: str, transcript: str):
    claude_logger.info(f"🚀 [Claude] Starting generation artifact={artifact_id}")
    try:
        response = await client.messages.create(...)
        claude_logger.info(
            f"✅ [Claude] artifact={artifact_id} tokens={response.usage.output_tokens}"
        )
        return response.content[0].text
    except anthropic.RateLimitError:
        claude_logger.warning(f"⚠️ [Claude] Rate limit hit artifact={artifact_id}, retrying")
        raise
    except Exception as e:
        claude_logger.error(f"❌ [Claude] artifact={artifact_id} failed: {e}")
        raise
```

---

## 7. Local Transcription Server Logging

`transcription/` is a separate FastAPI process. It uses its own logger writing to `transcription_*.log`.

```python
# transcription/logger.py
import logging, sys, os
from datetime import date
from logging.handlers import TimedRotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(__file__), "../logs")

def get_transcription_logger(module: str) -> logging.Logger:
    logger = logging.getLogger(f"transcription.{module}")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        logger.addHandler(logging.StreamHandler(sys.stdout))
        os.makedirs(LOG_DIR, exist_ok=True)
        today = date.today().isoformat()
        h = TimedRotatingFileHandler(
            os.path.join(LOG_DIR, f"transcription_{today}.log"),
            when="midnight", backupCount=30
        )
        h.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        logger.addHandler(h)
    return logger
```

Usage in transcription:

```python
logger = get_transcription_logger("whisper")
logger.info(f"🚀 [Transcription] Starting: {filename}")
logger.info(f"🔄 [Transcription] Whisper complete ({len(segments)} segments)")
logger.info(f"🔄 [Transcription] Diarization complete")
logger.info(f"✅ [Transcription] Done: {len(lines)} lines, {char_count} chars")
logger.error(f"❌ [Transcription] Failed: {e}")
```

---

## 8. Frontend Logging

### Next.js API Proxy — server-side terminal logs

```typescript
// frontend/app/api/proxy/[...path]/route.ts
const ts = () => new Date().toISOString().replace("T", " ").substring(0, 23);

// Logged in Next.js terminal (not browser)
console.log(`${ts()} 📡 [Frontend→API] ${method} ${fullPath}`);
console.log(`${ts()} ✅ [Frontend→API] ${method} ${fullPath} → ${status}`);
console.error(`${ts()} ❌ [Frontend→API] ${method} ${fullPath} error:`, err);
```

### Browser console logger utility

```typescript
// frontend/src/utils/logger.ts
const isDev = process.env.NODE_ENV === "development";

export const logger = {
  info:  (msg: string, data?: unknown) => isDev && console.log(`📘 ${msg}`, ...(data ? [data] : [])),
  warn:  (msg: string, data?: unknown) => console.warn(`⚠️ ${msg}`, ...(data ? [data] : [])),
  error: (msg: string, data?: unknown) => console.error(`❌ ${msg}`, ...(data ? [data] : [])),
  debug: (msg: string, data?: unknown) => isDev && console.debug(`🔍 ${msg}`, ...(data ? [data] : [])),
  sse:   (msg: string, data?: unknown) => isDev && console.log(`📡 [SSE] ${msg}`, ...(data ? [data] : [])),
};
```

---

## 9. Conventions

### Emoji key

| Emoji | Meaning |
|-------|---------|
| 📥 | Incoming request |
| 📤 | Outgoing response / SSE event sent |
| 📡 | API call / SSE connection |
| ✅ | Success |
| ❌ | Error |
| ⚠️ | Warning / rate limit |
| 🔄 | In-progress (Whisper, SSE stream, Claude generating) |
| 🗄️ | Database operation |
| 🚀 | Startup / Claude call initiated |
| 📌 | Business event |

### Module prefix format

```
[ModuleName] verb: detail
[Claude] Starting generation artifact=abc123
[DB] SELECT calls WHERE project_id=xyz
[SSE] Stream opened for call abc123
[Transcription] Whisper complete (42 segments)
```

### Never log

- Supabase service key or anon key
- Anthropic API key
- Transcript content (contains client PII)
- Raw stack traces in user-facing API responses (log internally, return clean message)

---

## 10. Environment Variables

### Railway (backend/.env)

```bash
LOG_LEVEL=INFO   # DEBUG | INFO | WARNING | ERROR
```

### Vercel (frontend/.env.local)

```bash
BACKEND_URL=https://your-railway-app.railway.app
```

### Local transcription server (.env.local in transcription/)

```bash
LOG_LEVEL=INFO
```

---

## 11. Implementation Checklist

- [ ] `backend/utils/logger.py` created with `get_logger()`, `api_logger`, `db_logger`, `sse_logger`, `claude_logger`
- [ ] `backend/middleware/logging_middleware.py` — HTTP request/response middleware wired in `main.py`
- [ ] Supabase client singleton logs on init
- [ ] SSE stream logs open / each event / close / error
- [ ] Claude service logs start / success (token count) / rate limit / error
- [ ] `transcription/logger.py` created, used throughout transcription pipeline
- [ ] `frontend/app/api/proxy/[...path]/route.ts` — proxy logs to Next.js terminal
- [ ] `frontend/src/utils/logger.ts` — browser console utility
- [ ] `logs/` directory created, added to `.gitignore`
- [ ] `LOG_LEVEL=INFO` in Railway env vars
- [ ] End-to-end smoke test: create project → verify logs appear in backend terminal + log file
