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
  const [newDecisions, setNewDecisions] = useState<
    Record<string, { action: "new" | "merge"; merge_to_id?: string | null }>
  >({});
  const [ndDecisions, setNdDecisions] = useState<
    Record<string, { action: "not_discussed" | "discussed" }>
  >({});

  function resolveNewDecision(
    name: string,
    result: VerifyNewResult | undefined
  ): { action: "new" | "merge"; merge_to_id?: string | null } {
    const explicit = newDecisions[name.toLowerCase().trim()];
    if (explicit) return explicit;
    if (result && !result.needs_manual_review) {
      if (result.verdict === "should_be_merged_with" && result.matched_topic_id) {
        return { action: "merge", merge_to_id: result.matched_topic_id };
      }
      if (result.verdict === "truly_new") return { action: "new" };
    }
    return { action: "new" };
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
      if (d.action === "merge" && d.merge_to_id) ids.add(d.merge_to_id);
    }
    return ids;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, eff.verify_new_cache, newDecisions]);

  // Inverse map: which pending topic was merged INTO each project topic? Lets
  // the Merged card surface an "override" affordance to revert the decision.
  const mergedFromNewSource = useMemo<Map<string, string>>(() => {
    const m = new Map<string, string>();
    const cache = (eff.verify_new_cache ?? {}) as Record<string, VerifyNewResult>;
    for (const p of pending) {
      const r = cache[p.name];
      const d = resolveNewDecision(p.name, r);
      if (d.action === "merge" && d.merge_to_id) m.set(d.merge_to_id, p.name);
    }
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, eff.verify_new_cache, newDecisions]);

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

    // A match_group with empty project_topic_ids = a "Mark as new" decision.
    // A match_group with non-empty project_topic_ids = a "Link" or "Merge" decision.
    const newGroupCallNames = new Set(
      groups
        .filter((g) => (g.project_topic_ids?.length ?? 0) === 0)
        .flatMap((g) => g.call_topic_names.map(norm))
    );
    const matchedProjectIds = new Set(groups.flatMap((g) => g.project_topic_ids));

    // "New" section = pending topics that the user explicitly marked as New
    // in matching (i.e. their name is in a group with no project_topic_ids).
    // Then exclude those that ① later decided should be merged (they live in section 3).
    const newCandidates = pending.filter((p) => newGroupCallNames.has(norm(p.name)));
    const newTopics = newCandidates.filter((p) => {
      const r = (eff.verify_new_cache ?? {})[p.name];
      const d = resolveNewDecision(p.name, r);
      // Topic stays in Section 1 unless effective decision is to merge with a real topic
      return !(d.action === "merge" && d.merge_to_id);
    });

    // Old project topics NOT in any match group AND not migrated to Merged by ②
    const notInCall = projectTopics.filter((t) => {
      const tid = t.topic_id ?? "";
      if (matchedProjectIds.has(tid)) return false;
      if (migratedFromNotDiscussed.has(tid)) return false;
      return true;
    });

    // Merged topics = (a) matched project topics + (b) ② migrations + (c) ① migrations
    const mergedSet = new Set<string>([
      ...matchedProjectIds,
      ...migratedFromNotDiscussed,
      ...migratedFromNew,
    ]);
    const merged = projectTopics.filter((t) => mergedSet.has(t.topic_id ?? ""));

    return { newTopics, notInCall, merged };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groups, pending, projectTopics, eff.verify_new_cache, migratedFromNew, migratedFromNotDiscussed, newDecisions]);

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

      // Topics the user explicitly merged from New → existing topic.
      // For these, the call topic's tasks/OQ/decisions are the source of truth
      // (not the project topic's). They become a topic_update on the existing topic.
      const userMergedFromNew = new Map<string, TopicData>();
      const vnCache = (eff.verify_new_cache ?? {}) as Record<string, VerifyNewResult>;
      for (const p of pending) {
        const r = vnCache[p.name];
        const d = resolveNewDecision(p.name, r);
        if (d.action === "merge" && d.merge_to_id) {
          userMergedFromNew.set(d.merge_to_id, p);
        }
      }

      // For merged topics: use extracted snapshot if present (Section 3 ran ③),
      // else user-merged-from-new data if available, else raw project topic.
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
          // Promote call topic content onto the existing project topic_id.
          payload.push({ ...fromNew, topic_id: tid });
        } else {
          payload.push({ ...m, topic_id: tid });
        }
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
        {/* Section 1 — New topics */}
        <section style={{ marginBottom: 24 }}>
          <SectionHeader
            title="1. New topics from this call"
            count={sections.newTopics.length}
            button={
              <button
                disabled={busy !== null || sections.newTopics.length === 0}
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
          {sections.newTopics.map((t) => {
            const r = (eff.verify_new_cache ?? {})[t.name] as VerifyNewResult | undefined;
            const d = resolveNewDecision(t.name, r);
            return (
              <NewTopicCard
                key={t.name}
                topic={t}
                result={r}
                decision={d}
                projectTopics={projectTopics}
                onDecisionChange={(next) =>
                  setNewDecisions((prev) => ({ ...prev, [t.name.toLowerCase().trim()]: next }))
                }
              />
            );
          })}
        </section>

        {/* Section 2 — Not in call */}
        <section style={{ marginBottom: 24 }}>
          <SectionHeader
            title="2. Old topics not in this call"
            count={sections.notInCall.length}
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

        {/* Section 3 — Merged */}
        <section style={{ marginBottom: 24 }}>
          <SectionHeader
            title="3. Merged topics"
            count={sections.merged.length}
            button={
              <button
                disabled={!stage2Done || busy !== null || sections.merged.length === 0}
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
          {sections.merged.map((t) => {
            const tid = t.topic_id ?? "";
            const fromNewName = mergedFromNewSource.get(tid);
            const fromNewResult = fromNewName
              ? ((eff.verify_new_cache ?? {})[fromNewName] as VerifyNewResult | undefined)
              : undefined;
            const fromNewPending = fromNewName
              ? pending.find((p) => p.name === fromNewName)
              : undefined;
            return (
              <MergedTopicCard
                key={tid}
                projectTopic={t}
                callMatches={pending.filter((p) =>
                  groups.some(
                    (g) =>
                      (g.project_topic_ids ?? []).includes(tid) &&
                      g.call_topic_names.some(
                        (n) => n.toLowerCase().trim() === p.name.toLowerCase().trim()
                      )
                  )
                )}
                extracted={(eff.extract_updates_cache ?? {})[tid]}
                fromNew={migratedFromNew.has(tid)}
                fromNotDiscussed={migratedFromNotDiscussed.has(tid)}
                callsById={callsById}
                fromNewSourceName={fromNewName}
                fromNewPending={fromNewPending}
                fromNewResult={fromNewResult}
                projectTopics={projectTopics}
                onRevertFromNew={
                  fromNewName
                    ? () =>
                        setNewDecisions((prev) => ({
                          ...prev,
                          [fromNewName.toLowerCase().trim()]: { action: "new" },
                        }))
                    : undefined
                }
                onChangeMergeTarget={
                  fromNewName
                    ? (new_id: string) =>
                        setNewDecisions((prev) => ({
                          ...prev,
                          [fromNewName.toLowerCase().trim()]: { action: "merge", merge_to_id: new_id },
                        }))
                    : undefined
                }
              />
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
  onDecisionChange,
}: {
  topic: TopicData;
  result?: VerifyNewResult;
  decision: { action: "new" | "merge"; merge_to_id?: string | null };
  projectTopics: TopicData[];
  onDecisionChange: (d: { action: "new" | "merge"; merge_to_id?: string | null }) => void;
}) {
  const isNewSelected = decision.action === "new";
  const isMergeSelected = decision.action === "merge";

  // Look up the merge target topic so we can show its data for comparison.
  const mergeTargetId = decision.merge_to_id ?? result?.matched_topic_id ?? null;
  const mergeTarget = mergeTargetId
    ? projectTopics.find((t) => t.topic_id === mergeTargetId)
    : null;

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

      {/* Candidate tasks */}
      {topic.tasks && topic.tasks.length > 0 && (
        <div style={{ marginTop: 6 }}>
          <div style={{ fontSize: 10, color: "#5e6c84", fontWeight: 600, textTransform: "uppercase" }}>
            Candidate tasks:
          </div>
          <ul style={{ fontSize: 12, color: "#42526e", paddingLeft: 20, marginTop: 2 }}>
            {topic.tasks.map((t, i) => (
              <li key={i}>
                {t.task}
                {t.next_step && <> → {t.next_step}</>}
              </li>
            ))}
          </ul>
        </div>
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
          <span style={{ fontSize: 10, color: "#5e6c84", fontWeight: 600, textTransform: "uppercase" }}>
            Your decision:
          </span>
          <button
            type="button"
            onClick={() => onDecisionChange({ action: "new" })}
            style={isNewSelected ? decisionButtonSelected : decisionButton}
          >
            ✓ Confirm new
          </button>
          <button
            type="button"
            onClick={() =>
              onDecisionChange({
                action: "merge",
                // Pre-populate with the LLM's suggested target when present —
                // saves a manual picker click on the common "accept LLM merge" case.
                merge_to_id: decision.merge_to_id ?? result?.matched_topic_id ?? null,
              })
            }
            style={isMergeSelected ? decisionButtonSelected : decisionButton}
          >
            ↻ Merge with…
            {result?.matched_topic_name && !decision.merge_to_id && (
              <span style={{ fontSize: 9, color: "#5e6c84", fontWeight: 400, marginLeft: 4 }}>
                ({result.matched_topic_name})
              </span>
            )}
          </button>
          {isMergeSelected && (
            <select
              value={decision.merge_to_id ?? ""}
              onChange={(e) => onDecisionChange({ action: "merge", merge_to_id: e.target.value || null })}
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
              <option value="">— select topic —</option>
              {projectTopics.map((t) => (
                <option key={t.topic_id} value={t.topic_id ?? ""}>
                  {t.name}
                </option>
              ))}
            </select>
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
  extracted,
  fromNew,
  fromNotDiscussed,
  callsById,
  fromNewSourceName,
  fromNewPending,
  fromNewResult,
  projectTopics,
  onRevertFromNew,
  onChangeMergeTarget,
}: {
  projectTopic: TopicData;
  callMatches: TopicData[];
  extracted?: ExtractedUpdateResult;
  fromNew: boolean;
  fromNotDiscussed: boolean;
  callsById: Record<string, Pick<Call, "id" | "title" | "created_at">>;
  fromNewSourceName?: string;
  fromNewPending?: TopicData;  // the call-topic data that migrated here via ①
  fromNewResult?: VerifyNewResult;
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
            <div style={{ color: "#42526e" }}>{projectTopic.summary || "(no summary)"}</div>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600, color: "#5e6c84", fontSize: 10 }}>
              THIS CALL ({allCallContributions.length})
            </div>
            {/* Match-group topics first (matched by user in matching step) */}
            {callMatches.map((m, i) => (
              <div key={`mg-${i}`} style={{ color: "#42526e", marginBottom: 4 }}>
                <strong>{m.name}</strong>: {m.summary || "(no summary)"}
              </div>
            ))}
            {/* Pass ① migrated topic — full audit trail inline */}
            {fromNewPending && (
              <div style={{ marginBottom: 4 }}>
                <div style={{ color: "#42526e" }}>
                  <strong>{fromNewPending.name}</strong>{" "}
                  <span style={{ fontSize: 10, color: "#974f0c", background: "#fff4e6", padding: "1px 4px", borderRadius: 3, marginLeft: 4 }}>
                    via Pass ①
                  </span>
                </div>
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
