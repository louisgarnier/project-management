# Story 1.1 — Repo Scaffold & Environment

**Epic:** EPIC-1 — Foundation & Logging
**Maps to plan:** Slice 1 (Foundation)
**Status:** `pending`

---

## Goal
Project runs locally with one command per process: `uvicorn` for Railway backend, `uvicorn` for local transcription server, `npm run dev` for Next.js frontend.

## Acceptance Criteria
- [ ] Folder structure matches architecture: `backend/`, `transcription/`, `frontend/`, `logs/`, `scripts/`, `docs/`
- [ ] `backend/requirements.txt` lists all approved Python packages
- [ ] `frontend/package.json` lists all approved Node packages
- [ ] `.env.example` has every required variable with placeholder values
- [ ] `logs/` exists and is in `.gitignore`
- [ ] `ruff` + `black` pass on `backend/` with zero errors
- [ ] `eslint` + `prettier` pass on `frontend/` with zero errors
- [ ] Railway FastAPI starts and returns `{"status": "ok"}` at `GET /health`
- [ ] Local transcription FastAPI starts and returns `{"status": "ok"}` at `GET /health`
- [ ] Next.js dev server starts at `localhost:3000` without errors

## Tasks
- [ ] Create folder structure: `backend/`, `transcription/`, `frontend/`, `logs/`, `scripts/`, `docs/`
- [ ] Add `logs/` to `.gitignore`
- [ ] Scaffold `backend/` FastAPI app with `main.py`, `requirements.txt`, `.env.example`
- [ ] Scaffold `transcription/` FastAPI app with `main.py`, `requirements.txt`
- [ ] Scaffold `frontend/` Next.js 14 app with App Router, TypeScript, Tailwind
- [ ] Configure `ruff` + `black` in `backend/pyproject.toml`
- [ ] Configure `eslint` + `prettier` in `frontend/.eslintrc.json` and `frontend/.prettierrc`
- [ ] Add `GET /health` to both FastAPI instances
- [ ] Write smoke test: `pytest backend/tests/test_health.py` → HTTP 200
- [ ] Verify Next.js starts clean

## Required packages (from architecture.md — no additions without ADR)

**backend/requirements.txt:**
```
fastapi==0.111.0
uvicorn[standard]==0.29.0
supabase==2.4.2
anthropic==0.26.0
python-multipart==0.0.9
httpx==0.27.0
python-dotenv==1.0.1
```

**transcription/requirements.txt:**
```
fastapi==0.111.0
uvicorn[standard]==0.29.0
openai-whisper==20231117
pyannote.audio==3.1.1
torch==2.2.2
torchaudio==2.2.2
python-multipart==0.0.9
python-dotenv==1.0.1
```

**frontend/package.json (key deps):**
```
next@14
react@18
typescript@5
tailwindcss@3
@supabase/supabase-js@2
```

## Dev Tests
- `backend/tests/test_health.py` — GET /health → 200, body = `{"status":"ok"}`
- `transcription/tests/test_health.py` — GET /health → 200, body = `{"status":"ok"}`
