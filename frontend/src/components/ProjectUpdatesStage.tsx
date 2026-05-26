"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { callsAPI, topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type {
  Call,
  TopicData,
  MatchGroup,
  VerifyNewResult,
  VerifyNotDiscussedResult,
  ExtractedUpdateResult,
} from "@/types";
import EvidenceTrail from "./EvidenceTrail";
import ProgressLog, { type ProgressEntry } from "./ProgressLog";
import ConfidenceGauge from "./ConfidenceGauge";

// ── Group colour palette (mirrors ProjectMatchingStage) ───────────────────
const GROUP_COLORS = [
  { bg: "#e9f0ff", border: "#4c9aff", text: "#0052cc" },  // blue
  { bg: "#e3fcef", border: "#57d9a3", text: "#006644" },  // green
  { bg: "#fce4fa", border: "#cc57c5", text: "#6b2066" },  // purple
  { bg: "#ffe8d6", border: "#ff8b00", text: "#bf4300" },  // orange
  { bg: "#e6fcff", border: "#00b8d9", text: "#00668c" },  // cyan
  { bg: "#ffd6d6", border: "#ff5630", text: "#ae2a19" },  // red
];
function groupColor(idx: number) {
  return GROUP_COLORS[idx % GROUP_COLORS.length];
}

// Reserved key inside the *_cache JSONB columns where the backend writes its
// step-by-step progress log. See backend/services/topic_verification.py::ProgressLogger.
const PROGRESS_KEY = "__progress__";
function readProgress(cache: Record<string, unknown> | null | undefined): ProgressEntry[] {
  if (!cache) return [];
  const raw = (cache as Record<string, unknown>)[PROGRESS_KEY];
  return Array.isArray(raw) ? (raw as ProgressEntry[]) : [];
}

type Props = {
  call: Call;
  projectId: string;
  /** New prop name — preferred. */
  onValidateComplete?: () => void;
  /** Legacy prop name from KanbanBoard/page.tsx — keep until parent is updated. */
  onValidated?: () => void;
  onPollCall?: () => Promise<void>;
  /** Legacy prop — ignored; call.id is used instead. */
  callId?: string;
};

