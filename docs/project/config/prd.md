# PRD — Call Tracker
> **Status:** `[ ] Draft` → `[ ] Reviewed` → `[ ] Locked`
> ⚠️ Once LOCKED, changes require a dated amendment at the bottom.

---

## 1. Project Summary

| Field | Value |
|---|---|
| **Project name** | Call Tracker |
| **One-liner** | A solo-use web app that turns raw client call recordings into structured artifacts and a living topic dashboard |
| **Owner** | Louis |
| **Target completion** | TBD |
| **Tech stack** | Next.js (Vercel) · FastAPI (Railway) · Supabase (PostgreSQL) · Claude API |

---

## 2. Goals & Non-Goals
> *This section is LAW for the AI. It will not build non-goals.*

### ✅ Goals (In Scope)
- **G1:** Full kanban pipeline per call — from transcript upload to Done — tracking each call's processing stage
- **G2:** AI-generated artifacts per call (via Claude API), with per-artifact progress, review, edit, and approval
- **G3:** Living topic dashboard aggregating key themes and follow-up items across all calls in a project
- **G4:** Editable prompt system — artifact type prompts and topic extraction prompt configurable per project
- **G5:** Multi-project support — each project is an independent engagement with its own calls and topics

### ❌ Non-Goals (Out of Scope — do NOT implement)
- **NG1:** No authentication or user accounts — solo-use tool, no login required
- **NG2:** No audio playback or processing inside the app — MP3 stays on local machine, never uploaded
- **NG3:** No speech-to-text inside the app — the external `transcribe_watcher.py` tool handles this; app only accepts .txt
- **NG4:** No real-time collaboration or multi-user access
- **NG5:** No mobile app — web only
- **NG6:** No export, sharing, or PDF generation in v1
- **NG7:** No Supabase Storage — all file storage excluded; transcripts stored as text in DB
- **NG8:** No artifact re-generation — user edits or pastes content directly; no re-run of Claude on existing artifacts

---

## 3. User Stories

### Must Have (MVP)

| ID | Story | Acceptance Criteria |
|---|---|---|
| US-01 | As a user, I want to create and manage projects so that I can track calls per client engagement | - [ ] Can create a project with a name and description <br>- [ ] Project appears in the project list <br>- [ ] Can open a project to see its kanban board |
| US-02 | As a user, I want to load either an MP3 or a .txt to create a call card so that I can start processing a call | - [ ] File picker accepts .mp3 or .txt <br>- [ ] If MP3: local FastAPI endpoint runs Whisper + pyannote transcription, produces transcript, stores it — card advances automatically <br>- [ ] If .txt: transcript stored directly — card advances immediately <br>- [ ] Both paths produce the same result: transcript stored in Supabase, call card ready for Artifacts stage |
| US-03 | As a user, I want to select which artifact types to include for a call and choose how each is generated so that I control token usage | - [ ] All 6 artifact types shown with two options each: "Generate via Claude" or "Manual" <br>- [ ] Can also deselect an artifact entirely (exclude it from this call) <br>- [ ] Selection and mode saved per call |
| US-04 | As a user, I want Claude-selected artifacts to generate simultaneously so that I don't wait sequentially | - [ ] Only artifacts set to "Generate via Claude" trigger API calls <br>- [ ] All Claude artifacts start generating at the same time <br>- [ ] Each artifact shows its own progress status (pending / generating / done / error) via SSE <br>- [ ] Manual artifacts show an empty editable field immediately <br>- [ ] Partial success is visible — one failure does not block others |
| US-05 | As a user, I want to review, edit, and mark each artifact as done so that I validate output before moving on | - [ ] Each artifact is editable inline (both Claude-generated and manual) <br>- [ ] Can paste content into manual artifacts <br>- [ ] Can mark individual artifacts as Done <br>- [ ] Call card cannot advance past Artifacts until all included artifacts are marked Done |
| US-06 | As a user, I want extracted topics to be reviewed and validated before the call is marked Done so that the topic dashboard stays accurate | - [ ] Topics are extracted automatically after artifacts are done <br>- [ ] On Call 1: fresh extraction from transcript + artifacts <br>- [ ] On Call 2+: existing topics checked for updates, new ones surfaced <br>- [ ] User can add, edit, remove topics before confirming <br>- [ ] Call moves to Done only after topic validation |
| US-07 | As a user, I want to see all calls as a kanban board so that I know where each call is in the pipeline | - [ ] Kanban columns: Get Transcript · Artifacts · Topics · Done <br>- [ ] Each call is a card with title and current stage <br>- [ ] Can open a card to see its detail view |

