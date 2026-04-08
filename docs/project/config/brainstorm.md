# Brainstorm — Call Tracker
**Status:** `[x] GO — Proceed to PRD`

---

## 0. Freeform Input

Solo-use web app to manage and process client project calls. Structured kanban pipeline from raw audio to organized artifacts. Living topic dashboard that aggregates themes across all calls in a project. Stack already decided: Next.js / FastAPI / Supabase / Claude API.

Key constraints confirmed:
- Hosted: Next.js on Vercel, FastAPI on Railway
- MP3 files stay local — only filename stored in DB, never uploaded
- Transcripts (.txt) stored in Supabase DB as text
- No Supabase Storage needed
- No authentication — solo-use tool
- Artifact generation uses SSE (FastAPI → frontend) for real-time per-artifact progress

---

## 1. The One-Liner

Call Tracker is a solo-use web app that turns raw client call recordings into structured artifacts and a living topic dashboard.

---

## 2. The Problem

- **Who has this problem?** A solo consultant/operator managing multiple ongoing client engagements, each involving recurring calls.
- **How are they solving it today?** Manually — notes scattered across docs, no structured pipeline from recording to actionable output, topics fall through the cracks between calls.
- **Why is the current solution inadequate?** No single place to track call progress, generate consistent artifacts, or see what topics have evolved across a project.
- **How often does this problem occur?** Every client call — recurring and central to the workflow.

---

## 3. The Solution

**Core workflow:**
1. User creates a project for a client engagement
2. For each call: provides a transcript (.txt) — either from the existing local `transcribe_watcher.py` tool (drops MP3 locally → auto-transcribed) or by dropping a .txt directly. This is the single first kanban step.
3. Selects artifact types to generate; Claude API generates all simultaneously — user reviews, edits, marks done
4. App extracts / updates key topics from the transcript; user validates
5. Topic Dashboard gives a bird's-eye view of all themes across all calls in the project

**What makes this different:**
- Structured, opinionated pipeline — no blank-page problem
- Artifacts and topics build incrementally per project, call by call
- Prompts are fully editable per project — adapts to how each engagement evolves

---

## 4. Assumptions & Risks

| Assumption | Risk if Wrong | Mitigation |
|---|---|---|
| User provides a .txt transcript — either from the existing local `transcribe_watcher.py` tool (MP3 → local Whisper → .txt) or a manually-created transcript | Garbled or inconsistent format degrades AI output | Validate file is non-empty text; document expected format. Watcher output format is known and consistent. |
| Claude API can generate all artifacts in parallel without rate limits | Slow or failed generation blocks progress | Per-artifact status + retry; SSE shows partial success |
| Topics can be reliably extracted and matched call-over-call by Claude | Topic drift / duplicates pollute dashboard | User always validates topics before moving to Done |
| Supabase free tier is sufficient for solo use | DB limits hit unexpectedly | Monitor row/storage counts; easy to upgrade |
| Railway + Vercel cold starts are acceptable for solo use | Slow first-load frustrates user | Keep FastAPI warm; acceptable tradeoff for free tier |

---

## 5. Feasibility Check

| Dimension | Assessment | Notes |
|---|---|---|
| **Technical complexity** | Medium | SSE, Claude API parallel calls, kanban state machine |
| **Time estimate (MVP)** | 3–4 weeks | Core pipeline first, topic dashboard second |
| **Dependencies / blockers** | Claude API key, Supabase project, Railway account | All accessible immediately |
| **Skills gap** | None — stack is known | Next.js / FastAPI / Supabase all familiar |
| **Maintenance burden** | Low | Solo-use, no auth, no multi-tenancy |

---

## 6. Go / No-Go Decision

**What does success look like?**
- Minimum (MVP done): Full pipeline works end-to-end for one call — load, transcript, generate artifacts, validate topics, Done
- Full success: Multi-project, multi-call flow with working Topic Dashboard aggregating across calls
- Failure looks like: Artifact generation is unreliable or topic tracking is too noisy to be useful

**Decision:**
```
[x] GO — The problem is real, the solution is scoped, committing to this
```

**Rationale:** Clear, bounded problem for a real solo workflow. Stack is already decided and familiar. The hardest part (Claude API + SSE) is well-understood. MVP is achievable in a few weeks.

---

## Outputs for 2-PRD.md

| Brainstorm | → PRD input |
|---|---|
| "Solo-use web app that turns raw client call recordings into structured artifacts and a living topic dashboard" | Project Summary |
| Solo consultant with recurring client calls, no structured pipeline today | Context & user story seeds |
| Claude reliability, topic drift, cold starts | Open Questions & Constraints |
| Medium complexity, 3–4 weeks, no skills gap | Non-functional requirements |
| GO — real problem, scoped solution, familiar stack | Goals framing |
