# Architecture Decision Records (ADR)

## TL;DR
- Log every significant technical decision here (if wrong = 2+ hours to undo)
- Check this BEFORE making architectural changes — don't contradict past decisions
- Never delete/modify entries — append only
- To override a past decision: add a new ADR referencing the old one

---

## ADR Index
| ID | Title | Status | Date | Epic |
|---|---|---|---|---|
| ADR-001 | Upgrade Next.js from 14 to 15 | Accepted | 2026-04-09 | EPIC-1 |
| ADR-002 | Use Supabase Storage for Call Context Files | Accepted | 2026-04-10 | EPIC-4 |
| ADR-003 | Unified project_topic_state view as single source of truth | Accepted | 2026-05-24 | EPIC-18 |
| ADR-004 | Line-number citation pattern for all cross-call verification (Pass 1) | Accepted | 2026-05-24 | EPIC-18 |
| ADR-005 | Task-level manual matching at project_matching stage | Accepted | 2026-05-25 | EPIC-19 |
| ADR-006 | Pass 3 as synthesis from bound tasks, not re-extraction | Accepted | 2026-05-25 | EPIC-19 |

---

## ADR-005 — Task-level manual matching at project_matching stage

**Date:** 2026-05-25
**Epic:** EPIC-19
**Status:** Accepted

### Context
EPIC-18's topic-level verification produced semantically-correct verdicts at 18-30% confidence due to sanity-stack compounding on a fuzzy unit (the topic). Real-data smoke on project a revealed the failure was structural: comparing topic blobs is fundamentally fuzzy. The data also showed 0/40 exact task-text matches between consecutive real calls, meaning task-level *automatic* matching also depends on LLM semantic match — but task-level *manual* matching is concrete and fast.

### Decision
project_matching becomes task-level: users manually bind candidate tasks (from v5) to existing tasks (from project_topic_state) with N:M support. Cross-topic bindings surface a modal for the topic-shape decision. LLM-driven matching is removed from this stage entirely. The 3 LLM passes downstream become safety-net verifiers (Pass 1 + 2) and synthesizer (Pass 3) — not primary matchers.

### Consequences
- User does identity work; LLM does only safety-net (Pass 1/2) + synthesis (Pass 3)
- 18-30% confidence problem dissolves (Pass 1 reflects actual match quality, no penalty stack)
- Smaller LLM cost (4 candidate topics × 1 advisory call instead of 7 × full sanity-stack)
- Workflow adds user time at matching stage (~5-10 min/call); acceptable at human-scale PMO use
- The `topic_match_groups` table is extended (migration 035) with task-level `call_task_refs` + `project_task_refs` + `kind` discriminator

### Alternatives considered
- **Task-level LLM matching:** still fragile; EPIC-18's failure modes recur at finer granularity. Real-data showed 0/40 exact text matches between consecutive calls, so the deterministic-pre-match argument fails.
- **Embedding-based semantic matching:** infra dependency; ROI unclear at scale of one PMO; deferred until needed.
- **Status quo + workflow accommodations:** ship EPIC-18 as-is and have user tolerate 18-30% review burden. Rejected as accepting mediocrity.

---

## ADR-006 — Pass 3 as synthesis from bound tasks, not re-extraction

**Date:** 2026-05-25
**Epic:** EPIC-19
**Status:** Accepted

### Context
EPIC-18 Pass 3 (`extract_topic_updates`) re-extracted task state from raw transcripts on every call. Heavy LLM work; produced spurious tasks when the LLM "discovered" things differently each call. EPIC-15's failed chronology attempts (twice) tried this approach with prompt variations; none produced coherent cross-call updates.

### Decision
Pass 3 receives the already-confirmed bindings (from matching + Pass 1/2 user overrides) + previous `topic_updates` state + ingested transcripts. It SYNTHESIZES the merged state — preserves `task_id` identity, updates fields based on new evidence. Does NOT re-discover or re-extract tasks. One LLM call per merged topic (parallelizable across topics, structured JSON inputs per Q2 + Q4 decisions).

### Consequences
- Task identity is stable across calls (`task_id` preserved through `topic_updates` chain)
- Pass 3 output structure is deterministic (one row per merged topic, exact task list from the bindings)
- LLM work narrower: synthesize + update, not extract
- Cross-call chronology is a derived view over the `topic_updates` history rather than an LLM re-generation
- Function renamed: `run_extract_topic_updates` → `run_synthesize_merged_topic`

### Alternatives considered
- **Keep re-extraction with stricter prompts:** the failure mode of EPIC-15's chronology — both attempts dropped after producing incoherent cross-call updates on real data
- **Event-sourced task model:** over-engineered for current scale; rejected during EPIC-19 brainstorm
- **Skip Pass 3 entirely; just append new tasks to topic_updates as-is:** loses synthesized topic-level summary + status rollup that the user wants for the Brief/Kanban view

---

## ADR-003 — Unified `project_topic_state` view as single source of truth

**Date:** 2026-05-24
**Epic:** EPIC-18
**Status:** Accepted

