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

  // Migrations from ① and ②
  const migratedFromNew = useMemo<Set<string>>(() => {
    const cache = call.verify_new_cache ?? {};
    const ids = new Set<string>();
    for (const r of Object.values(cache)) {
      if (r?.verdict === "should_be_merged_with" && r.matched_topic_id) {
        ids.add(r.matched_topic_id);
      }
    }
    return ids;
  }, [call.verify_new_cache]);

  const migratedFromNotDiscussed = useMemo<Set<string>>(() => {
    const cache = call.verify_not_discussed_cache ?? {};
    const ids = new Set<string>();
    for (const [tid, r] of Object.entries(cache)) {
      if (r?.verdict === "actually_discussed") ids.add(tid);
    }
    return ids;
  }, [call.verify_not_discussed_cache]);

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
      const r = (call.verify_new_cache ?? {})[p.name];
      return !(r && r.verdict === "should_be_merged_with");
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
  }, [groups, pending, projectTopics, call.verify_new_cache, migratedFromNew, migratedFromNotDiscussed]);

  const stage1Done = call.verify_new_status === "done";
  const stage2Done = call.verify_not_discussed_status === "done";
  const stage3Done = call.extract_updates_status === "done";
  const allDone = stage1Done && stage2Done && stage3Done;

  const triggerPass = async (which: "①" | "②" | "③") => {
    setBusy(which);
    setError(null);
    try {
      if (which === "①") await topicsAPI.verifyNew(call.id);
      else if (which === "②") await topicsAPI.verifyNotDiscussed(call.id);
      else await topicsAPI.extractUpdates(call.id);

      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        try {
          const fresh = await callsAPI.getCall(call.id);
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
            // Notify parent to refresh the call prop so cache fields appear in state.
            if (onPollCall) {
              await onPollCall();
            } else {
              // Fallback: hard reload so the parent re-fetches.
              window.location.reload();
            }
          }
        } catch (e) {
          logger.error("[ProjectUpdatesStage] poll failed", { data: e });
        }
      }, 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to trigger pass");
      setBusy(null);
    }
  };

  const handleSaveContinue = async () => {
    setSaving(true);
    setError(null);
    try {
      const extractCache = call.extract_updates_cache ?? {};
      const matchedProjectIds = new Set(groups.flatMap((g) => g.project_topic_ids));
      // matchedProjectIds is used implicitly via sections.merged — suppress unused var
      void matchedProjectIds;

      const payload: TopicData[] = [];

      // For new topics that truly are new (not migrated): persist raw pending data
      for (const p of sections.newTopics) {
        payload.push({ ...p, topic_id: null });
      }

      // For merged topics: use extracted snapshot if present, else fall back to raw
      for (const m of sections.merged) {
        const tid = m.topic_id ?? "";
        const extracted = extractCache[tid];
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
            citations: [], // citations live in extract cache; let backend pick them up
            evidence_trail: extracted.evidence_trail,
            needs_manual_review: extracted.needs_manual_review,
          });
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
          {sections.newTopics.map((t) => (
            <NewTopicCard
              key={t.name}
              topic={t}
              result={(call.verify_new_cache ?? {})[t.name]}
            />
          ))}
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
          {sections.notInCall.map((t) => (
            <NotInCallCard
              key={t.topic_id}
              topic={t}
              result={(call.verify_not_discussed_cache ?? {})[t.topic_id ?? ""]}
            />
          ))}
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
          {sections.merged.map((t) => (
            <MergedTopicCard
              key={t.topic_id}
              projectTopic={t}
              callMatches={pending.filter((p) =>
                groups.some(
                  (g) =>
                    (g.project_topic_ids ?? []).includes(t.topic_id ?? "") &&
                    g.call_topic_names.some(
                      (n) => n.toLowerCase().trim() === p.name.toLowerCase().trim()
                    )
                )
              )}
              extracted={(call.extract_updates_cache ?? {})[t.topic_id ?? ""]}
              fromNew={migratedFromNew.has(t.topic_id ?? "")}
              fromNotDiscussed={migratedFromNotDiscussed.has(t.topic_id ?? "")}
              callsById={callsById}
            />
          ))}
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

function NewTopicCard({ topic, result }: { topic: TopicData; result?: VerifyNewResult }) {
  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <strong style={{ fontSize: 13, color: "#172b4d" }}>{topic.name}</strong>
        {result?.verdict === "truly_new" && <span style={badgeGreen}>✓ truly new</span>}
        {result?.verdict === "should_be_merged_with" && (
          <span style={badgeAmber}>↻ moved to merged → {result.matched_topic_name}</span>
        )}
        {result?.needs_manual_review && (
          <span style={badgeRed}>⚠ needs manual review</span>
        )}
      </div>
      {topic.tasks && topic.tasks.length > 0 && (
        <ul style={{ fontSize: 12, color: "#5e6c84", marginTop: 6, paddingLeft: 20 }}>
          {topic.tasks.map((t, i) => (
            <li key={i}>
              {t.task}
              {t.next_step && <> → {t.next_step}</>}
            </li>
          ))}
        </ul>
      )}
      {result?.extraction_grounded === false && result.ungrounded_items.length > 0 && (
        <div style={{ fontSize: 11, color: "#ae2a19", marginTop: 6 }}>
          ⚠ Ungrounded items: {result.ungrounded_items.map((u) => u.text).join(", ")}
        </div>
      )}
    </div>
  );
}

function NotInCallCard({
  topic,
  result,
}: {
  topic: TopicData;
  result?: VerifyNotDiscussedResult;
}) {
  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <strong style={{ fontSize: 13, color: "#172b4d" }}>{topic.name}</strong>
        {result?.verdict === "not_discussed" && (
          <span style={badgeGreen}>✓ not discussed</span>
        )}
        {result?.verdict === "actually_discussed" && (
          <span style={badgeAmber}>↻ actually discussed — moved to merged</span>
        )}
        {result?.needs_manual_review && <span style={badgeRed}>⚠ needs manual review</span>}
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
}: {
  projectTopic: TopicData;
  callMatches: TopicData[];
  extracted?: ExtractedUpdateResult;
  fromNew: boolean;
  fromNotDiscussed: boolean;
  callsById: Record<string, Pick<Call, "id" | "title" | "created_at">>;
}) {
  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <strong style={{ fontSize: 13, color: "#172b4d" }}>{projectTopic.name}</strong>
        {fromNew && <span style={badgeAmber}>moved from New</span>}
        {fromNotDiscussed && <span style={badgeAmber}>moved from Not discussed</span>}
        {extracted && !extracted.needs_manual_review && (
          <span style={badgeGreen}>✓ Verified</span>
        )}
        {extracted?.needs_manual_review && (
          <span style={badgeRed}>⚠ needs manual review</span>
        )}
      </div>

      {/* Side-by-side: previous (project topic latest snapshot) | this call (call topics merged into this group) */}
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
              THIS CALL ({callMatches.length})
            </div>
            {callMatches.map((m, i) => (
              <div key={i} style={{ color: "#42526e", marginBottom: 4 }}>
                <strong>{m.name}</strong>: {m.summary || "(no summary)"}
              </div>
            ))}
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
