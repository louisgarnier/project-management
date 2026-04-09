# Story 8.2 — Deployment

**Epic:** EPIC-8 — Testing & Deployment
**Maps to PRD:** NFR-03, NFR-04, NFR-06
**Status:** `pending`

---

## Goal
Railway backend and Vercel frontend are live. The full pipeline works end-to-end in production (using the local transcription server). Setup is documented so the app can be run from scratch in < 15 minutes.

## Acceptance Criteria
- [ ] Railway: FastAPI deployed, `GET /health` returns 200 in production
- [ ] Vercel: Next.js deployed, loads project list from Railway API
- [ ] All env vars set in Railway and Vercel (no hardcoded secrets)
- [ ] `NEXT_PUBLIC_BACKEND_URL` set in Vercel to Railway URL
- [ ] CORS on Railway configured to allow Vercel domain
- [ ] `run_transcription.sh` starts local transcription server, health check passes
- [ ] `README.md` covers: what it is, how to set up Supabase, Railway, Vercel, and the local transcription server
- [ ] `.env.example` complete — every variable documented

## Tasks
- [ ] Create Railway project, set env vars (`SUPABASE_URL`, `SUPABASE_KEY`, `ANTHROPIC_API_KEY`, `LOG_LEVEL`)
- [ ] Deploy backend to Railway via git push
- [ ] Create Vercel project, set env vars (`NEXT_PUBLIC_BACKEND_URL`, `BACKEND_URL`)
- [ ] Deploy frontend to Vercel via git push
- [ ] Update CORS in `backend/main.py` to allow Vercel domain
- [ ] Smoke test full pipeline in production
- [ ] Write `README.md` with setup instructions
- [ ] Verify `run_transcription.sh` works from a clean terminal

## Dev Tests
Manual production smoke test:
- Open Vercel URL → project list loads
- Create project → persisted in Supabase
- Full call pipeline end-to-end in production
- Badge shows Online when local transcription server is running