### Context
Two independent read paths existed for "what topics exist in this project":
- v5 Stage 1 (clustering) queried `topic_registry` table — names + descriptions only
- Pass 1 (`_get_previous_topics`) queried `topics` + `topic_updates` — full structural payload

These paths diverged: a topic could exist in `project_topics` but not be approved into the registry, leading Stage 5 to invent a near-duplicate name that Pass 1 had to reconcile. Wrong-canonical assignments silently corrupted state. Three separate similarity scoring implementations layered on top compounded the inconsistency.

### Decision
Create a Postgres view `project_topic_state` (migration 034) that joins `topics` + latest `topic_updates` per topic. Both v5 Stage 1 and Pass 1 consume this view through a single `backend/services/project_topic_state.py::get_project_topic_state()` API. `topic_registry` table is retained for now (Stage 6 still writes to it); future cleanup epic can sunset the table.

### Consequences
- One read shape across the system; no drift possible between consumers
- Stage 5 now sees the FULL structural payload (key_terms + tasks per topic) — enables V5-CORE behavior
- Adding/removing fields requires editing the view definition + the service (one path, not three)
- `topic_registry` table becomes write-only legacy until a future cleanup epic deprecates it

### Alternatives considered
- **Table merge** (collapse `topic_registry` into a column on `topics`): bigger migration cost; chose view for incremental safety.
- **Per-consumer caching**: would mask divergence rather than fix it.

---

## ADR-004 — Line-number citation pattern for Pass 1 verification

**Date:** 2026-05-24
**Epic:** EPIC-18
**Status:** Accepted

### Context
Pass 1's original citation contract asked the LLM to copy-paste verbatim quotes from past transcripts. The verifier ran `quote in body` strict-substring check. DeepSeek v3.2 paraphrased quotes (collapsed repeated filler, normalized punctuation, etc.) and failed verification 6/6 times on the user's 2026-05-23 same-transcript test. The architecture asked the LLM to do mechanical work (verbatim copying) it can't reliably do.

v5 (EPIC-17) had solved this for extraction by inverting responsibility: LLM emits line numbers (`evidence_lines: [start, end]`), code resolves to verbatim text via `stage_0_ingest.resolve_lines()`. Citations are byte-perfect by construction.

### Decision
Port v5's line-number pattern to Pass 1. The LLM emits `{"call_id": "<uuid>", "evidence_lines": [start, end]}` per citation. New `verify_evidence_lines()` validates with a bounds check (in-range, non-inverted). `resolve_evidence_lines()` returns verbatim text by line lookup. The LLM never reproduces transcript text in its output.

Pass 2 (`verify_not_discussed`) and Pass 3 (`extract_updates`) retain the legacy `verify_citations` string-match path — out of scope for EPIC-18, to be migrated in a future epic.

### Consequences
- Pass 1 is model-agnostic: works with DeepSeek (cost-efficient dev) and Opus (prod-quality)
- LLM context simpler: line-numbered transcripts (`0001  <text>` per line) are easier to reason about
- Cached `verify_new_cache` blobs from the old schema are unreadable — addressed by STREAM 5 migration script (one-shot reprocess)
- Pass 2/3 still architecturally broken on same failure mode until follow-up epic
- Similarity scoring also unified (ADR-003 sister change) — Stage 6 + Pass 1 share `backend/services/topic_similarity.py`

### Alternatives considered
- **Swap to Opus for Pass 1 only**: would fix verbatim quoting at runtime cost; chose structural fix because it works for any model.
- **Fuzzy-match verifier**: would mask the model problem and create false positives.
- **Atomic-unit-ID citations** (cite by v5 unit_id instead of line range): cleaner but requires v5 to have been run on every past call, which isn't true for legacy data.

---

## Planning Lessons — Specification gaps to check before every plan

These are categories of gaps that consistently cause bugs or delays. Use as a checklist when writing plans.

### Category A — External API contracts
| # | Gap to avoid | What the spec must include |
|---|---|---|
| A1 | Hardcoding API values that are owned by the external service | "Names/IDs are enum values owned by the API. Always fetch from the API — never hardcode." |
| A2 | Assuming one global unique ID per entity across accounts | "Check whether the external system scopes IDs per account or globally. Dedup must match." |
| A3 | Undefined history window for sync/import operations | "Specify: how far back on first sync, how far back on subsequent syncs, whether user can control it." |

### Category B — Infrastructure & secrets
| # | Gap to avoid | What the spec must include |
|---|---|---|
| B1 | Unspecified secret format for hosting platform | "Specify exact storage format. Document that multi-line secrets must be stored single-line and reconstructed at runtime." |
| B2 | Relying on package extras for critical transitive deps | "Always pin transitive dependencies explicitly. Never rely on extras to pull in critical packages." |
| B3 | Env var formatting issues not anticipated | "After adding any secret to the hosting platform, verify in raw editor — no trailing chars, newlines, or quotes." |

### Category C — Framework behaviour
| # | Gap to avoid | What the spec must include |
|---|---|---|
| C1 | CORS middleware ordering left implicit | "State explicitly: CORS must be the outermost middleware layer. Register it last, after all middleware decorators." |
| C2 | External client instantiation outside error handler | "Every external client call at a system boundary must be inside the error handler. No exceptions." |