export default function ProjectUpdatesStage({ call, projectId, onValidateComplete, onValidated, onPollCall }: Props) {
  // Normalise: accept either prop name for the completion callback.
  const fireComplete = onValidateComplete ?? onValidated ?? (() => {});
  const [projectTopics, setProjectTopics] = useState<TopicData[]>([]);
  const [pending, setPending] = useState<TopicData[]>([]);
  const [groups, setGroups] = useState<MatchGroup[]>([]);
  const [busy, setBusy] = useState<null | "①" | "②" | "③">(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  // Live cache+status overlay updated on every poll tick. Lets the ProgressLog
  // panels show backend progress in real time without waiting for the final
  // window.location.reload at the end of a pass.
  const [live, setLive] = useState<Partial<Call>>({});
  const eff: Call = { ...call, ...live };

  // ── User decisions (override LLM verdicts) ──
  // Keys: lowercased topic name (Section 1) or topic_id (Section 2).
  // Decision shape:
  //   action          : "new" | "merge"
  //   merge_to_ids    : project_topic ids being merged with (old topics — archived if ≥2 sources)
  //   merge_pending_names : OTHER call-topic names from this call to absorb into this merge
  // 1 source (1 merge_to_id, 0 merge_pending_names) = standard 1:1 merge
  // ≥2 sources total = M:N — new topic created, old topics archived, other absorbed candidates skipped from payload
  const [newDecisions, setNewDecisions] = useState<
    Record<string, { action: "new" | "merge"; merge_to_ids: string[]; merge_pending_names: string[] }>
  >({});
  const [ndDecisions, setNdDecisions] = useState<
    Record<string, { action: "not_discussed" | "discussed" }>
  >({});

  function resolveNewDecision(
    name: string,
    result: VerifyNewResult | undefined
  ): { action: "new" | "merge"; merge_to_ids: string[]; merge_pending_names: string[] } {
    const explicit = newDecisions[name.toLowerCase().trim()];
    if (explicit) return explicit;
    if (result && !result.needs_manual_review) {
      if (result.verdict === "should_be_merged_with" && result.matched_topic_id) {
        return { action: "merge", merge_to_ids: [result.matched_topic_id], merge_pending_names: [] };
      }
      if (result.verdict === "truly_new") return { action: "new", merge_to_ids: [], merge_pending_names: [] };
    }
    return { action: "new", merge_to_ids: [], merge_pending_names: [] };
  }
  function resolveNdDecision(
    topic_id: string,
    result: VerifyNotDiscussedResult | undefined
  ): { action: "not_discussed" | "discussed" } {
    const explicit = ndDecisions[topic_id];
    if (explicit) return explicit;
    if (result && !result.needs_manual_review) {
      if (result.verdict === "actually_discussed") return { action: "discussed" };
      if (result.verdict === "not_discussed") return { action: "not_discussed" };
    }
    return { action: "not_discussed" };
  }

  useEffect(() => {
    Promise.all([
      topicsAPI.getMatchGroups(call.id),
      topicsAPI.getPending(call.id),
      topicsAPI.priorToCall(projectId, call.id),
    ])
      .then(([g, p, pr]) => {
        setGroups(
          g.map((x: { project_topic_ids: string[]; call_topic_names: string[] }) => ({
            project_topic_ids: x.project_topic_ids ?? [],
            call_topic_names: x.call_topic_names ?? [],
          }))
        );
        setPending(p);
        setProjectTopics(pr);
      })
      .catch((e: unknown) => {
        logger.error("[ProjectUpdatesStage] load failed", { data: e });
        setError("Failed to load data");
      });
  }, [call.id, projectId]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // Migration sets derived from EFFECTIVE decisions (user override > LLM verdict
  // > default). Used to compute section placement of project topics.
  const migratedFromNew = useMemo<Set<string>>(() => {
    const ids = new Set<string>();
    const cache = (eff.verify_new_cache ?? {}) as Record<string, VerifyNewResult>;
    for (const p of pending) {
      const r = cache[p.name];
      const d = resolveNewDecision(p.name, r);
      if (d.action === "merge") {
        d.merge_to_ids.forEach((id) => ids.add(id));
      }
    }
    return ids;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, eff.verify_new_cache, newDecisions]);

  // Names of pending candidates that have been ABSORBED by another candidate's
  // M:N merge. They get hidden from Section 1 (the primary candidate's card
  // represents the whole merge).
  const absorbedPendingNames = useMemo<Set<string>>(() => {
    const names = new Set<string>();
    const cache = (eff.verify_new_cache ?? {}) as Record<string, VerifyNewResult>;
    for (const p of pending) {
      const r = cache[p.name];
      const d = resolveNewDecision(p.name, r);
      if (d.action === "merge" && d.merge_pending_names && d.merge_pending_names.length > 0) {
        d.merge_pending_names.forEach((n) => names.add(n.toLowerCase().trim()));
      }
    }
    return names;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, eff.verify_new_cache, newDecisions]);

  // For M:N merges (≥2 targets), the FIRST target id is the "primary" — it
  // shows the merge card in Section 3. Subordinate ids are hidden (they will
  // be archived at Save & Continue, so showing them as separate Section 3
  // entries would be confusing).
  const subordinateMergeIds = useMemo<Set<string>>(() => {
    const ids = new Set<string>();
    const cache = (eff.verify_new_cache ?? {}) as Record<string, VerifyNewResult>;
    for (const p of pending) {
      const r = cache[p.name];
      const d = resolveNewDecision(p.name, r);
      if (d.action === "merge" && d.merge_to_ids.length >= 2) {
        d.merge_to_ids.slice(1).forEach((id) => ids.add(id));
      }
    }
    return ids;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, eff.verify_new_cache, newDecisions]);

  // Inverse map: each PRIMARY target id → pending name that merged into it.
  // Section 3 uses this to show "moved from New: X" + audit trail.
  const mergedFromNewSource = useMemo<Map<string, string>>(() => {
    const m = new Map<string, string>();
    const cache = (eff.verify_new_cache ?? {}) as Record<string, VerifyNewResult>;
    for (const p of pending) {
      const r = cache[p.name];
      const d = resolveNewDecision(p.name, r);
      if (d.action === "merge" && d.merge_to_ids.length >= 1) {
        m.set(d.merge_to_ids[0], p.name);
      }
    }
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, eff.verify_new_cache, newDecisions]);

  // For showing subordinate target names on the primary card.
  const mergedFromNewSubordinateNames = useMemo<Map<string, string[]>>(() => {
    const m = new Map<string, string[]>();
    const cache = (eff.verify_new_cache ?? {}) as Record<string, VerifyNewResult>;
    for (const p of pending) {
      const r = cache[p.name];
      const d = resolveNewDecision(p.name, r);
      if (d.action === "merge" && d.merge_to_ids.length >= 2) {
        const primary = d.merge_to_ids[0];
        const subs = d.merge_to_ids
          .slice(1)
          .map((id) => projectTopics.find((t) => t.topic_id === id)?.name ?? "(unknown)");
        m.set(primary, subs);
      }
    }
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, eff.verify_new_cache, newDecisions, projectTopics]);

  const migratedFromNotDiscussed = useMemo<Set<string>>(() => {
    const ids = new Set<string>();
    const cache = (eff.verify_not_discussed_cache ?? {}) as Record<string, VerifyNotDiscussedResult>;
    for (const t of projectTopics) {
      const tid = t.topic_id ?? "";
      if (!tid) continue;
      const r = cache[tid];
      const d = resolveNdDecision(tid, r);
      if (d.action === "discussed") ids.add(tid);
    }
    return ids;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectTopics, eff.verify_not_discussed_cache, ndDecisions]);

  const sections = useMemo(() => {
    // Backend lowercases call_topic_names on save (save_match_groups), but
    // pending.name keeps original case. Normalise both sides to compare.
    const norm = (s: string) => s.toLowerCase().trim();

    // ── Per-group display arrays (EPIC-19 restructure) ────────────────────
    // Only "binding" kind groups participate in display (skip topic_merge rows).
    const bindingGroups = groups.filter((g) => (g.kind ?? "binding") === "binding");
    const markNewGroups = bindingGroups.filter((g) => (g.project_topic_ids?.length ?? 0) === 0);
    const mergedBindingGroups = bindingGroups.filter((g) => (g.project_topic_ids?.length ?? 0) > 0);

    // Helper: resolve task_id → task data from pending topics
    const resolveCallTask = (taskId: string | undefined): { task: string; next_step?: string; owner?: string; task_id?: string; topicName: string } | null => {
      if (!taskId) return null;
      for (const p of pending) {
        for (const t of (p.tasks ?? [])) {
          if (t.task_id === taskId) return { ...t, topicName: p.name };
        }
      }
      return null;
    };

    // SECTION 1: one item per mark-new group
    const newGroups = markNewGroups.map((g, i) => ({
      groupIndex: i,
      g,
      candidateTopicNames: g.call_topic_names ?? [],
      candidateTasks: (g.call_task_refs ?? [])
        .map((r) => resolveCallTask(r.task_id))
        .filter((x): x is NonNullable<typeof x> => x !== null),
    }));

    // SECTION 2: project topics not in any binding group AND not migrated
    const matchedProjectIds = new Set(bindingGroups.flatMap((g) => g.project_topic_ids));
    const notInCall = projectTopics.filter((t) => {
      const tid = t.topic_id ?? "";
      if (matchedProjectIds.has(tid)) return false;
      if (migratedFromNotDiscussed.has(tid)) return false;
      if (migratedFromNew.has(tid)) return false;
      return true;
    });

    // SECTION 3: one card per merged binding group
    const mergedGroups = mergedBindingGroups.map((g, i) => ({
      groupIndex: markNewGroups.length + i,
      g,
      candidateTasks: (g.call_task_refs ?? [])
        .map((r) => resolveCallTask(r.task_id))
        .filter((x): x is NonNullable<typeof x> => x !== null),
      projectTasks: (g.project_task_refs ?? [])
        .map((r) => {
          const topic = projectTopics.find((t) => t.topic_id === r.project_topic_id);
          if (!topic) return null;
          const task = (topic.tasks ?? []).find((t) => t.task_id === r.task_id);
          if (!task) return null;
          return { ...task, topicName: topic.name, topicId: topic.topic_id };
        })
        .filter((x): x is NonNullable<typeof x> => x !== null),
      targetTopicName: g.target_topic_name ?? null,
    }));

    // ── Topic-level arrays (kept for handleSaveContinue compatibility) ────
    const newGroupCallNames = new Set(markNewGroups.flatMap((g) => g.call_topic_names.map(norm)));
    const allMatchedProjectIds = new Set(groups.flatMap((g) => g.project_topic_ids));

    const newCandidates = pending.filter((p) => newGroupCallNames.has(norm(p.name)));
    const newTopics = newCandidates.filter((p) => {
      if (absorbedPendingNames.has(norm(p.name))) return false;
      const r = (eff.verify_new_cache ?? {})[p.name];
      const d = resolveNewDecision(p.name, r);
      return !(d.action === "merge" && (d.merge_to_ids.length >= 1 || d.merge_pending_names.length >= 1));
    });

    const mergedSet = new Set<string>([
      ...allMatchedProjectIds,
      ...migratedFromNotDiscussed,
      ...migratedFromNew,
    ]);
    const merged = projectTopics.filter((t) => {
      const tid = t.topic_id ?? "";
      return mergedSet.has(tid) && !subordinateMergeIds.has(tid);
    });

    return { newGroups, notInCall, mergedGroups, newTopics, merged };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groups, pending, projectTopics, eff.verify_new_cache, migratedFromNew, migratedFromNotDiscussed, subordinateMergeIds, absorbedPendingNames, newDecisions]);

  const stage1Done = eff.verify_new_status === "done";
  const stage2Done = eff.verify_not_discussed_status === "done";
  const stage3Done = eff.extract_updates_status === "done";
  const allDone = stage1Done && stage2Done && stage3Done;

  const triggerPass = async (which: "①" | "②" | "③") => {
    setBusy(which);
    setError(null);
    // Optimistic clear: don't wait for the first 3s poll tick — the old cache
    // (and its stale progress log + topic results) should disappear immediately.
    // Backend will overwrite cache + status when its background task runs.
    setLive((prev) => {
      if (which === "①") return { ...prev, verify_new_cache: null, verify_new_status: "processing" };
      if (which === "②") return { ...prev, verify_not_discussed_cache: null, verify_not_discussed_status: "processing" };
      return { ...prev, extract_updates_cache: null, extract_updates_status: "processing" };
    });
    // Also reset user decisions linked to this pass — otherwise stale decisions
    // pin topics in the wrong section even after re-verify.
    if (which === "①") setNewDecisions({});
    if (which === "②") setNdDecisions({});
    try {
      if (which === "①") await topicsAPI.verifyNew(call.id);
      else if (which === "②") await topicsAPI.verifyNotDiscussed(call.id);
      else await topicsAPI.extractUpdates(call.id);

      if (pollRef.current) clearInterval(pollRef.current);
      // First poll fires after 1s (not 3s) so the progress log appears
      // promptly. Subsequent polls keep the 3s cadence.
      const doPoll = async () => {
        try {
          const fresh = await callsAPI.getCall(call.id);
          // Always refresh the live overlay so the ProgressLog panel updates
          // mid-flight while the backend writes new entries into the cache.
          setLive({
            verify_new_cache: fresh.verify_new_cache,
            verify_new_status: fresh.verify_new_status,
            verify_not_discussed_cache: fresh.verify_not_discussed_cache,
            verify_not_discussed_status: fresh.verify_not_discussed_status,
            extract_updates_cache: fresh.extract_updates_cache,
            extract_updates_status: fresh.extract_updates_status,
          });
          const status =
            which === "①"
              ? fresh.verify_new_status
              : which === "②"
                ? fresh.verify_not_discussed_status
                : fresh.extract_updates_status;
          if (status === "done" || status === "failed") {
            if (pollRef.current) {
              clearInterval(pollRef.current);
              pollRef.current = null;
            }
            setBusy(null);
            // Notify parent (if listener registered) so the source-of-truth `call`
            // prop also refreshes; otherwise we stay on the live overlay (no
            // hard-reload — would clobber the ProgressLog the user just saw).
            if (onPollCall) {
              await onPollCall();
            }
          }
        } catch (e) {
          logger.error("[ProjectUpdatesStage] poll failed", { data: e });
        }
      };
      // Kick off first poll after 1s (then 3s cadence) so the progress log
      // appears promptly without waiting 3s for the first backend write.
      setTimeout(doPoll, 1000);
      pollRef.current = setInterval(doPoll, 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to trigger pass");
      setBusy(null);
    }
  };

  const handleSaveContinue = async () => {
    setSaving(true);
    setError(null);
    try {
      const extractCache = eff.extract_updates_cache ?? {};
      const matchedProjectIds = new Set(groups.flatMap((g) => g.project_topic_ids));
      // matchedProjectIds is used implicitly via sections.merged — suppress unused var
      void matchedProjectIds;

      const payload: TopicData[] = [];

      // For new topics that truly are new (not migrated): persist raw pending data
      for (const p of sections.newTopics) {
        payload.push({ ...p, topic_id: null });
      }

      // Topics the user explicitly merged from New → existing topic(s) and/or
      // other call candidates. The merge collapses all into ONE topic.
      // Tasks/OQ/decisions are union'd across the primary candidate + all
      // absorbed call-topic candidates.
      const userMergedFromNew = new Map<
        string,
        { primary_pending: TopicData; all_targets: string[]; absorbed_pending: TopicData[] }
      >();
      const absorbedNames = new Set<string>();
      const vnCache = (eff.verify_new_cache ?? {}) as Record<string, VerifyNewResult>;
      for (const p of pending) {
        const r = vnCache[p.name];
        const d = resolveNewDecision(p.name, r);
        if (d.action === "merge" && (d.merge_to_ids.length >= 1 || d.merge_pending_names.length >= 1)) {
          const absorbedPendings: TopicData[] = [];
          for (const n of d.merge_pending_names) {
            const found = pending.find((pp) => pp.name.toLowerCase().trim() === n);
            if (found) {
              absorbedPendings.push(found);
              absorbedNames.add(found.name.toLowerCase().trim());
            }
          }
          // Anchor key for Section 3 placement: use first old target_id if any,
          // else a synthetic key (we'll see this when only call-to-call merge).
          const anchorKey = d.merge_to_ids[0] ?? `__pending_merge__${p.name.toLowerCase().trim()}`;
          userMergedFromNew.set(anchorKey, {
            primary_pending: p,
            all_targets: d.merge_to_ids,
            absorbed_pending: absorbedPendings,
          });
        }
      }
      // Skip absorbed candidates from the new_topics payload (they are absorbed
      // into the primary's merge, not standalone new topics).
      // (Implementation: we'll filter when building payload below.)

      // Helper: union tasks/OQ/decisions across primary + absorbed candidates.
      const unionPendings = (primary: TopicData, absorbed: TopicData[]) => ({
        tasks: [...(primary.tasks ?? []), ...absorbed.flatMap((a) => a.tasks ?? [])],
        open_questions: [...(primary.open_questions ?? []), ...absorbed.flatMap((a) => a.open_questions ?? [])],
        decisions: [...(primary.decisions ?? []), ...absorbed.flatMap((a) => a.decisions ?? [])],
      });

      const processedAnchorKeys = new Set<string>();

      for (const m of sections.merged) {
        const tid = m.topic_id ?? "";
        const extracted = extractCache[tid];
        const fromNew = userMergedFromNew.get(tid);
        if (extracted) {
          const s = extracted.extracted_snapshot;
          payload.push({
            ...m,
            topic_id: tid,
            summary: s.summary,
            status: s.status,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            tasks: s.tasks as any,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            open_questions: s.open_questions as any,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            decisions: s.decisions as any,
            citations: [],
            evidence_trail: extracted.evidence_trail,
            needs_manual_review: extracted.needs_manual_review,
          });
        } else if (fromNew) {
          const u = unionPendings(fromNew.primary_pending, fromNew.absorbed_pending);
          const totalSources = fromNew.all_targets.length + fromNew.absorbed_pending.length;
          if (totalSources >= 2 || fromNew.absorbed_pending.length >= 1) {
            // M:N — new topic absorbing all sources. _source_topic_ids triggers
            // archival of the old topics in validate_project_updates.
            payload.push({
              ...fromNew.primary_pending,
              ...u,
              topic_id: null,
              _source_topic_ids: fromNew.all_targets,
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            } as any);
          } else {
            // 1:1 — promote primary onto the existing target topic_id.
            payload.push({ ...fromNew.primary_pending, topic_id: tid });
          }
          processedAnchorKeys.add(tid);
        } else {
          payload.push({ ...m, topic_id: tid });
        }
      }

      // Pure-pending merges (primary + absorbed candidates, NO old topics).
      // These don't appear in sections.merged (no project_topic anchor), so
      // we emit them separately as new topics combining the absorbed data.
      for (const [anchorKey, group] of userMergedFromNew.entries()) {
        if (processedAnchorKeys.has(anchorKey)) continue;
        // Only pure-pending anchors remain (synthetic __pending_merge__ keys).
        const u = unionPendings(group.primary_pending, group.absorbed_pending);
        payload.push({
          ...group.primary_pending,
          ...u,
          topic_id: null,
        });
      }

      // Not-discussed topics: backend will mark not_discussed=true via flag in payload
      for (const t of sections.notInCall) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        payload.push({ ...t, not_discussed: true } as any);
      }

      await topicsAPI.validateUpdates(call.id, payload);
      fireComplete();
    } catch (e: unknown) {
      logger.error("[ProjectUpdatesStage] save failed", { data: e });
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  // Build callsById from the projectTopics' implicit calls? We need a separate call to enumerate calls.
  // For the evidence trail we need all calls in the project. Since calls list isn't loaded here,
  // we synthesize minimal entries — the trail rendering needs id + title + created_at to sort/label.
  // Simplest path: lazy-load when ③ done.
  const [callsById, setCallsById] = useState<Record<string, Pick<Call, "id" | "title" | "created_at">>>({});
  useEffect(() => {
    if (!stage3Done) return;
    // Lazy-fetch all calls of the project to build a callsById map.
    // Try the project-calls endpoint if available; otherwise synthesize from current call only.
    (async () => {
      try {
        // No direct callsAPI for project calls list? Fall back to a single-call map.
        // If a project-calls endpoint exists, use it.
        // @ts-expect-error — listForProject may or may not exist
        const list = await callsAPI.listForProject?.(projectId);
        if (Array.isArray(list)) {
          const map: Record<string, Pick<Call, "id" | "title" | "created_at">> = {};
          for (const c of list) {
            map[c.id] = { id: c.id, title: c.title ?? "", created_at: c.created_at ?? "" };
          }
          setCallsById(map);
          return;
        }
      } catch {
        // ignore — fall through to single-call synth
      }
      setCallsById({
        [call.id]: { id: call.id, title: call.title, created_at: call.created_at },
      });
    })();
  }, [stage3Done, projectId, call.id, call.title, call.created_at]);

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <header style={{ padding: "14px 20px", borderBottom: "1px solid #dfe1e6" }}>
        <h2 style={{ margin: 0, fontSize: 15, color: "#172b4d" }}>
          Project Updates · {call.title ?? "Untitled"}
        </h2>
      </header>

      {error && (
        <div
          style={{
            margin: 16,
            padding: 12,
            background: "#fff1f0",
            color: "#ae2a19",
            borderRadius: 6,
            border: "1px solid #ffbdad",
            fontSize: 12,
          }}
        >
          {error}
        </div>
      )}

      <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
        {/* Section 1 — New groups (one card per mark-new binding group) */}
        <section style={{ marginBottom: 24 }}>
          <SectionHeader
            title="1. New tasks in this call"
            count={sections.newGroups.reduce((sum, ng) => sum + ng.candidateTasks.length, 0)}
            button={
              <button
                disabled={busy !== null || sections.newGroups.length === 0}
                onClick={() => triggerPass("①")}
                style={passButton(stage1Done)}
              >
                {busy === "①" ? "Running…" : stage1Done ? "Re-verify ①" : "① Verify new"}
              </button>
            }
            done={stage1Done}
            disabled={false}
          />
          <ProgressLog
            entries={readProgress(eff.verify_new_cache)}
            active={busy === "①"}
          />
          {sections.newGroups.map((ng) => {
            const color = groupColor(ng.groupIndex);
            // LLM results: look up by each candidate topic name (best-effort until Phase B)
            const groupResults = ng.candidateTopicNames
              .map((name) => (eff.verify_new_cache ?? {})[name] as VerifyNewResult | undefined)
              .filter((r): r is VerifyNewResult => r !== undefined);
            const firstResult = groupResults[0];

            return (
              <div
                key={`new-group-${ng.groupIndex}`}
                style={{
                  ...cardStyle,
                  borderColor: color.border,
                  borderLeftWidth: 4,
                }}
              >
                {/* Card header */}
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: 3,
                      background: color.bg,
                      color: color.text,
                      border: `1px solid ${color.border}`,
                    }}
                  >
                    New group {ng.groupIndex + 1}
                  </span>
                  {ng.candidateTopicNames.length > 0 && (
                    <span style={{ fontSize: 11, color: "#42526e" }}>
                      {ng.candidateTopicNames.join(", ")}
                    </span>
                  )}
                  {firstResult?.verdict === "truly_new" && !firstResult.needs_manual_review && (
                    <span style={badgeGreen}>LLM: ✓ truly new</span>
                  )}
                  {firstResult?.verdict === "should_be_merged_with" && !firstResult.needs_manual_review && (
                    <span style={badgeAmber}>LLM: ↻ merge suggested</span>
                  )}
                  {firstResult?.needs_manual_review && (
                    <span style={badgeRed}>⚠ needs manual review</span>
                  )}
                </div>

                {/* Candidate tasks */}
                {ng.candidateTasks.length > 0 ? (
                  <div>
                    <div style={{ fontSize: 10, fontWeight: 600, color: "#5e6c84", textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 2 }}>
                      New tasks ({ng.candidateTasks.length})
                    </div>
                    <ul style={{ fontSize: 12, color: "#42526e", margin: 0, paddingLeft: 16 }}>
                      {ng.candidateTasks.map((t, i) => (
                        <li key={i} style={{ marginBottom: 2 }}>
                          <span style={{ color: "#97a0af", fontSize: 10 }}>[{t.topicName}]</span>{" "}
                          {t.task || <em style={{ color: "#97a0af" }}>(no task)</em>}
                          {t.next_step && <span style={{ color: "#5e6c84" }}> → {t.next_step}</span>}
                          {t.owner && <span style={{ color: "#97a0af", fontSize: 10 }}> ({t.owner})</span>}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <div style={{ fontSize: 11, color: "#97a0af", fontStyle: "italic" }}>(no task-level bindings — topic-level group)</div>
                )}

              </div>
            );
          })}
        </section>

        {/* Section 2 — Not in call */}
        <section style={{ marginBottom: 24 }}>
          <SectionHeader
            title="2. Old tasks not discussed in this call"
            count={sections.notInCall.reduce((sum, t) => sum + (t.tasks?.length ?? 0), 0)}
            button={
              <button
                disabled={!stage1Done || busy !== null || sections.notInCall.length === 0}
                onClick={() => triggerPass("②")}
                style={passButton(stage2Done)}
              >
                {busy === "②" ? "Running…" : stage2Done ? "Re-verify ②" : "② Verify not discussed"}
              </button>
            }
            done={stage2Done}
            disabled={!stage1Done}
          />
          <ProgressLog
            entries={readProgress(eff.verify_not_discussed_cache)}
            active={busy === "②"}
          />
          {sections.notInCall.map((t) => {
            const tid = t.topic_id ?? "";
            const r = (eff.verify_not_discussed_cache ?? {})[tid] as VerifyNotDiscussedResult | undefined;
            const d = resolveNdDecision(tid, r);
            return (
              <NotInCallCard
                key={tid}
                topic={t}
                result={r}
                decision={d}
                onDecisionChange={(next) =>
                  setNdDecisions((prev) => ({ ...prev, [tid]: next }))
                }
              />
            );
          })}
        </section>

        {/* Section 3 — Merged groups (one card per merged binding group) */}
        <section style={{ marginBottom: 24 }}>
          <SectionHeader
            title="3. Merged topics"
            count={sections.mergedGroups.length}
            button={
              <button
                disabled={!stage2Done || busy !== null || sections.mergedGroups.length === 0}
                onClick={() => triggerPass("③")}
                style={passButton(stage3Done)}
              >
                {busy === "③" ? "Running…" : stage3Done ? "Re-extract ③" : "③ Extract updates"}
              </button>
            }
            done={stage3Done}
            disabled={!stage2Done}
          />
          <ProgressLog
            entries={readProgress(eff.extract_updates_cache)}
            active={busy === "③"}
          />
          {sections.mergedGroups.map((mg) => {
            const color = groupColor(mg.groupIndex);

            // For MergedTopicCard compat: collect the project topics from this group's project_task_refs
            const groupProjectTopicIds = [...new Set((mg.g.project_task_refs ?? []).map((r) => r.project_topic_id).filter(Boolean) as string[])];
            // Fallback to project_topic_ids if no project_task_refs
            const effectiveProjectTopicIds = groupProjectTopicIds.length > 0
              ? groupProjectTopicIds
              : (mg.g.project_topic_ids ?? []);

            return (
              <div
                key={`merged-group-${mg.groupIndex}`}
                style={{
                  ...cardStyle,
                  borderColor: color.border,
                  borderLeftWidth: 4,
                  marginBottom: 8,
                }}
              >
                {/* Card header */}
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: 3,
                      background: color.bg,
                      color: color.text,
                      border: `1px solid ${color.border}`,
                    }}
                  >
                    Merged group {mg.groupIndex + 1}
                  </span>
                  {mg.targetTopicName && (
                    <span style={{ fontSize: 11, color: "#974f0c", fontWeight: 600 }}>
                      → new topic: &quot;{mg.targetTopicName}&quot;
                    </span>
                  )}
                  {(mg.g.call_topic_names ?? []).length > 0 && (
                    <span style={{ fontSize: 11, color: "#42526e" }}>
                      {mg.g.call_topic_names.join(", ")}
                    </span>
                  )}
                </div>

                {/* Two-column: PREVIOUS (project tasks) | THIS CALL (candidate tasks) */}
                <div style={{ display: "flex", gap: 12, fontSize: 12 }}>
                  {/* Left: project tasks */}
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, color: "#5e6c84", fontSize: 10, textTransform: "uppercase", marginBottom: 4 }}>
                      Previous ({mg.projectTasks.length} task{mg.projectTasks.length === 1 ? "" : "s"})
                    </div>
                    {mg.projectTasks.length > 0 ? (
                      <ul style={{ fontSize: 11, color: "#5e6c84", margin: 0, paddingLeft: 16 }}>
                        {mg.projectTasks.map((t, i) => (
                          <li key={i} style={{ marginBottom: 2 }}>
                            <span style={{ color: "#97a0af", fontSize: 10 }}>[{t.topicName}]</span>{" "}
                            {t.task || <em style={{ color: "#97a0af" }}>(no task)</em>}
                            {t.next_step && <span style={{ color: "#97a0af" }}> → {t.next_step}</span>}
                            {t.owner && <span style={{ color: "#97a0af", fontSize: 10 }}> ({t.owner})</span>}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div style={{ fontSize: 11, color: "#97a0af", fontStyle: "italic" }}>(no task-level bindings)</div>
                    )}
                  </div>
                  {/* Divider */}
                  <div style={{ width: 1, background: "#ebecf0", flexShrink: 0 }} />
                  {/* Right: candidate tasks from this call */}
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, color: "#5e6c84", fontSize: 10, textTransform: "uppercase", marginBottom: 4 }}>
                      This call ({mg.candidateTasks.length} task{mg.candidateTasks.length === 1 ? "" : "s"})
                    </div>
                    {mg.candidateTasks.length > 0 ? (
                      <ul style={{ fontSize: 11, color: "#42526e", margin: 0, paddingLeft: 16 }}>
                        {mg.candidateTasks.map((t, i) => (
                          <li key={i} style={{ marginBottom: 2 }}>
                            <span style={{ color: "#97a0af", fontSize: 10 }}>[{t.topicName}]</span>{" "}
                            {t.task || <em style={{ color: "#97a0af" }}>(no task)</em>}
                            {t.next_step && <span style={{ color: "#5e6c84" }}> → {t.next_step}</span>}
                            {t.owner && <span style={{ color: "#97a0af", fontSize: 10 }}> ({t.owner})</span>}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div style={{ fontSize: 11, color: "#97a0af", fontStyle: "italic" }}>(no task-level bindings)</div>
                    )}
                  </div>
                </div>

              </div>
            );
          })}
        </section>
      </div>

      <footer
        style={{
          padding: 12,
          borderTop: "1px solid #dfe1e6",
          display: "flex",
          justifyContent: "flex-end",
        }}
      >
        <button
          disabled={!allDone || saving}
          onClick={handleSaveContinue}
          style={{
            padding: "8px 22px",
            borderRadius: 6,
            border: "none",
            background: allDone && !saving ? "#0052cc" : "#f4f5f7",
            color: allDone && !saving ? "white" : "#97a0af",
            cursor: allDone && !saving ? "pointer" : "default",
            fontSize: 13,
            fontWeight: 600,
            fontFamily: "inherit",
          }}
        >
          {saving ? "Saving…" : "Save & Continue → Artifacts"}
        </button>
      </footer>
    </div>
  );
}

// ── Helper components ──────────────────────────────────────────────────────

function SectionHeader({
  title,
  count,
  button,
  done,
  disabled,
}: {
  title: string;
  count: number;
  button: React.ReactNode;
  done: boolean;
  disabled: boolean;
}) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "8px 12px",
        background: disabled ? "#f4f5f7" : "#fafbfc",
        opacity: disabled ? 0.5 : 1,
        borderRadius: 6,
        marginBottom: 8,
      }}
    >
      <span style={{ fontSize: 13, fontWeight: 700, color: "#172b4d" }}>
        {title} ({count}) {done && <span style={{ color: "#36b37e", marginLeft: 6 }}>✓ done</span>}
      </span>
      {button}
    </div>
  );
}

