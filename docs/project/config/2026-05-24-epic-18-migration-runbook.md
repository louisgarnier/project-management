# EPIC-18 Migration Runbook

## What's changing
- Pass 1 (`verify_new`) output schema changed:
  - Citations now use `evidence_lines: [start, end]` instead of free-form `quote` strings
  - `extraction_grounded` / `ungrounded_items` fields removed
  - New verdict states: `confirmed_match`, `wrong_canonical_actually_new`, `wrong_canonical_belongs_elsewhere` (alongside existing `truly_new` and `should_be_merged_with`)
- `compute_confidence` emits `auto_accept_eligible` flag
- v5 Stage 5 cluster prompt receives full project topic structure (key_terms + tasks)

Cached `verify_new_cache` blobs in the `calls` table have the OLD schema and are unreadable by the new frontend.

## Pre-flight (one-time)
1. Confirm migration 034 (`project_topic_state` view) is applied:
   ```sql
   SELECT * FROM project_topic_state LIMIT 1;
   ```
   If the view doesn't exist, apply `backend/database/migrations/034_unified_project_topic_state.sql` in Supabase Dashboard.

## Reprocess verify_new_cache (per-project)

2. **Dry run first** to see what's affected:
   ```bash
   python3 -m backend.scripts.repopulate_verify_new_cache --project <uuid> --dry-run
   ```

3. **Actual reset** (clears cache + status; user re-opens to trigger fresh Pass 1):
   ```bash
   python3 -m backend.scripts.repopulate_verify_new_cache --project <uuid>
   ```

4. **Re-open each affected call** in the UI. Pass 1 re-runs automatically under the new schema (assuming the call's stage is at `project_updates` or later).

## All projects (use with care)
Reset across every project at once:
```bash
python3 -m backend.scripts.repopulate_verify_new_cache --all --dry-run  # preview
python3 -m backend.scripts.repopulate_verify_new_cache --all            # commit
```

## Post-flight verification
For each project where cache was reset, spot-check 2-3 calls in the UI:
- No "ungrounded items" warnings (the old broken check is removed)
- Citation evidence renders as line ranges (`Call X, lines 28-32`)
- Auto-accepted `truly_new` items show "✓ Auto-accepted as new (confidence ##%)" with an "Override: merge instead" button
- Wrong-canonical detections (if any) surface as distinct verdict labels in the Pass 1 review screen