### Should Have

| ID | Story | Acceptance Criteria |
|---|---|---|
| US-10 | As a user, I want to see the Topic Dashboard for a project so that I get a bird's-eye view of all themes across calls | - [ ] Dedicated tab at project level <br>- [ ] Each topic shows: first raised (which call), latest status/update, open follow-up items <br>- [ ] Can expand a topic to see its per-call history |
| US-11 | As a user, I want to edit artifact type prompts so that the AI output matches my specific needs | - [ ] Can view the prompt behind each artifact type <br>- [ ] Can edit the prompt inline <br>- [ ] Edited prompt is used on the next generation <br>- [ ] Original prompt snapshot is preserved on already-generated artifacts |
| US-12 | As a user, I want to create new artifact types so that I can extend the system for different call types | - [ ] Can add a new artifact type with a name and prompt <br>- [ ] New type appears in the artifact selector for future calls |

### Nice to Have (v2 — do NOT build in v1)

| ID | Story | Notes |
|---|---|---|
| US-20 | Per-project prompt overrides | Different prompts per client engagement |
| US-21 | Re-generate individual artifact | Removed — edit/paste is sufficient |
| US-22 | Export call summary as markdown/PDF | Defer to v2 |
| US-23 | Archive / close a project | Defer to v2 |

---

## 4. Functional Requirements