### Category D — Test design
| # | Gap to avoid | What the spec must include |
|---|---|---|
| D1 | Single mock return_value reused across multiple DB calls | "State the multi-call mock rule before any test is written: use side_effect=[...] when the same chain is called more than once." |
| D2 | Assertions wrapped in conditional guards | "Never wrap assertions in conditional guards. Assert unconditionally — a missing row is a test failure, not a no-op." |

### Meta-lesson
Most bugs happen at **integration seams** — where two systems meet. Every plan must include an "Integration assumptions to verify" section per external dependency, listing format contracts, known edge cases, and how to validate before coding. See `3-ARCHITECTURE.md` Section 9.

---

## ADR Template
> Copy this block for each new decision. One ADR per significant choice.
> What counts as "significant"? If getting it wrong would cost more than 2 hours to undo — write an ADR.

---

### ADR-001: Upgrade Next.js from 14 to 15
**Date:** 2026-04-09
**Epic / Story:** EPIC-1 / Story 1.1
**Status:** `Accepted`
**Decided by:** Both

#### Context
Architecture locked `next@14`. During EPIC-1 implementation, `next@16.0.3` was installed instead. `next@16.0.3` carries an active CVE (CVE-2025-66478). Downgrading to `next@14` would mean building on an aging major. `next@15` (stable since Oct 2024) is the standard production target with no known CVEs.

#### Decision
**We will use `next@15.x` (latest stable patch) and `eslint@9.x` (flat config) instead of the originally approved `next@14` and `eslint@8.x`.**

#### Alternatives Considered
| Option | Pros | Cons | Reason Rejected |
|---|---|---|---|
| next@15 (chosen) | Stable, no CVE, React 19, ESLint 9 | Breaking changes from 14 (minor) | *Chosen* |
| next@14 | Matches original spec | Aging major, going stale | Starting a new project on old major is poor practice |
| next@16.0.3 | Latest | Active CVE (CVE-2025-66478) | Security vulnerability unacceptable |

#### Consequences
**Positive:**
- No active CVEs
- ESLint 9 flat config is cleaner long-term
- React 19 compatible

**Negative / Trade-offs:**
- Minor Next.js 14→15 migration concerns (minimal for a new project with no existing pages)

**What this decision affects:**
- `frontend/package.json` — `next`, `react`, `react-dom`, `eslint-config-next`
- `frontend/eslint.config.mjs` — flat config replaces `.eslintrc.json`

#### Review Triggers
- [ ] If a CVE is reported against next@15

---

---

### ADR-002: Use Supabase Storage for Call Context Files
**Date:** 2026-04-10
**Epic / Story:** EPIC-4 / Story 4.6
**Status:** `Accepted`
**Decided by:** Both

#### Context
Story 4.6 requires storing arbitrary binary files (PDF, DOCX, CSV, TXT, MD) attached to calls. We needed a file storage solution compatible with our existing Supabase backend. Options were: Supabase Storage (native integration), a separate S3 bucket, or storing files as base64 in the DB.

#### Decision
**We will use Supabase Storage (`call-files` private bucket) for all call context file storage. Files are uploaded via the Python backend (not directly from the browser) and accessed only via 60-second signed URLs.**

#### Alternatives Considered
| Option | Pros | Cons | Reason Rejected |
|---|---|---|---|
| Supabase Storage (chosen) | Native integration, same auth, no extra infra | Signed URL expiry needs management | *Chosen* |
| AWS S3 | Industry standard, very mature | Separate credentials, extra infra, no native Supabase link | Unnecessary complexity for this scale |
| DB blob storage | Simplest — no extra service | Binary in Postgres is slow, expensive, bad practice for large files | Poor practice for files >100KB |

#### Consequences
**Positive:**
- Single Supabase project covers DB + file storage — no extra credentials
- RLS policies can restrict file access to authenticated users
- `call_files` DB table keeps metadata (filename, size, path) for fast listing without hitting storage

**Negative / Trade-offs:**
- Signed URLs expire in 60s — frontend must call `/download` endpoint each time a download is needed (cannot cache URLs)
- supabase-py `storage.from_().upload()` returns an object with `path` on success; error handling requires checking the response type

**What this decision affects:**
- `backend/routers/files.py` — upload, list, delete, signed URL generation
- `backend/tests/test_files.py` — storage client mocked, 10 tests
- `frontend/src/components/ContextFiles.tsx` — download triggers fresh signed URL
- Supabase dashboard — `call-files` bucket must be created manually before deploy

**Known gotcha — supabase-py None in .update():**
`supabase-py` silently strips `None` values from `.update()` dicts. For any PATCH that must set a column to NULL, use `client.postgrest.session.patch()` with `content=json.dumps(payload)` directly.

#### Review Triggers
- [ ] If signed URL TTL causes UX issues (links expiring during active session)
- [ ] If file sizes grow beyond Supabase free-tier storage limits

---

## 📌 Superseded Decisions
| Superseded ADR | Superseded By | Date | Reason |
|---|---|---|---|
