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
