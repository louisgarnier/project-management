# Story 1.3 — Supabase Schema

**Epic:** EPIC-1 — Foundation & Logging
**Maps to plan:** Slice 1 (Foundation)
**Maps to PRD:** FR-01 through FR-13 (data model underpins all features)
**Status:** `pending`

---

## Goal
All six tables exist in Supabase with correct constraints, indexes, and seed data (6 default artifact types). The app can connect and query without errors.

## Acceptance Criteria
- [ ] Tables created: `projects`, `calls`, `artifact_types`, `artifacts`, `topics`, `topic_updates`
- [ ] `calls.kanban_stage` CHECK constraint: `('transcript','artifacts','topics','done')`
- [ ] `artifacts.mode` CHECK constraint: `('claude','manual')`
- [ ] `artifacts.status` CHECK constraint: `('pending','generating','done','error')`
- [ ] `topics.status` CHECK constraint: `('active','decision_made','on_hold','closed')`
- [ ] `artifacts.prompt_used` column is NOT NULL (immutable snapshot enforced at app level)
- [ ] 6 default artifact types seeded in `artifact_types` table
- [ ] `backend/database/supabase_client.py` singleton connects successfully
- [ ] `GET /health` returns `{"status":"ok","db":"connected"}` when Supabase is reachable

## Tasks
- [ ] Run migration SQL in Supabase dashboard (copy from plan Slice 1)
- [ ] Seed 6 default artifact types (copy from plan Slice 1 seed SQL)
- [ ] Create `backend/database/supabase_client.py` with singleton `get_client()`
- [ ] Update `GET /health` to ping Supabase and return db status
- [ ] Write test: `backend/tests/test_db.py` — connect, insert dummy project, delete it

## Schema (copy to Supabase SQL editor)

```sql
CREATE TABLE projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE calls (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  transcript TEXT,
  kanban_stage TEXT NOT NULL DEFAULT 'transcript'
    CHECK (kanban_stage IN ('transcript','artifacts','topics','done')),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE artifact_types (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  prompt TEXT NOT NULL,
  is_default BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE artifacts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  call_id UUID NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
  artifact_type_id UUID NOT NULL REFERENCES artifact_types(id),
  mode TEXT NOT NULL CHECK (mode IN ('claude','manual')),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending','generating','done','error')),
  content TEXT,
  prompt_used TEXT NOT NULL,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE topics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active','decision_made','on_hold','closed')),
  first_raised_call_id UUID REFERENCES calls(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE topic_updates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  call_id UUID NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
  summary TEXT NOT NULL,
  follow_up_items JSONB DEFAULT '[]',
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Seed Data

```sql
INSERT INTO artifact_types (name, prompt, is_default) VALUES
  ('Executive Summary',
   'Write a concise executive summary of this call in 3–5 bullet points. Focus on decisions made, key outcomes, and the overall direction agreed upon.',
   TRUE),
  ('Next Steps & Action Items',
   'Extract all action items and next steps from this call. For each item, state: what needs to be done, who is responsible (if mentioned), and any deadline discussed.',
   TRUE),
  ('Questions for Stakeholders',
   'List all open questions that remain unanswered after this call and should be raised with stakeholders before the next session.',
   TRUE),
  ('Email Summary (1-pager)',
   'Write a professional 1-page email summarising this call for the client. Include: context, key discussion points, decisions made, and next steps. Tone: clear and business-professional.',
   TRUE),
  ('Email Follow-up (pre-next-call)',
   'Write a short follow-up email to send before the next call. Summarise what was agreed, what each party should have completed, and confirm the agenda for the next session.',
   TRUE),
  ('Next Call Meeting Invite Topics',
   'Generate a structured agenda for the next call based on open items, unresolved questions, and planned next steps from this call.',
   TRUE);
```

## Dev Tests
- `backend/tests/test_db.py`:
  - Supabase client connects without error
  - Can insert and delete a test project row
  - `GET /health` returns `{"status":"ok","db":"connected"}`
