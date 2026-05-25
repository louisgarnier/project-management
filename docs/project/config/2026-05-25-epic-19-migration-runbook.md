# EPIC-19 Migration Runbook

## Pre-flight (one-time per environment)

1. **Apply migration 035** in Supabase Dashboard:
   ```sql
   -- Paste contents of backend/database/migrations/035_task_level_match_groups.sql
   ```

2. **Verify the new columns exist:**
   ```sql
   SELECT column_name FROM information_schema.columns
   WHERE table_name = 'topic_match_groups';
   ```
   Should include: `call_task_refs`, `project_task_refs`, `kind`.

## Reset stale Pass 1/2/3 caches (per-project)

3. **Dry run:**
   ```bash
   python3 -m backend.scripts.repopulate_verify_new_cache --project <uuid> --dry-run
   ```

4. **Actual reset:**
   ```bash
   python3 -m backend.scripts.repopulate_verify_new_cache --project <uuid>
   ```

## Backfill historical match_groups (per-project)

5. **Dry run:**
   ```bash
   python3 -m backend.scripts.migrate_match_groups_to_task_level --project <uuid> --dry-run
   ```

6. **Actual backfill:**
   ```bash
   python3 -m backend.scripts.migrate_match_groups_to_task_level --project <uuid>
   ```

## Post-flight verification

Re-open a representative call in the UI and confirm:

- **project_matching:** new task-level UI loads; existing tasks (left) and candidate tasks (right) render. Exact-text matches highlighted yellow. Keyboard shortcuts (j/k/h/l/space/n/esc) work.
- **Cross-topic binding:** when binding a candidate task from topic X to an existing task under topic Y, modal appears with 3 choices (keep existing topic, keep candidate topic, merge topics).
- **Pass 1** (if any candidates in `new_topics` bucket): runs cleanly; verdicts now use `confirmed_new` / `suggest_merge_with` (legacy aliases `truly_new` / `should_be_merged_with` still surface for downstream compat). No `citations_lack_rare_terms` warnings — those were deleted with the sanity-flag stack.
- **Pass 2** (if any `old_untouched_topics`): runs with line-number citations. Verdicts: `confirmed_not_discussed` / `suggest_discussed_at`. No verbatim-quote citation failures.
- **Pass 3** (if any `merged_topics`): runs synthesis (NOT re-extraction). Output preserves `task_id` identity across calls. Citations are line-ranges.

## Rolling back (if needed)

Migration 035 added columns with `DEFAULT '[]'` — they are non-destructive. To roll back EPIC-19:
- Backend: `git revert` the EPIC-19 commits (or branch off pre-EPIC-19 SHA `4c6a531`)
- Frontend: `ProjectMatchingStage.tsx` still exists; restore its render in `app/projects/[id]/calls/[call_id]/page.tsx`
- Cache resets via `repopulate_verify_new_cache.py` work the same under either version

## Commit log (15 EPIC-19 commits)

| # | Phase | SHA | Description |
|---|---|---|---|
| Plan | — | 4c6a531 | docs: implementation plan |
| 1 | 1 | ca799cd | migration 035 SQL |
| 2 | 1 | 38bcda0 | task_match_persistence service |
| 3 | 1 | 9899572 | save_match_groups endpoint task-level |
| 4 | 2 | 49b0af1 | delete S2.2 canonical-match path |
| 5 | 2 | 152fd20 | delete rarity check + sanity stack |
| 6 | 2 | a03a401 | Pass 1 prompt safety-net framing |
| 7 | 2 | 26f79b8 | verdict aliasing + fixture cleanup |
| 8 | 3 | 3da7150 | Pass 2 line-number citations |
| 9 | 4 | ab7082c | Pass 3 synthesis prompt |
| 10 | 4 | 376ea9b | Pass 3 orchestration |
| 11 | 5 | 89a9793 | task-matching UI components |
| 12 | 5 | 7957adf | cross-topic binding modal |
| 13 | 5 | 35cbe1a | keyboard nav + auto-bind |
| 14 | 6 | b9ca278 | backfill script |
| 15 | 6 | (this commit) | runbook + wrap-up docs |
