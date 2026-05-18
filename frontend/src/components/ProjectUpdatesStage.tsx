"use client";

import { useEffect, useRef, useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call, TopicData } from "@/types";

type Props = {
  callId: string;
  projectId: string;
  call: Call;
  onValidated: () => void;
  onPollCall?: () => Promise<void>;
};

const SEL: React.CSSProperties = {
  fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4,
  padding: "3px 7px", background: "white", color: "#172b4d",
  fontFamily: "inherit", cursor: "pointer",
};

const STATUS_BADGE: Record<string, React.CSSProperties> = {
  open:        { background: "#e9f0ff", color: "#0052cc" },
  in_progress: { background: "#fff4e6", color: "#974f0c" },
  resolved:    { background: "#e3fcef", color: "#006644" },
};

const SENTIMENT_COLOR: Record<string, string> = {
  positive: "#216e4e", neutral: "#5e6c84", concern: "#ae2a19",
};

function TopicRow({ topic, onChange, onViewEvidence }: {
  topic: TopicData;
  onChange: (t: TopicData) => void;
  onViewEvidence?: (topicId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [newFollowUp, setNewFollowUp] = useState("");
  const isNew = !topic.topic_id;

  return (
    <div style={{
      borderBottom: "1px solid #f0f1f3",
      paddingLeft: expanded ? 17 : 20,
      paddingRight: 20,
      paddingTop: 10,
      paddingBottom: 10,
      borderLeft: expanded ? "3px solid #0052cc" : `3px solid ${isNew ? "#79dbb2" : "transparent"}`,
      background: expanded ? "#fafbfc" : "white",
    }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, flex: 1, minWidth: 0 }}>
          {expanded ? (
            <input
              value={topic.name}
              onChange={(e) => onChange({ ...topic, name: e.target.value })}
              style={{ fontSize: 13, fontWeight: 600, color: "#172b4d",
                border: "none", borderBottom: "2px solid #0052cc", outline: "none",
                background: "transparent", flex: 1, minWidth: 0, fontFamily: "inherit" }}
            />
          ) : (
            <span style={{ fontSize: 13, fontWeight: 600, color: "#172b4d" }}>{topic.name}</span>
          )}
          <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
            padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap", flexShrink: 0,
            ...(STATUS_BADGE[topic.status ?? "open"] ?? STATUS_BADGE.open) }}>
            {(topic.status ?? "open").replace("_", " ")}
          </span>
          {isNew && (
            <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
              padding: "2px 6px", borderRadius: 3, background: "#f0fdf7", color: "#36b37e", flexShrink: 0 }}>
              New
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
          {onViewEvidence && topic.topic_id && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onViewEvidence(topic.topic_id!);
              }}
              style={{
                background: "none", border: "none", cursor: "pointer",
                fontSize: 11, color: "#0052cc", padding: 0, fontFamily: "inherit",
                textDecoration: "underline",
              }}
            >
              View evidence
            </button>
          )}
          <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase",
            color: SENTIMENT_COLOR[topic.sentiment ?? "neutral"] ?? "#5e6c84" }}>
            {topic.sentiment}
          </span>
          <button onClick={() => setExpanded((v) => !v)}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: 13,
              padding: "0 2px", color: expanded ? "#0052cc" : "#97a0af", lineHeight: 1 }}>
            ✎
          </button>
        </div>
      </div>

      {!expanded && topic.summary && (
        <p style={{ fontSize: 12, color: "#5e6c84", margin: "3px 0 0", lineHeight: 1.5 }}>
          {topic.summary}
        </p>
      )}
      {!expanded && (topic.follow_up_items ?? []).map((item, i) => (
        <div key={i} style={{ fontSize: 11, color: "#5e6c84", paddingTop: 2 }}>→ {item}</div>
      ))}

      {expanded && (
        <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <select value={topic.status ?? "open"} onChange={(e) => onChange({ ...topic, status: e.target.value as TopicData["status"] })} style={SEL}>
              <option value="open">Open</option>
              <option value="in_progress">In Progress</option>
              <option value="resolved">Resolved</option>
            </select>
            <select value={topic.owner ?? "Us"} onChange={(e) => onChange({ ...topic, owner: e.target.value as TopicData["owner"] })} style={SEL}>
              <option value="Us">Us</option>
              <option value="Client">Client</option>
              <option value="Both">Both</option>
            </select>
            <select value={topic.sentiment ?? "neutral"} onChange={(e) => onChange({ ...topic, sentiment: e.target.value as TopicData["sentiment"] })} style={SEL}>
              <option value="positive">Positive</option>
              <option value="neutral">Neutral</option>
              <option value="concern">Concern</option>
            </select>
          </div>
          <textarea
            value={topic.summary ?? ""}
            onChange={(e) => onChange({ ...topic, summary: e.target.value })}
            placeholder="Summary…"
            rows={3}
            style={{ fontSize: 12, color: "#172b4d", border: "1px solid #dfe1e6", borderRadius: 4,
              padding: "6px 8px", resize: "vertical", fontFamily: "inherit",
              width: "100%", boxSizing: "border-box" }}
          />
          <div>
            {(topic.follow_up_items ?? []).map((item, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                <span style={{ color: "#97a0af", fontSize: 11 }}>→</span>
                <input value={item}
                  onChange={(e) => {
                    const items = [...(topic.follow_up_items ?? [])];
                    items[i] = e.target.value;
                    onChange({ ...topic, follow_up_items: items });
                  }}
                  style={{ flex: 1, fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "3px 6px", fontFamily: "inherit" }}
                />
                <button onClick={() => onChange({ ...topic, follow_up_items: (topic.follow_up_items ?? []).filter((_, idx) => idx !== i) })}
                  style={{ background: "none", border: "none", cursor: "pointer", color: "#bfc5ce", fontSize: 11 }}>✕</button>
              </div>
            ))}
            <div style={{ display: "flex", gap: 6, marginTop: 2 }}>
              <input
                value={newFollowUp}
                onChange={(e) => setNewFollowUp(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && newFollowUp.trim()) {
                    onChange({ ...topic, follow_up_items: [...(topic.follow_up_items ?? []), newFollowUp.trim()] });
                    setNewFollowUp("");
                  }
                }}
                placeholder="Add follow-up…"
                style={{ flex: 1, fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "3px 6px", fontFamily: "inherit" }}
              />
              <button
                onClick={() => {
                  if (newFollowUp.trim()) {
                    onChange({ ...topic, follow_up_items: [...(topic.follow_up_items ?? []), newFollowUp.trim()] });
                    setNewFollowUp("");
                  }
                }}
                style={{ fontSize: 11, color: "#0052cc", background: "none", border: "1px solid #b3c6e8", borderRadius: 4, padding: "3px 10px", cursor: "pointer" }}>
                Add
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ProjectUpdatesStage({ callId, projectId, call, onValidated, onPollCall }: Props) {
  const alreadyMerged = call.merge_status === "done" && !!(call.merge_cache?.length);
  const [topics, setTopics] = useState<TopicData[]>(() => alreadyMerged ? (call.merge_cache ?? []) : []);
  const [starting, setStarting] = useState(false);   // button click in-flight
  const [merging, setMerging] = useState(() => call.merge_status === "processing");
  const [merged, setMerged] = useState(alreadyMerged);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(() => call.verification_status === "processing");
  const [verificationCache, setVerificationCache] = useState<Call["verification_cache"]>(call.verification_cache);
  // Track whether we've applied the cache to avoid overwriting user edits
  const mergeApplied = useRef(alreadyMerged);

  // Load topics on mount
  useEffect(() => {
    // If merge already done, load from cache
    if (call.merge_status === "done" && call.merge_cache) {
      setTopics(call.merge_cache);
      setMerged(true);
      mergeApplied.current = true;
      logger.info("Loaded topics from merge_cache", { component: "ProjectUpdatesStage" });
      return;
    }
    // Otherwise reconstruct from match groups (covers: idle, processing, failed)
    Promise.all([
      topicsAPI.getMatchGroups(callId),
      topicsAPI.getPending(callId),
      topicsAPI.priorToCall(projectId, callId),
    ]).then(([groups, pending, projectTopics]) => {
      const pendingByName = new Map(pending.map((t: TopicData) => [t.name.toLowerCase().trim(), t]));
      const projectById = new Map(projectTopics.map((t: TopicData) => [t.topic_id ?? "", t]));
      const matchedProjectIds = new Set(
        groups.flatMap((g: { project_topic_ids: string[]; call_topic_names: string[] }) => g.project_topic_ids)
      );

      const result: TopicData[] = [];

      for (const g of groups as { project_topic_ids: string[]; call_topic_names: string[] }[]) {
        if (g.project_topic_ids.length === 0) {
          for (const name of g.call_topic_names) {
            const ct = pendingByName.get(name.toLowerCase().trim());
            if (ct) result.push({ ...ct, topic_id: undefined });
          }
        } else {
          for (const pid of g.project_topic_ids) {
            const existing = projectById.get(pid);
            if (existing) {
              result.push({ ...existing, pending_merge: true });
            }
          }
        }
      }

      for (const pt of projectTopics as TopicData[]) {
        if (!matchedProjectIds.has(pt.topic_id ?? "")) {
          result.push({ ...pt, not_discussed: true });
        }
      }

      logger.info(`Auto-populated ${result.length} topics`, { component: "ProjectUpdatesStage" });
      setTopics(result);
    }).catch(() => setError("Failed to load topics"));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Watch for merge completion when polling
  useEffect(() => {
    if (call.merge_status === "done" && call.merge_cache && !mergeApplied.current) {
      setTopics(call.merge_cache);
      setMerged(true);
      setMerging(false);
      mergeApplied.current = true;
      logger.info("Merge complete — applied cache", { component: "ProjectUpdatesStage" });
    }
    if (call.merge_status === "failed" && merging) {
      setMerging(false);
      setError("Merge failed — please try again.");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [call.merge_status, call.merge_cache]);

  // Watch for verification completion
  useEffect(() => {
    if (call.verification_status === "done" && call.verification_cache) {
      setVerificationCache(call.verification_cache);
      setVerifying(false);
    }
    if (call.verification_status === "failed" && verifying) {
      setVerifying(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [call.verification_status, call.verification_cache]);

  // Poll every 3s while merging or verifying
  useEffect(() => {
    if ((!merging && !verifying) || !onPollCall) return;
    const interval = setInterval(async () => {
      await onPollCall();
    }, 3000);
    return () => clearInterval(interval);
  }, [merging, verifying, onPollCall]);

  async function handleRunMerge() {
    setStarting(true);
    setError(null);
    try {
      await topicsAPI.mergePreview(callId);
      setMerging(true);
      mergeApplied.current = false;
      logger.info("Merge started in background", { component: "ProjectUpdatesStage" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Merge failed");
    } finally {
      setStarting(false);
    }
  }

  async function handleValidate() {
    setValidating(true);
    setError(null);
    try {
      await topicsAPI.validateUpdates(callId, topics);
      onValidated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed");
    } finally {
      setValidating(false);
    }
  }

  async function handleRerunVerification() {
    setError(null);
    try {
      await topicsAPI.verifyNotDiscussed(callId);
      setVerifying(true);
      setVerificationCache(null);
      logger.info("Verification re-run triggered", { component: "ProjectUpdatesStage" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Re-run check failed");
    }
  }

  async function handlePromote(topic: TopicData) {
    // Move from not_discussed straight to editable Updated Topics section.
    // Persist as a ptid-only match group so re-running merge or refreshing the
    // page doesn't wipe the promotion (backend rebuilds from match_groups).
    if (!topic.topic_id) return;
    try {
      await topicsAPI.promoteNotDiscussed(callId, topic.topic_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Promote failed");
      return;
    }
    setTopics(prev => prev.map(t =>
      t === topic ? { ...t, not_discussed: false, pending_merge: false } : t
    ));
  }

  const newTopics = topics.filter(t => !t.not_discussed && !t.topic_id);
  const mergeTopics = topics.filter(t => t.pending_merge);
  const updatedTopics = topics.filter(t => !t.not_discussed && !!t.topic_id && !t.pending_merge);
  const notDiscussed = topics.filter(t => t.not_discussed);
  const discussed = topics.filter(t => !t.not_discussed);

  return (
    <>
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

      {/* Header */}
      <div style={{ padding: "16px 20px 12px", borderBottom: "1px solid #dfe1e6", flexShrink: 0 }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", margin: "0 0 4px" }}>
          Project Topic Updates
        </h2>
        <div style={{ fontSize: 12, color: "#5e6c84" }}>
          Step 2 of 2 — Review and merge topic updates before saving to the project.
        </div>
      </div>

      {error && (
        <div style={{ margin: "0 20px", marginTop: 12, background: "#fff1f0", border: "1px solid #ffbdad",
          borderRadius: 6, padding: "10px 14px", fontSize: 12, color: "#ae2a19", flexShrink: 0 }}>
          {error}
        </div>
      )}

      <div style={{ flex: 1, overflowY: "auto" }}>

        {/* Section 1: New Topics */}
        {newTopics.length > 0 && (
          <>
            <div style={{ padding: "10px 20px 6px", fontSize: 11, fontWeight: 700, color: "#5e6c84",
              textTransform: "uppercase", letterSpacing: ".05em", borderBottom: "1px solid #f4f5f7" }}>
              New Topics ({newTopics.length})
            </div>
            {newTopics.map((t) => {
              const i = topics.indexOf(t);
              return (
                <TopicRow
                  key={t.topic_id ?? t.name ?? i}
                  topic={t}
                  onChange={(updated) => {
                    const next = [...topics];
                    next[i] = updated;
                    setTopics(next);
                  }}
                />
              );
            })}
          </>
        )}

        {/* Section 2a: Needs Merge (before merge runs or while merging) */}
        {mergeTopics.length > 0 && (
          <div style={{ marginTop: newTopics.length > 0 ? 8 : 0 }}>
            <div style={{ padding: "8px 20px 6px", borderTop: newTopics.length > 0 ? "1px solid #dfe1e6" : undefined,
              borderBottom: "1px solid #dfe1e6", background: "#f4f5f7" }}>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "#97a0af",
                letterSpacing: ".05em" }}>
                Updated Topics — {mergeTopics.length} need{mergeTopics.length !== 1 ? "" : "s"} merge
              </div>
              <div style={{ fontSize: 11, color: "#97a0af", marginTop: 2 }}>
                {merging
                  ? "⏳ Merging in background… you can navigate away and come back."
                  : "Showing existing data — click Run Merge to generate AI-updated content"}
              </div>
            </div>

            {/* Run Merge button (only when not merging) */}
            {!merging && (
              <div style={{ padding: "8px 20px", borderBottom: "1px solid #f0f1f3" }}>
                <button
                  onClick={handleRunMerge}
                  disabled={starting}
                  style={{
                    padding: "7px 16px", borderRadius: 6, border: "none",
                    background: starting ? "#f4f5f7" : "#0052cc",
                    color: starting ? "#97a0af" : "white",
                    fontSize: 12, fontWeight: 600, cursor: starting ? "default" : "pointer",
                    fontFamily: "inherit",
                  }}
                >
                  {starting ? "Starting…" : `Run Merge for ${mergeTopics.length} topic${mergeTopics.length !== 1 ? "s" : ""}`}
                </button>
                <span style={{ fontSize: 11, color: "#97a0af", marginLeft: 12 }}>
                  Generates AI-merged summaries for matched topics
                </span>
              </div>
            )}

            {/* Placeholder rows — italic, read-only */}
            {mergeTopics.map((t, idx) => (
              <div key={t.topic_id ?? t.name ?? idx}
                style={{ opacity: 0.65, borderBottom: "1px solid #f0f1f3",
                  paddingLeft: 20, paddingRight: 20, paddingTop: 10, paddingBottom: 10,
                  borderLeft: "3px solid transparent", background: "white",
                  fontStyle: "italic" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "#172b4d" }}>{t.name}</span>
                  <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                    padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap", flexShrink: 0,
                    ...(STATUS_BADGE[t.status ?? "open"] ?? STATUS_BADGE.open) }}>
                    {(t.status ?? "open").replace("_", " ")}
                  </span>
                  <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase",
                    color: SENTIMENT_COLOR[t.sentiment ?? "neutral"] ?? "#5e6c84", marginLeft: "auto" }}>
                    {t.sentiment}
                  </span>
                </div>
                {t.summary && (
                  <p style={{ fontSize: 12, color: "#5e6c84", margin: "3px 0 0", lineHeight: 1.5 }}>
                    {t.summary}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Section 2b: Updated Topics (after merge runs — editable) */}
        {updatedTopics.length > 0 && (
          <div style={{ marginTop: newTopics.length > 0 ? 8 : 0 }}>
            <div style={{ padding: "8px 20px 6px", borderTop: newTopics.length > 0 ? "1px solid #dfe1e6" : undefined,
              borderBottom: "1px solid #dfe1e6", background: "#f4f5f7" }}>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "#5e6c84",
                letterSpacing: ".05em" }}>
                Updated Topics ({updatedTopics.length})
              </div>
              <div style={{ fontSize: 11, color: "#97a0af", marginTop: 2 }}>
                AI-merged summaries — review and edit before saving
              </div>
            </div>
            {updatedTopics.map((t) => {
              const i = topics.indexOf(t);
              return (
                <TopicRow
                  key={t.topic_id ?? t.name ?? i}
                  topic={t}
                  onChange={(updated) => {
                    const next = [...topics];
                    next[i] = updated;
                    setTopics(next);
                  }}
                />
              );
            })}
          </div>
        )}

        {/* Section 3: Not Discussed */}
        {notDiscussed.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={{ padding: "8px 20px 6px", borderTop: "1px solid #dfe1e6", borderBottom: "1px solid #dfe1e6",
              background: "#f4f5f7", display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "#97a0af",
                  letterSpacing: ".05em" }}>
                  Not discussed in this call&nbsp;&nbsp;({notDiscussed.length} topic{notDiscussed.length !== 1 ? "s" : ""})
                  {verifying && <span style={{ fontWeight: 400, textTransform: "none", marginLeft: 8 }}>⏳ Verifying…</span>}
                </div>
                <div style={{ fontSize: 11, color: "#97a0af", marginTop: 2 }}>
                  These topics exist in the project but were not mentioned in this call. They carry over unchanged.
                </div>
              </div>
              <button
                onClick={handleRerunVerification}
                disabled={verifying}
                title="Re-run the LLM check against the transcript for every topic below"
                style={{ padding: "4px 10px", borderRadius: 4, border: "1px solid #dfe1e6",
                  background: verifying ? "#f4f5f7" : "white", color: verifying ? "#97a0af" : "#5e6c84",
                  fontSize: 11, cursor: verifying ? "default" : "pointer", fontFamily: "inherit",
                  whiteSpace: "nowrap", flexShrink: 0 }}
              >
                {verifying ? "Checking…" : "Re-run check"}
              </button>
            </div>
            {notDiscussed.map((t, idx) => {
              const v = verificationCache?.[t.topic_id ?? ""];
              const hasEntry = !!v;
              const hasError = !!v?.error;
              const isFlagged = !hasError && v?.discussed === true;
              const isConfirmed = !hasError && v?.discussed === false;
              const isChecking = verifying && !hasEntry;
              const notChecked = !verifying && !hasEntry;
              return (
                <div key={t.topic_id ?? t.name ?? idx}
                  style={{
                    opacity: isFlagged ? 1 : 0.7,
                    borderBottom: "1px solid #f0f1f3",
                    paddingLeft: 20, paddingRight: 20, paddingTop: 10, paddingBottom: 10,
                    borderLeft: isFlagged ? "3px solid #ff991f" : hasError ? "3px solid #de350b" : "3px solid transparent",
                    background: isFlagged ? "#fffae6" : hasError ? "#ffebe6" : "white",
                  }}>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ color: "#97a0af", fontSize: 12 }}>•</span>
                    <span style={{ fontSize: 13, fontWeight: 600, color: "#172b4d" }}>{t.name}</span>
                    <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                      padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap", flexShrink: 0,
                      ...(STATUS_BADGE[t.status ?? "open"] ?? STATUS_BADGE.open) }}>
                      {(t.status ?? "open").replace("_", " ")}
                    </span>
                    {isFlagged && (
                      <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 3,
                        background: "#fff4e6", color: "#974f0c", border: "1px solid #ff991f", whiteSpace: "nowrap", flexShrink: 0 }}>
                        ⚠ Discussed in call
                      </span>
                    )}
                    {isConfirmed && (
                      <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 3,
                        background: "#e3fcef", color: "#006644", whiteSpace: "nowrap", flexShrink: 0 }}>
                        ✓ Check ran · not discussed
                      </span>
                    )}
                    {hasError && (
                      <span title={v?.error ?? ""} style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 3,
                        background: "#ffebe6", color: "#bf2600", border: "1px solid #de350b", whiteSpace: "nowrap", flexShrink: 0 }}>
                        ✕ Check failed
                      </span>
                    )}
                    {isChecking && (
                      <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 3,
                        background: "#deebff", color: "#0747a6", border: "1px solid #4c9aff", whiteSpace: "nowrap", flexShrink: 0 }}>
                        ⏳ Checking…
                      </span>
                    )}
                    {notChecked && (
                      <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 3,
                        background: "#f4f5f7", color: "#5e6c84", border: "1px solid #dfe1e6", whiteSpace: "nowrap", flexShrink: 0 }}>
                        — Not checked
                      </span>
                    )}
                    <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase",
                      color: SENTIMENT_COLOR[t.sentiment ?? "neutral"] ?? "#5e6c84", marginLeft: "auto" }}>
                      {t.sentiment}
                    </span>
                  </div>
                  {t.summary && (
                    <p style={{ fontSize: 12, color: "#5e6c84", margin: "3px 0 0 18px", lineHeight: 1.5 }}>
                      {t.summary}
                    </p>
                  )}
                  {isFlagged && v?.reasoning && (
                    <p style={{ fontSize: 11, color: "#974f0c", margin: "4px 0 0 18px", lineHeight: 1.4, fontStyle: "italic" }}>
                      {v.reasoning}
                    </p>
                  )}
                  {hasError && v?.error && (
                    <p style={{ fontSize: 11, color: "#bf2600", margin: "4px 0 0 18px", lineHeight: 1.4, fontStyle: "italic" }}>
                      {v.error}
                    </p>
                  )}
                  {isFlagged && (
                    <button
                      onClick={() => handlePromote(t)}
                      style={{
                        marginTop: 6, marginLeft: 18, padding: "4px 12px", borderRadius: 4,
                        border: "1px solid #ff991f", background: "#fff4e6", color: "#974f0c",
                        fontSize: 11, fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
                      }}
                    >
                      Promote to Updated →
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Action bar */}
      <div style={{ padding: "12px 20px", borderTop: "1px solid #dfe1e6", background: "white",
        display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
        <div>
          {merged && (
            <button
              onClick={handleRunMerge}
              disabled={starting || merging}
              style={{ padding: "7px 16px", borderRadius: 6, border: "1px solid #dfe1e6",
                background: "white", color: "#5e6c84", fontSize: 12, cursor: (starting || merging) ? "default" : "pointer",
                fontFamily: "inherit" }}
            >
              {starting ? "Starting…" : merging ? "Re-running…" : "Re-run Merge"}
            </button>
          )}
        </div>
        <button
          onClick={handleValidate}
          disabled={validating || discussed.length === 0 || merging}
          style={{ padding: "8px 22px", borderRadius: 6, border: "none",
            background: validating || discussed.length === 0 || merging ? "#f4f5f7" : "#0052cc",
            color: validating || discussed.length === 0 || merging ? "#97a0af" : "white",
            fontSize: 13, fontWeight: 600,
            cursor: validating || discussed.length === 0 || merging ? "default" : "pointer",
            fontFamily: "inherit" }}
        >
          {validating ? "Saving…" : merging ? "Merging…" : "Save & Continue →"}
        </button>
      </div>
    </div>
    </>
  );
}