- **FR-01:** The system shall allow creation, viewing, and deletion of projects
- **FR-02:** The system shall accept either an MP3 or .txt file to create a call record. If MP3: a local FastAPI endpoint (running on the user's machine) transcribes it using Whisper + pyannote and stores the resulting transcript. If .txt: transcript is stored directly. Both paths store transcript text in Supabase and advance the card.
- **FR-03:** The system shall display call cards in a 4-column kanban: Get Transcript · Artifacts · Topics · Done
- **FR-04:** The system shall seed 6 global default artifact types at app launch: (1) Executive Summary, (2) Next Steps / Action Items, (3) Questions for Stakeholders, (4) Email Summary (1-pager), (5) Email Follow-up (pre-next-call), (6) Next Call Meeting Invite Topics. For each call, the user sets each artifact to: Generate via Claude · Manual · Excluded.
- **FR-05:** The system shall generate all "Generate via Claude" artifacts simultaneously via Claude API, streaming per-artifact status to the frontend via SSE. Manual artifacts skip the API and present an empty editable field immediately.
- **FR-06:** The system shall allow the user to edit artifact content inline (or paste in externally generated content) and mark each as Done
- **FR-07:** The system shall block advancement from the Artifacts stage until all selected artifacts are marked Done
- **FR-08:** The system shall extract topics via Claude API after the Artifacts stage is complete
- **FR-09:** On the first call of a project, the system shall extract topics fresh; on subsequent calls, it shall check existing topics for updates and surface new ones
- **FR-10:** The system shall require topic validation before a call card moves to Done
- **FR-11:** The system shall aggregate all validated topics into a project-level Topic Dashboard, showing first raised, latest update, and open follow-up items per topic
- **FR-12:** The system shall allow the user to add, edit, and delete artifact types and their associated prompts
- **FR-13:** The system shall store the exact prompt used at generation time on each artifact record (immutable — changes to prompts do not alter past artifacts)
- **FR-14:** The system shall log all errors and surface user-friendly messages — no raw stack traces in the UI

---

## 5. Non-Functional Requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-01 | Performance | Artifact generation (5 artifacts in parallel) should complete within 60 seconds under normal Claude API conditions |
| NFR-02 | Reliability | Each artifact generation is independent — one failure must not block others; failed artifacts show error state with retry |
| NFR-03 | Security | Claude API key stored in Railway environment variables only — never sent to or stored on the frontend |
| NFR-04 | Security | Supabase connection strings and service role key stored in environment variables — never committed to source |
| NFR-05 | Observability | All FastAPI requests and Claude API calls logged with timestamp, status, and duration |
| NFR-06 | Availability | Cold starts on Railway/Vercel are acceptable — solo-use tool, no SLA required |
| NFR-07 | Data integrity | Prompt snapshot stored immutably on each artifact — editing a prompt template never mutates past artifacts |

---

## 6. Data Requirements

| Dataset | Source | Format | Volume | Notes |
|---|---|---|---|---|
| Transcripts | User upload (.txt) | Plain text | ~5–50KB per call | Stored as text in Supabase |
| Artifacts | Claude API output | Text (markdown) | ~0.5–5KB per artifact | Stored with prompt snapshot |
| Topics | Claude API extraction | Structured text | ~10–20 topics per project | Per-call update history kept |

**Data constraints:**
- Transcripts are read-only after upload
- Artifact content is editable by user but prompt snapshot is immutable
- No PII beyond what the user's own transcripts contain — user is responsible for their data

---

## 7. Interfaces & Integrations

| System | Direction | Method | Auth |
|---|---|---|---|
| Claude API | Outbound | REST (Anthropic SDK) | API key in Railway env |
| Supabase (PostgreSQL) | Read/Write | Supabase Python client (FastAPI) + Supabase JS client (Next.js, read-only queries) | Service role key (.env) |
| Vercel | Deploy | Git push (main branch) | Vercel account |
| Railway | Deploy | Git push (main branch) | Railway account |
| Local FastAPI (transcription) | Outbound from browser | REST (`localhost`) | None — local only |

---

## 8. Error Handling Policy

- All errors must be caught and logged — no silent failures
- User-facing errors must show a clear, actionable message — never a raw stack trace
- Failed artifact generation: show error state per artifact with a retry button; do not block other artifacts
- Failed topic extraction: show error with retry; do not auto-advance the call card
- Network/SSE disconnection during generation: frontend reconnects and polls for current artifact status

---

## 9. Constraints

- Solo-use only — no authentication, no multi-user, no row-level security required
- MP3 transcription runs on a local FastAPI endpoint (user's machine) — MP3 never sent to Railway
- Transcription requires Whisper + pyannote models installed locally (same stack as existing `transcribe_watcher.py`)
- No Supabase Storage — all data in PostgreSQL as text/JSON
- Claude API rate limits must be respected — implement basic retry with backoff on 429s
- Next.js deployed to Vercel; FastAPI deployed to Railway — no self-hosted infra
- No new packages added to the project without prior approval in `workflow/ADR.md`

---

## 10. Open Questions

| # | Question | Owner | Deadline | Answer |
|---|---|---|---|---|
| Q1 | Which Claude model for artifact generation and topic extraction? | Louis | Before architecture | `claude-sonnet-4-6` for both |
| Q2 | Default artifact types — global or per-project? | Louis | Before architecture | 6 global defaults seeded at app launch (see FR-04) |
| Q3 | Re-generate artifact or edit-only? | Louis | Before architecture | Edit-only — user can also paste in externally generated content |
| Q4 | Call naming convention | Louis | Before architecture | User-defined title — typically the date of the call |

---

## 📝 Amendments Log

| Date | Change | Reason |
|---|---|---|
| | | |

---

## 📤 Outputs for 3-ARCHITECTURE.md

| PRD Section | → Architecture input |
|---|---|
| Stack (§1) | Section 1 — Tech stack decisions |
| Functional Requirements (§4) | Section 3 — Component breakdown |
| Non-Functional Requirements (§5) | Section 10 — Performance & scalability |
| Data Requirements (§6) | Section 4 — Data model |
| Interfaces & Integrations (§7) | Section 8 — Key technical decisions |
| Error Handling (§8) | Section 8 — Error handling approach |
| Constraints (§9) | Section 1 — Stack limitations |
| User Stories (§3) | Section 2 — User flows |