function NewTopicCard({
  topic,
  result,
  decision,
  projectTopics,
  otherPending,
  onDecisionChange,
}: {
  topic: TopicData;
  result?: VerifyNewResult;
  decision: { action: "new" | "merge"; merge_to_ids: string[]; merge_pending_names: string[] };
  projectTopics: TopicData[];
  otherPending: TopicData[];  // other call topics from this call (excluding self)
  onDecisionChange: (d: {
    action: "new" | "merge";
    merge_to_ids: string[];
    merge_pending_names: string[];
  }) => void;
}) {
  const isNewSelected = decision.action === "new";
  const isMergeSelected = decision.action === "merge";

  // Local DRAFT state while user is editing the merge picker.
  const [draftIds, setDraftIds] = useState<string[] | null>(null);
  const [draftPendingNames, setDraftPendingNames] = useState<string[] | null>(null);
  const pickerOpen = draftIds !== null;
  const displayedIds = draftIds ?? decision.merge_to_ids;
  const displayedPendingNames = draftPendingNames ?? decision.merge_pending_names;
  const totalSelected = displayedIds.length + displayedPendingNames.length;

  // The "primary" target for comparison display = first picked, fallback to LLM suggestion.
  const mergeTargetId = decision.merge_to_ids[0] ?? result?.matched_topic_id ?? null;
  const mergeTarget = mergeTargetId
    ? projectTopics.find((t) => t.topic_id === mergeTargetId)
    : null;

  // Resolved name lookup for chip display
  const topicNameById = (id: string): string =>
    projectTopics.find((t) => t.topic_id === id)?.name ?? "(unknown)";

  // Helpers for rendering
  const verdictCitations = (result?.citations ?? []).filter(
    (c) => !c.for || c.for === "verdict"
  );
  const extractionCitations = (result?.citations ?? []).filter(
    (c) => c.for === "extraction"
  );

  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 10, color: "#97a0af", textTransform: "uppercase", letterSpacing: ".04em" }}>
          from topic:
        </span>
        <strong style={{ fontSize: 13, color: "#172b4d" }}>{topic.name}</strong>
        {result?.verdict === "truly_new" && !result.needs_manual_review && (
          <span style={badgeGreen}>LLM: ✓ truly new</span>
        )}
        {result?.verdict === "should_be_merged_with" && !result.needs_manual_review && (
          <span style={badgeAmber}>LLM: ↻ merge with {result.matched_topic_name}</span>
        )}
        {result?.needs_manual_review && (
          <span style={badgeRed}>⚠ LLM uncertain — manual decision needed</span>
        )}
      </div>

      {/* EPIC-19: show the actual tasks the user marked as new, prominently */}
      {topic.tasks && topic.tasks.length > 0 && (
        <div style={{ marginTop: 6 }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: "#5e6c84", textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 2 }}>
            New tasks ({topic.tasks.length})
          </div>
          <ul style={{ fontSize: 12, color: "#42526e", margin: 0, paddingLeft: 16 }}>
            {topic.tasks.map((t, i) => (
              <li key={i} style={{ marginBottom: 2 }}>
                {t.task || <em style={{ color: "#97a0af" }}>(no task)</em>}
                {t.next_step && <span style={{ color: "#5e6c84" }}> → {t.next_step}</span>}
                {t.owner && <span style={{ color: "#97a0af", fontSize: 10 }}> ({t.owner})</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <ConfidenceGauge result={result} />

      {/* Sanity flags */}
      {result?.sanity_flag === "llm_recommends_merge_but_no_overlap" && (
        <div style={{ marginTop: 8, padding: 8, background: "#fff1f0", border: "1px solid #ffbdad", borderRadius: 4, fontSize: 11, color: "#ae2a19" }}>
          ⚠ <strong>Sanity flag:</strong> LLM recommends merge with &quot;{result.matched_topic_name}&quot; but the lexical pre-check
          found ZERO key_terms overlap AND ZERO mentions in past transcripts. Likely a false merge suggestion — review carefully.
        </div>
      )}
      {result?.sanity_flag === "llm_says_new_but_strong_overlap_exists" && (
        <div style={{ marginTop: 8, padding: 8, background: "#fff1f0", border: "1px solid #ffbdad", borderRadius: 4, fontSize: 11, color: "#ae2a19" }}>
          ⚠ <strong>Sanity flag:</strong> LLM says truly new, but the lexical pre-check shows strong key_terms overlap with an existing topic.
          Possible missed merge — review the comparison below.
        </div>
      )}
      {result?.sanity_flag === "insufficient_verdict_citations" && (
        <div style={{ marginTop: 8, padding: 8, background: "#fff1f0", border: "1px solid #ffbdad", borderRadius: 4, fontSize: 11, color: "#ae2a19" }}>
          ⚠ <strong>Sanity flag:</strong> LLM proposed merge with only 1 supporting quote (need ≥2 for confidence). Manual decision required.
        </div>
      )}
      {result?.sanity_flag === "platform_terms_only_overlap" && (
        <div style={{ marginTop: 8, padding: 8, background: "#fff1f0", border: "1px solid #ffbdad", borderRadius: 4, fontSize: 11, color: "#ae2a19" }}>
          ⚠ <strong>Sanity flag:</strong> The shared term(s) between candidate and merge target are only platform/vendor names (e.g. Snowflake, AWS). Different work streams that just happen to use the same tool. Manual decision required.
        </div>
      )}

      {/* Merge reasoning (from new task-fit prompt) */}
      {result?.merge_reasoning && (
        <div style={{ marginTop: 8, padding: 8, background: "#fafbfc", border: "1px solid #ebecf0", borderRadius: 4, fontSize: 11, color: "#42526e" }}>
          <strong style={{ color: "#5e6c84", fontSize: 10, textTransform: "uppercase" }}>LLM merge reasoning:</strong>
          <div style={{ marginTop: 2 }}>{result.merge_reasoning}</div>
        </div>
      )}

      {/* Per-topic evaluations — full audit trail of the LLM's task-fit checks */}
      {result?.evaluations && result.evaluations.length > 0 && (
        <details style={{ marginTop: 8, fontSize: 11 }}>
          <summary style={{ cursor: "pointer", color: "#5e6c84", fontWeight: 600, textTransform: "uppercase", fontSize: 10 }}>
            Task-fit evaluations ({result.evaluations.length} existing topic{result.evaluations.length === 1 ? "" : "s"} checked)
          </summary>
          <ul style={{ marginTop: 4, paddingLeft: 16, color: "#42526e" }}>
            {result.evaluations.map((e) => (
              <li key={e.topic_id} style={{ marginBottom: 4 }}>
                <span style={{ color: e.task_fit === "yes" ? "#36b37e" : "#97a0af", fontWeight: 600, marginRight: 4 }}>
                  {e.task_fit === "yes" ? "✓ YES" : "✗ no"}
                </span>
                <strong>{e.topic_name}</strong>: {e.reason}
              </li>
            ))}
          </ul>
        </details>
      )}

      {/* Lexical pre-check breakdown */}
      {result?.lexical_precheck && (
        <details style={{ marginTop: 8, fontSize: 11 }}>
          <summary style={{ cursor: "pointer", color: "#5e6c84", fontWeight: 600, textTransform: "uppercase", fontSize: 10 }}>
            Layer 1 — Mechanical pre-filter (IDF-weighted, no LLM)
            {result.lexical_precheck.qualified_topic_ids && (
              <span style={{ color: "#0052cc", marginLeft: 6 }}>
                · {result.lexical_precheck.qualified_topic_ids.length} qualified
              </span>
            )}
          </summary>
          <div style={{ marginTop: 4, paddingLeft: 12, color: "#42526e" }}>
            <div>
              Candidate key_terms: {result.lexical_precheck.candidate_terms.join(", ") || "(none)"}
            </div>
            <div style={{ marginTop: 4 }}>
              <strong>Mechanical scoring</strong> (threshold={result.lexical_precheck.threshold ?? "?"}, top_k={result.lexical_precheck.top_k ?? "?"}):
              {!result.lexical_precheck.scored_topics || result.lexical_precheck.scored_topics.length === 0 ? (
                <span> (no existing topics)</span>
              ) : (
                <ul style={{ marginTop: 2, paddingLeft: 16 }}>
                  {result.lexical_precheck.scored_topics.slice(0, 5).map((s) => (
                    <li key={s.topic_id} style={{ color: s.qualified ? "#172b4d" : "#97a0af", marginBottom: 2 }}>
                      <span style={{ color: s.qualified ? "#36b37e" : "#bfc5ce", fontWeight: 600 }}>
                        {s.qualified ? "✓" : "✗"}
                      </span>{" "}
                      <strong>{s.name}</strong> · combined={s.combined_score}{" "}
                      <span style={{ color: "#97a0af" }}>
                        (IDF-Jac={s.score_idf_jaccard}, task-subj={s.score_task_subject}, mentions={s.score_transcript_mentions})
                      </span>
                      {s.shared_terms_rare.length > 0 && (
                        <span style={{ color: "#974f0c", marginLeft: 4 }}>
                          rare-shared: {s.shared_terms_rare.join(", ")}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div style={{ marginTop: 4, fontWeight: 600 }}>
              Verdict hint: <span style={{ color: "#0052cc" }}>{result.lexical_precheck.verdict_hint}</span>
            </div>
          </div>
        </details>
      )}

      {/* LLM reasoning — citations that support the verdict */}
      {result && verdictCitations.length > 0 && (
        <details open style={{ marginTop: 8, fontSize: 11 }}>
          <summary style={{ cursor: "pointer", color: "#5e6c84", fontWeight: 600, textTransform: "uppercase", fontSize: 10 }}>
            Why LLM thinks this {result.verdict === "should_be_merged_with" ? `should merge with "${result.matched_topic_name}"` : "is new"} ({verdictCitations.length} quote{verdictCitations.length === 1 ? "" : "s"})
          </summary>
          <ul style={{ marginTop: 4, paddingLeft: 20, color: "#42526e" }}>
            {verdictCitations.map((c, i) => (
              <li key={i} style={{ marginBottom: 4 }}>
                <span style={{ fontStyle: "italic" }}>&quot;{c.quote}&quot;</span>
                <span style={{ color: "#97a0af", marginLeft: 4 }}>
                  ({c.call_id?.slice(0, 8) ?? "?"}…, lines {c.lines || "?"})
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {/* Side-by-side comparison when LLM suggests merge */}
      {result?.verdict === "should_be_merged_with" && mergeTarget && (
        <div style={{ marginTop: 8, padding: 8, background: "#fafbfc", border: "1px solid #ebecf0", borderRadius: 4 }}>
          <div style={{ fontSize: 10, color: "#5e6c84", fontWeight: 600, textTransform: "uppercase", marginBottom: 4 }}>
            Comparison
          </div>
          <div style={{ display: "flex", gap: 12, fontSize: 11 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, color: "#172b4d" }}>Candidate: {topic.name}</div>
              {topic.key_terms && topic.key_terms.length > 0 && (
                <div style={{ color: "#5e6c84" }}>key_terms: {topic.key_terms.join(", ")}</div>
              )}
              {topic.summary && <div style={{ color: "#5e6c84" }}>{topic.summary}</div>}
            </div>
            <div style={{ flex: 1, borderLeft: "1px solid #dfe1e6", paddingLeft: 12 }}>
              <div style={{ fontWeight: 600, color: "#172b4d" }}>Target: {mergeTarget.name}</div>
              {mergeTarget.key_terms && mergeTarget.key_terms.length > 0 && (
                <div style={{ color: "#5e6c84" }}>key_terms: {mergeTarget.key_terms.join(", ")}</div>
              )}
              {mergeTarget.summary && <div style={{ color: "#5e6c84" }}>{mergeTarget.summary}</div>}
              {mergeTarget.tasks && mergeTarget.tasks.length > 0 && (
                <div style={{ color: "#5e6c84", marginTop: 2 }}>
                  Tasks: {mergeTarget.tasks.slice(0, 3).map((t) => t.task).filter(Boolean).join("; ")}
                  {mergeTarget.tasks.length > 3 && ` +${mergeTarget.tasks.length - 3} more`}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Ungrounded items — handles both string and {type, text} shape */}
      {result?.extraction_grounded === false && result.ungrounded_items.length > 0 && (
        <div style={{ fontSize: 11, color: "#ae2a19", marginTop: 6 }}>
          ⚠ Items not grounded in current call transcript:{" "}
          {result.ungrounded_items
            .map((u) =>
              typeof u === "string" ? u : (u?.text ?? JSON.stringify(u))
            )
            .filter((s) => s && s !== "undefined")
            .join("; ") || "(LLM didn't specify)"}
        </div>
      )}

      {/* Failed citations (needs_manual_review) */}
      {result && result.needs_manual_review && (result.failed_citations?.length ?? 0) > 0 && (
        <details style={{ fontSize: 11, color: "#5e6c84", marginTop: 6 }}>
          <summary style={{ cursor: "pointer" }}>What went wrong with the LLM&apos;s evidence</summary>
          <ul style={{ marginTop: 4, paddingLeft: 20 }}>
            {(result.failed_citations ?? []).map((f, i) => (
              <li key={i} style={{ color: "#ae2a19" }}>{f}</li>
            ))}
          </ul>
        </details>
      )}

      {/* Extraction-grounding citations (if separate from verdict citations) */}
      {extractionCitations.length > 0 && (
        <details style={{ fontSize: 11, color: "#5e6c84", marginTop: 4 }}>
          <summary style={{ cursor: "pointer" }}>Extraction grounding ({extractionCitations.length} quote{extractionCitations.length === 1 ? "" : "s"})</summary>
          <ul style={{ marginTop: 4, paddingLeft: 20, color: "#42526e" }}>
            {extractionCitations.map((c, i) => (
              <li key={i} style={{ marginBottom: 4, fontStyle: "italic" }}>
                &quot;{c.quote}&quot;
              </li>
            ))}
          </ul>
        </details>
      )}

      {/* Decision row */}
      {result && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginTop: 10,
            paddingTop: 8,
            borderTop: "1px solid #f0f1f3",
            flexWrap: "wrap",
          }}
        >
          {/* EPIC-18 STREAM 4: auto-accepted truly_new — skip manual buttons */}
          {result.confidence?.auto_accept_eligible ? (
            <>
              <span
                style={{
                  fontSize: 11,
                  color: "#006644",
                  background: "#e3fcef",
                  border: "1px solid #abf5d1",
                  borderRadius: 4,
                  padding: "4px 10px",
                  fontWeight: 600,
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                }}
              >
                ✓ Auto-accepted as new (confidence {result.confidence.pct}%)
              </span>
              <button
                type="button"
                onClick={() => onDecisionChange({ action: "merge", merge_to_ids: result?.matched_topic_id ? [result.matched_topic_id] : [], merge_pending_names: [] })}
                style={{ ...decisionButton, fontSize: 10 }}
              >
                Override: merge instead
              </button>
            </>
          ) : (
            <>
          <span style={{ fontSize: 10, color: "#5e6c84", fontWeight: 600, textTransform: "uppercase" }}>
            Your decision:
          </span>
          <button
            type="button"
            onClick={() => onDecisionChange({ action: "new", merge_to_ids: [], merge_pending_names: [] })}
            style={isNewSelected ? decisionButtonSelected : decisionButton}
          >
            ✓ Confirm new
          </button>
          <button
            type="button"
            onClick={() => {
              const initial =
                decision.merge_to_ids.length > 0
                  ? decision.merge_to_ids
                  : result?.matched_topic_id
                    ? [result.matched_topic_id]
                    : [];
              setDraftIds(initial);
              setDraftPendingNames(decision.merge_pending_names);
            }}
            style={isMergeSelected || pickerOpen ? decisionButtonSelected : decisionButton}
          >
            ↻ Merge with…
            {result?.matched_topic_name && displayedIds.length === 0 && (
              <span style={{ fontSize: 9, color: "#5e6c84", fontWeight: 400, marginLeft: 4 }}>
                ({result.matched_topic_name})
              </span>
            )}
          </button>
          {pickerOpen && (
            <div
              style={{
                width: "100%",
                marginTop: 6,
                border: "1px solid #dfe1e6",
                borderRadius: 4,
                background: "#fafbfc",
              }}
            >
              <div
                style={{
                  padding: "6px 10px",
                  fontSize: 10,
                  color: "#5e6c84",
                  fontWeight: 600,
                  textTransform: "uppercase",
                  letterSpacing: ".04em",
                  borderBottom: "1px solid #ebecf0",
                }}
              >
                Pick topics to merge with{" "}
                <span style={{ color: "#0052cc", fontWeight: 700 }}>
                  ({totalSelected} selected: {displayedIds.length} old, {displayedPendingNames.length} new)
                </span>
              </div>
              <div style={{ display: "flex", gap: 0 }}>
                {/* LEFT — existing project topics */}
                <div style={{ flex: 1, borderRight: "1px solid #ebecf0" }}>
                  <div style={{ padding: "4px 8px", fontSize: 9, color: "#5e6c84", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".04em", background: "#f4f5f7" }}>
                    Existing project topics (old)
                  </div>
                  <div style={{ maxHeight: 220, overflowY: "auto", padding: 4 }}>
                    {projectTopics.length === 0 ? (
                      <div style={{ padding: 8, fontSize: 11, color: "#97a0af" }}>(none)</div>
                    ) : (
                      projectTopics.map((t) => {
                        const id = t.topic_id ?? "";
                        const checked = displayedIds.includes(id);
                        return (
                          <label
                            key={id}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 6,
                              padding: "4px 8px",
                              fontSize: 12,
                              cursor: "pointer",
                              color: checked ? "#0052cc" : "#172b4d",
                              background: checked ? "#deebff" : "transparent",
                              borderRadius: 3,
                              marginBottom: 1,
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(e) => {
                                const current = draftIds ?? decision.merge_to_ids;
                                const next = e.target.checked
                                  ? [...current, id]
                                  : current.filter((x) => x !== id);
                                setDraftIds(next);
                              }}
                              style={{ cursor: "pointer" }}
                            />
                            <span style={{ fontWeight: checked ? 600 : 400, flex: 1 }}>{t.name}</span>
                          </label>
                        );
                      })
                    )}
                  </div>
                </div>

                {/* RIGHT — other call topics from this call */}
                <div style={{ flex: 1 }}>
                  <div style={{ padding: "4px 8px", fontSize: 9, color: "#5e6c84", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".04em", background: "#f4f5f7" }}>
                    Other call topics (this call)
                  </div>
                  <div style={{ maxHeight: 220, overflowY: "auto", padding: 4 }}>
                    {otherPending.length === 0 ? (
                      <div style={{ padding: 8, fontSize: 11, color: "#97a0af" }}>
                        (no other new candidates in this call)
                      </div>
                    ) : (
                      otherPending.map((t) => {
                        const norm = t.name.toLowerCase().trim();
                        const checked = displayedPendingNames.includes(norm);
                        return (
                          <label
                            key={t.name}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 6,
                              padding: "4px 8px",
                              fontSize: 12,
                              cursor: "pointer",
                              color: checked ? "#0052cc" : "#172b4d",
                              background: checked ? "#deebff" : "transparent",
                              borderRadius: 3,
                              marginBottom: 1,
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(e) => {
                                const current = draftPendingNames ?? decision.merge_pending_names;
                                const next = e.target.checked
                                  ? [...current, norm]
                                  : current.filter((x) => x !== norm);
                                setDraftPendingNames(next);
                              }}
                              style={{ cursor: "pointer" }}
                            />
                            <span style={{ fontWeight: checked ? 600 : 400, flex: 1 }}>{t.name}</span>
                          </label>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>

              {totalSelected >= 2 && (
                <div
                  style={{
                    padding: "6px 10px",
                    fontSize: 10,
                    color: "#974f0c",
                    background: "#fff4e6",
                    borderTop: "1px solid #ffe0b3",
                    fontStyle: "italic",
                  }}
                >
                  M:N merge — a new topic will be created absorbing this candidate + {displayedIds.length} old topic(s) + {displayedPendingNames.length} other call topic(s). Old topics get archived; other call topics are merged into this one.
                </div>
              )}
              {totalSelected === 1 && displayedIds.length === 1 && (
                <div style={{ padding: "6px 10px", fontSize: 10, color: "#42526e", background: "#deebff", borderTop: "1px solid #b3d4ff" }}>
                  1:1 merge — candidate&apos;s tasks will be added to &quot;{topicNameById(displayedIds[0])}&quot;.
                </div>
              )}
              {totalSelected === 1 && displayedPendingNames.length === 1 && (
                <div style={{ padding: "6px 10px", fontSize: 10, color: "#42526e", background: "#deebff", borderTop: "1px solid #b3d4ff" }}>
                  Merging with another candidate &quot;{displayedPendingNames[0]}&quot; — a new topic will be created absorbing both.
                </div>
              )}

              <div
                style={{
                  display: "flex",
                  gap: 8,
                  padding: "6px 10px",
                  borderTop: "1px solid #ebecf0",
                  background: "white",
                  justifyContent: "flex-end",
                }}
              >
                <button
                  type="button"
                  onClick={() => {
                    setDraftIds(null);
                    setDraftPendingNames(null);
                  }}
                  style={{ fontSize: 11, padding: "4px 10px", borderRadius: 4, border: "1px solid #c1c7d0", background: "white", color: "#42526e", cursor: "pointer", fontFamily: "inherit" }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={totalSelected === 0}
                  onClick={() => {
                    onDecisionChange({
                      action: "merge",
                      merge_to_ids: displayedIds,
                      merge_pending_names: displayedPendingNames,
                    });
                    setDraftIds(null);
                    setDraftPendingNames(null);
                  }}
                  style={{
                    fontSize: 11,
                    padding: "4px 12px",
                    borderRadius: 4,
                    border: "none",
                    background: totalSelected === 0 ? "#f4f5f7" : "#0052cc",
                    color: totalSelected === 0 ? "#97a0af" : "white",
                    cursor: totalSelected === 0 ? "default" : "pointer",
                    fontFamily: "inherit",
                    fontWeight: 600,
                  }}
                >
                  {totalSelected >= 2 ? `Apply M:N merge (${totalSelected + 1} total topics)` : "Apply merge"}
                </button>
              </div>
            </div>
          )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function NotInCallCard({
  topic,
  result,
  decision,
  onDecisionChange,
}: {
  topic: TopicData;
  result?: VerifyNotDiscussedResult;
  decision: { action: "not_discussed" | "discussed" };
  onDecisionChange: (d: { action: "not_discussed" | "discussed" }) => void;
}) {
  const isNotDiscussedSelected = decision.action === "not_discussed";
  const isDiscussedSelected = decision.action === "discussed";
  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 10, color: "#97a0af", textTransform: "uppercase", letterSpacing: ".04em" }}>
          from topic:
        </span>
        <strong style={{ fontSize: 13, color: "#172b4d" }}>{topic.name}</strong>
        {result?.verdict === "not_discussed" && !result.needs_manual_review && (
          <span style={badgeGreen}>LLM: ✓ not discussed</span>
        )}
        {result?.verdict === "actually_discussed" && !result.needs_manual_review && (
          <span style={badgeAmber}>LLM: ↻ actually discussed</span>
        )}
        {result?.needs_manual_review && <span style={badgeRed}>⚠ LLM uncertain</span>}
      </div>
      {topic.summary && (
        <div style={{ fontSize: 11, color: "#5e6c84", marginTop: 6 }}>
          Latest snapshot: {topic.summary}
        </div>
      )}
      {/* EPIC-19: show the existing tasks that were not bound in this call */}
      {topic.tasks && topic.tasks.length > 0 && (
        <div style={{ marginTop: 6 }}>
          <div style={{ fontSize: 10, fontWeight: 600, color: "#5e6c84", textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 2 }}>
            Existing tasks not touched this call ({topic.tasks.length})
          </div>
          <ul style={{ fontSize: 12, color: "#42526e", margin: 0, paddingLeft: 16 }}>
            {topic.tasks.map((t, i) => (
              <li key={i} style={{ marginBottom: 2 }}>
                {t.task || <em style={{ color: "#97a0af" }}>(no task)</em>}
                {t.next_step && <span style={{ color: "#5e6c84" }}> → {t.next_step}</span>}
                {t.owner && <span style={{ color: "#97a0af", fontSize: 10 }}> ({t.owner})</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {result?.verdict === "actually_discussed" && result.citation && (
        <div style={{ fontSize: 11, color: "#42526e", marginTop: 4, fontStyle: "italic" }}>
          &quot;{result.citation.quote}&quot;
        </div>
      )}
      {result && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginTop: 10,
            paddingTop: 8,
            borderTop: "1px solid #f0f1f3",
            flexWrap: "wrap",
          }}
        >
          <span style={{ fontSize: 10, color: "#5e6c84", fontWeight: 600, textTransform: "uppercase" }}>
            Your decision:
          </span>
          <button
            type="button"
            onClick={() => onDecisionChange({ action: "not_discussed" })}
            style={isNotDiscussedSelected ? decisionButtonSelected : decisionButton}
          >
            ✓ Confirm not discussed
          </button>
          <button
            type="button"
            onClick={() => onDecisionChange({ action: "discussed" })}
            style={isDiscussedSelected ? decisionButtonSelected : decisionButton}
          >
            ↻ Was actually discussed → move to Merged
          </button>
        </div>
      )}
    </div>
  );
}

function MergedTopicCard({
  projectTopic,
  callMatches,
  matchingGroups,
  extracted,
  fromNew,
  fromNotDiscussed,
  callsById,
  fromNewSourceName,
  fromNewPending,
  fromNewResult,
  subordinateMergeNames,
  projectTopics,
  onRevertFromNew,
  onChangeMergeTarget,
}: {
  projectTopic: TopicData;
  callMatches: TopicData[];
  matchingGroups?: Array<{
    call_task_refs?: Array<{ call_topic_name?: string; task_id?: string }>;
    project_task_refs?: Array<{ project_topic_id?: string; task_id?: string }>;
    target_topic_name?: string | null;
  }>;
  extracted?: ExtractedUpdateResult;
  fromNew: boolean;
  fromNotDiscussed: boolean;
  callsById: Record<string, Pick<Call, "id" | "title" | "created_at">>;
  fromNewSourceName?: string;
  fromNewPending?: TopicData;
  fromNewResult?: VerifyNewResult;
  subordinateMergeNames?: string[];  // names of additional sources for M:N merges
  projectTopics: TopicData[];
  onRevertFromNew?: () => void;
  onChangeMergeTarget?: (new_target_id: string) => void;
}) {
  // The full "this call" list combines (a) topics matched via match_groups and
  // (b) the topic migrated by Pass ① (if any). Both are equally part of "what
  // this call contributes to this merge target".
  const allCallContributions: TopicData[] = [
    ...callMatches,
    ...(fromNewPending ? [fromNewPending] : []),
  ];
  const [showOverride, setShowOverride] = useState(false);
  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <strong style={{ fontSize: 13, color: "#172b4d" }}>{projectTopic.name}</strong>
        {fromNew && fromNewSourceName && (
          <span style={badgeAmber}>moved from New: &quot;{fromNewSourceName}&quot;</span>
        )}
        {(subordinateMergeNames?.length ?? 0) >= 1 && (
          <span style={{ ...badgeAmber, background: "#fff1f0", color: "#ae2a19", border: "1px solid #ffbdad" }}>
            M:N merge — also absorbing: {subordinateMergeNames!.join(", ")} (will be archived)
          </span>
        )}
        {fromNotDiscussed && <span style={badgeAmber}>moved from Not discussed</span>}
        {extracted && !extracted.needs_manual_review && (
          <span style={badgeGreen}>✓ Verified</span>
        )}
        {extracted?.needs_manual_review && (
          <span style={badgeRed}>⚠ needs manual review</span>
        )}
      </div>

      {/* Override controls for topics that migrated here from New */}
      {fromNew && fromNewSourceName && (onRevertFromNew || onChangeMergeTarget) && (
        <div style={{ marginTop: 6, fontSize: 11 }}>
          <button
            type="button"
            onClick={() => setShowOverride((v) => !v)}
            style={{
              fontSize: 10,
              color: "#5e6c84",
              background: "none",
              border: "none",
              cursor: "pointer",
              textDecoration: "underline",
              padding: 0,
            }}
          >
            {showOverride ? "▾ hide override" : "▸ change my mind"}
          </button>
          {showOverride && (
            <div style={{ marginTop: 4, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              {onRevertFromNew && (
                <button type="button" onClick={onRevertFromNew} style={decisionButton}>
                  ↺ Not a duplicate — move back to New
                </button>
              )}
              {onChangeMergeTarget && (
                <>
                  <span style={{ fontSize: 10, color: "#5e6c84" }}>or merge with a different topic:</span>
                  <select
                    defaultValue=""
                    onChange={(e) => {
                      if (e.target.value) onChangeMergeTarget(e.target.value);
                    }}
                    style={{
                      fontSize: 11,
                      padding: "4px 8px",
                      border: "1px solid #dfe1e6",
                      borderRadius: 4,
                      background: "white",
                      color: "#172b4d",
                      fontFamily: "inherit",
                    }}
                  >
                    <option value="">— pick another topic —</option>
                    {projectTopics
                      .filter((t) => t.topic_id !== projectTopic.topic_id)
                      .map((t) => (
                        <option key={t.topic_id} value={t.topic_id ?? ""}>
                          {t.name}
                        </option>
                      ))}
                  </select>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Side-by-side: PREVIOUS (latest project topic snapshot) | THIS CALL */}
      {!extracted && (
        <div style={{ display: "flex", gap: 12, marginTop: 8, fontSize: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, color: "#5e6c84", fontSize: 10 }}>
              PREVIOUS
            </div>
            {projectTopic.summary && (
              <div style={{ color: "#42526e", marginBottom: 4 }}>{projectTopic.summary}</div>
            )}
            {projectTopic.tasks && projectTopic.tasks.length > 0 ? (
              <ul style={{ fontSize: 11, color: "#5e6c84", margin: "2px 0 0", paddingLeft: 16 }}>
                {projectTopic.tasks.map((t, i) => (
                  <li key={`pt-${i}`}>
                    {t.task || <em style={{ color: "#97a0af" }}>(no task)</em>}
                    {t.next_step && <span style={{ color: "#97a0af" }}> → {t.next_step}</span>}
                    {t.owner && <span style={{ color: "#97a0af" }}> ({t.owner})</span>}
                  </li>
                ))}
              </ul>
            ) : (
              !projectTopic.summary && <div style={{ color: "#97a0af", fontStyle: "italic" }}>(no tasks yet)</div>
            )}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, color: "#5e6c84", fontSize: 10 }}>
              THIS CALL ({allCallContributions.length})
            </div>
            {/* Match-group topics — show per-group sub-sections when task-level groups available */}
            {matchingGroups && matchingGroups.length > 0 ? (
              matchingGroups.map((g, gi) => {
                // Build a lookup of all candidate tasks by task_id (across all callMatches' tasks)
                const allCandidateTasks = new Map<string, { task: string; next_step?: string; owner?: string; topicName: string }>();
                for (const m of callMatches) {
                  for (const t of m.tasks || []) {
                    if (t.task_id) {
                      allCandidateTasks.set(t.task_id, {
                        task: t.task,
                        next_step: t.next_step,
                        owner: t.owner,
                        topicName: m.name,
                      });
                    }
                  }
                }
                // Resolve the tasks bound in THIS group
                const groupTasks = (g.call_task_refs || [])
                  .map((r) => r.task_id ? allCandidateTasks.get(r.task_id) : null)
                  .filter((x): x is { task: string; next_step?: string; owner?: string; topicName: string } => !!x);
                if (groupTasks.length === 0) return null;
                const subGroupBg = gi % 2 === 0 ? "#fafbfc" : "#f4f5f7";
                return (
                  <div
                    key={`sg-${gi}`}
                    style={{
                      background: subGroupBg,
                      borderLeft: "3px solid #c1c7d0",
                      paddingLeft: 8,
                      paddingTop: 4,
                      paddingBottom: 4,
                      marginBottom: 6,
                      borderRadius: 2,
                    }}
                  >
                    <div style={{ fontSize: 10, fontWeight: 600, color: "#5e6c84", textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 2 }}>
                      Sub-group {gi + 1}
                      {g.target_topic_name && (
                        <span style={{ marginLeft: 6, color: "#974f0c", textTransform: "none", letterSpacing: 0 }}>
                          → new topic: &quot;{g.target_topic_name}&quot;
                        </span>
                      )}
                    </div>
                    <ul style={{ fontSize: 11, color: "#5e6c84", margin: 0, paddingLeft: 16 }}>
                      {groupTasks.map((t, ti) => (
                        <li key={`sgt-${gi}-${ti}`}>
                          <span style={{ color: "#42526e" }}>[{t.topicName}]</span>{" "}
                          {t.task || <em style={{ color: "#97a0af" }}>(no task)</em>}
                          {t.next_step && <span style={{ color: "#97a0af" }}> → {t.next_step}</span>}
                          {t.owner && <span style={{ color: "#97a0af" }}> ({t.owner})</span>}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })
            ) : (
              // Fallback: no matchingGroups — use flat callMatches rendering
              callMatches.map((m, i) => (
                <div key={`mg-${i}`} style={{ marginBottom: 6 }}>
                  <div style={{ color: "#42526e" }}>
                    <strong>{m.name}</strong>
                    {m.summary && <span style={{ color: "#5e6c84" }}>: {m.summary}</span>}
                  </div>
                  {m.tasks && m.tasks.length > 0 && (
                    <ul style={{ fontSize: 11, color: "#5e6c84", margin: "2px 0 0", paddingLeft: 16 }}>
                      {m.tasks.map((t, j) => (
                        <li key={`mt-${i}-${j}`}>
                          {t.task || <em style={{ color: "#97a0af" }}>(no task)</em>}
                          {t.next_step && <span style={{ color: "#97a0af" }}> → {t.next_step}</span>}
                          {t.owner && <span style={{ color: "#97a0af" }}> ({t.owner})</span>}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))
            )}
            {/* Pass ① migrated topic — full audit trail inline */}
            {fromNewPending && (
              <div style={{ marginBottom: 4 }}>
                <div style={{ color: "#42526e" }}>
                  <strong>{fromNewPending.name}</strong>{" "}
                  <span style={{ fontSize: 10, color: "#974f0c", background: "#fff4e6", padding: "1px 4px", borderRadius: 3, marginLeft: 4 }}>
                    via Pass ①
                  </span>
                </div>
                <ConfidenceGauge result={fromNewResult} />
                {fromNewPending.summary && (
                  <div style={{ color: "#5e6c84" }}>{fromNewPending.summary}</div>
                )}
                {fromNewPending.tasks && fromNewPending.tasks.length > 0 && (
                  <ul style={{ fontSize: 11, color: "#5e6c84", marginTop: 2, paddingLeft: 16 }}>
                    {fromNewPending.tasks.map((t, i) => (
                      <li key={i}>
                        {t.task}
                        {t.next_step && <> → {t.next_step}</>}
                      </li>
                    ))}
                  </ul>
                )}

                {/* Audit trail panels for the Pass ① migration */}
                {fromNewResult && (
                  <div style={{ marginTop: 6 }}>
                    {fromNewResult.merge_reasoning && (
                      <div style={{ padding: 6, background: "#fafbfc", border: "1px solid #ebecf0", borderRadius: 4, fontSize: 11, color: "#42526e", marginBottom: 4 }}>
                        <strong style={{ color: "#5e6c84", fontSize: 9, textTransform: "uppercase" }}>LLM merge reasoning:</strong>
                        <div style={{ marginTop: 2 }}>{fromNewResult.merge_reasoning}</div>
                      </div>
                    )}

                    {fromNewResult.evaluations && fromNewResult.evaluations.length > 0 && (
                      <details style={{ fontSize: 11, marginBottom: 2 }}>
                        <summary style={{ cursor: "pointer", color: "#5e6c84", fontWeight: 600, textTransform: "uppercase", fontSize: 9 }}>
                          Task-fit evaluations ({fromNewResult.evaluations.length} existing topic{fromNewResult.evaluations.length === 1 ? "" : "s"} checked)
                        </summary>
                        <ul style={{ marginTop: 4, paddingLeft: 16, color: "#42526e" }}>
                          {fromNewResult.evaluations.map((e) => (
                            <li key={e.topic_id} style={{ marginBottom: 4 }}>
                              <span style={{ color: e.task_fit === "yes" ? "#36b37e" : "#97a0af", fontWeight: 600, marginRight: 4 }}>
                                {e.task_fit === "yes" ? "✓ YES" : "✗ no"}
                              </span>
                              <strong>{e.topic_name}</strong>: {e.reason}
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}

                    {(fromNewResult.citations ?? []).filter((c) => !c.for || c.for === "verdict").length > 0 && (
                      <details style={{ fontSize: 11, marginBottom: 2 }}>
                        <summary style={{ cursor: "pointer", color: "#5e6c84", fontWeight: 600, textTransform: "uppercase", fontSize: 9 }}>
                          Why LLM picked this merge ({(fromNewResult.citations ?? []).filter((c) => !c.for || c.for === "verdict").length} quote{(fromNewResult.citations ?? []).filter((c) => !c.for || c.for === "verdict").length === 1 ? "" : "s"})
                        </summary>
                        <ul style={{ marginTop: 4, paddingLeft: 20, color: "#42526e" }}>
                          {(fromNewResult.citations ?? [])
                            .filter((c) => !c.for || c.for === "verdict")
                            .map((c, i) => (
                              <li key={i} style={{ marginBottom: 4 }}>
                                <span style={{ fontStyle: "italic" }}>&quot;{c.quote}&quot;</span>
                                <span style={{ color: "#97a0af", marginLeft: 4 }}>
                                  ({c.call_id?.slice(0, 8) ?? "?"}…, lines {c.lines || "?"})
                                </span>
                              </li>
                            ))}
                        </ul>
                      </details>
                    )}

                    {fromNewResult.lexical_precheck && (
                      <details style={{ fontSize: 11, marginBottom: 2 }}>
                        <summary style={{ cursor: "pointer", color: "#5e6c84", fontWeight: 600, textTransform: "uppercase", fontSize: 9 }}>
                          Layer 1 — Mechanical pre-filter (IDF-weighted, no LLM)
                        </summary>
                        <div style={{ marginTop: 4, paddingLeft: 12, color: "#42526e" }}>
                          <div>Candidate key_terms: {fromNewResult.lexical_precheck.candidate_terms.join(", ") || "(none)"}</div>
                          <div style={{ marginTop: 4 }}>
                            <strong>Mechanical scoring</strong> (threshold={fromNewResult.lexical_precheck.threshold ?? "?"}, top_k={fromNewResult.lexical_precheck.top_k ?? "?"}):
                            {!fromNewResult.lexical_precheck.scored_topics || fromNewResult.lexical_precheck.scored_topics.length === 0 ? (
                              <span> (no existing topics)</span>
                            ) : (
                              <ul style={{ marginTop: 2, paddingLeft: 16 }}>
                                {fromNewResult.lexical_precheck.scored_topics.slice(0, 5).map((s) => (
                                  <li key={s.topic_id} style={{ color: s.qualified ? "#172b4d" : "#97a0af" }}>
                                    <span style={{ color: s.qualified ? "#36b37e" : "#bfc5ce", fontWeight: 600 }}>
                                      {s.qualified ? "✓" : "✗"}
                                    </span>{" "}
                                    <strong>{s.name}</strong> · combined={s.combined_score}
                                    {s.shared_terms_rare.length > 0 && (
                                      <span style={{ color: "#974f0c", marginLeft: 4 }}>rare: {s.shared_terms_rare.join(", ")}</span>
                                    )}
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                          <div style={{ marginTop: 4, fontWeight: 600 }}>
                            Verdict hint: <span style={{ color: "#0052cc" }}>{fromNewResult.lexical_precheck.verdict_hint}</span>
                          </div>
                        </div>
                      </details>
                    )}

                    {fromNewResult.sanity_flag && (
                      <div style={{ marginTop: 4, padding: 6, background: "#fff1f0", border: "1px solid #ffbdad", borderRadius: 4, fontSize: 11, color: "#ae2a19" }}>
                        ⚠ <strong>Sanity flag:</strong> {fromNewResult.sanity_flag.replaceAll("_", " ")}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {extracted && (
        <div style={{ marginTop: 8 }}>
          <div style={{ fontSize: 12, color: "#42526e" }}>
            <strong>Status:</strong> {extracted.extracted_snapshot.status}
          </div>
          <div style={{ fontSize: 12, color: "#42526e", marginTop: 4 }}>
            {extracted.extracted_snapshot.summary}
          </div>
          {extracted.extracted_snapshot.tasks.length > 0 && (
            <ul style={{ fontSize: 12, color: "#5e6c84", marginTop: 6, paddingLeft: 20 }}>
              {extracted.extracted_snapshot.tasks.map((t, i) => (
                <li key={i}>
                  {t.task}
                  {t.next_step && <> → {t.next_step}</>}
                </li>
              ))}
            </ul>
          )}
          <EvidenceTrail entries={extracted.evidence_trail} callsById={callsById} />
        </div>
      )}
    </div>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────────

const cardStyle: React.CSSProperties = {
  padding: 10,
  marginBottom: 8,
  border: "1px solid #dfe1e6",
  borderRadius: 6,
  background: "white",
};

const passButton = (done: boolean): React.CSSProperties => ({
  padding: "5px 12px",
  borderRadius: 4,
  border: "none",
  fontFamily: "inherit",
  background: done ? "#36b37e" : "#0052cc",
  color: "white",
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
});

const badgeGreen: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  padding: "2px 6px",
  borderRadius: 3,
  background: "#e3fcef",
  color: "#006644",
  border: "1px solid #abf5d1",
};

const badgeAmber: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  padding: "2px 6px",
  borderRadius: 3,
  background: "#fff4e6",
  color: "#974f0c",
  border: "1px solid #ffe0b3",
};

const badgeRed: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  padding: "2px 6px",
  borderRadius: 3,
  background: "#fff1f0",
  color: "#ae2a19",
  border: "1px solid #ffbdad",
};

const decisionButton: React.CSSProperties = {
  fontSize: 11,
  padding: "5px 10px",
  borderRadius: 4,
  border: "1px solid #c1c7d0",
  background: "white",
  color: "#42526e",
  cursor: "pointer",
  fontFamily: "inherit",
  fontWeight: 600,
};

const decisionButtonSelected: React.CSSProperties = {
  ...decisionButton,
  background: "#0052cc",
  color: "white",
  border: "1px solid #0052cc",
};
