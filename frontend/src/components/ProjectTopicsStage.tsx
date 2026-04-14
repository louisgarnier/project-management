"use client";

import { useCallback, useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type {
  Call, TopicData, AggregateResult, TopicSavePayload, TopicDisposition,
  TopicStatus, TopicOwner, TopicSentiment,
} from "@/types";

type Props = {
  call: Call;
  initialResult: AggregateResult | null;
  onValidated: () => void;
};

type BucketType = "followed_up" | "not_discussed" | "new_topics";

type EditableTopic = TopicData & {
  disposition?: TopicDisposition;
  _linkedTopicId?: string | null;
};

// ── Styles ─────────────────────────────────────────────────────────────────────

const STATUS_BADGE: Record<string, React.CSSProperties> = {
  open:        { background: "#e9f0ff", color: "#0052cc" },
  in_progress: { background: "#fff4e6", color: "#974f0c" },
  resolved:    { background: "#e3fcef", color: "#006644" },
};

const SENTIMENT_COLOR: Record<string, string> = {
  positive: "#216e4e",
  neutral:  "#5e6c84",
  concern:  "#ae2a19",
};

const SEL: React.CSSProperties = {
  fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4,
  padding: "3px 7px", background: "white", color: "#172b4d",
  fontFamily: "inherit", cursor: "pointer",
};

// ── Topic row ──────────────────────────────────────────────────────────────────

function TopicRow({
  topic,
  bucket,
  existingTopics,
  onChange,
  onDelete,
  onLink,
  callIsLocked,
}: {
  topic: EditableTopic;
  bucket: BucketType;
  existingTopics: TopicData[];
  onChange: (t: EditableTopic) => void;
  onDelete: () => void;
  onLink: (topicId: string, topicName: string) => void;
  callIsLocked: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [showPicker, setShowPicker] = useState(false);
  const [search, setSearch] = useState("");
  const [newFollowUp, setNewFollowUp] = useState("");

  const filtered = existingTopics.filter((t) =>
    t.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={{
      borderBottom: "1px solid #f0f1f3",
      paddingLeft: expanded ? 17 : 20,
      paddingRight: 20,
      paddingTop: 10,
      paddingBottom: 10,
      borderLeft: expanded ? "3px solid #0052cc" : "3px solid transparent",
      background: expanded ? "#fafbfc" : "white",
      opacity: callIsLocked ? 0.75 : 1,
    }}>

      {/* Header row */}
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, flex: 1, minWidth: 0 }}>
          {expanded && !callIsLocked ? (
            <input
              value={topic.name}
              onChange={(e) => onChange({ ...topic, name: e.target.value })}
              style={{
                fontSize: 13, fontWeight: 600, color: "#172b4d",
                border: "none", borderBottom: "2px solid #0052cc", outline: "none",
                background: "transparent", flex: 1, minWidth: 0, fontFamily: "inherit",
              }}
            />
          ) : (
            <span style={{ fontSize: 13, fontWeight: 600, color: "#172b4d" }}>{topic.name}</span>
          )}
          <span style={{
            fontSize: 9, fontWeight: 700, textTransform: "uppercase",
            padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap", flexShrink: 0,
            ...(STATUS_BADGE[topic.status] ?? STATUS_BADGE.open),
          }}>
            {topic.status?.replace("_", " ")}
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
          <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: SENTIMENT_COLOR[topic.sentiment] ?? "#5e6c84" }}>
            {topic.sentiment}
          </span>
          {bucket === "new_topics" && !callIsLocked && (
            <button
              onClick={() => { setShowPicker((v) => !v); setExpanded(true); }}
              style={{ fontSize: 10, padding: "2px 8px", borderRadius: 4,
                border: "1px solid #b3c6e8", background: "#e9f0ff", color: "#0052cc",
                cursor: "pointer", whiteSpace: "nowrap", fontFamily: "inherit" }}
            >
              Link →
            </button>
          )}
          {!callIsLocked && (
            <button
              onClick={() => setExpanded((v) => !v)}
              title="Edit"
              style={{ background: "none", border: "none", cursor: "pointer", fontSize: 13, padding: "0 2px",
                color: expanded ? "#0052cc" : "#97a0af", lineHeight: 1 }}
            >
              ✎
            </button>
          )}
          {!callIsLocked && (
            <button
              onClick={onDelete}
              title="Remove"
              style={{ background: "none", border: "none", cursor: "pointer", fontSize: 13, padding: "0 2px", color: "#bfc5ce", lineHeight: 1 }}
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Collapsed view */}
      {!expanded && (
        <>
          {topic.summary && (
            <p style={{ fontSize: 12, color: "#5e6c84", margin: "3px 0 0", lineHeight: 1.5 }}>{topic.summary}</p>
          )}
          {(topic.follow_up_items ?? []).map((item, i) => (
            <div key={i} style={{ fontSize: 11, color: "#5e6c84", paddingTop: 2 }}>→ {item}</div>
          ))}
          {/* Not-discussed disposition buttons (always visible for this bucket) */}
          {bucket === "not_discussed" && !callIsLocked && (
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <button
                onClick={() => onChange({ ...topic, disposition: "keep_as_is" })}
                style={{ flex: 1, padding: "4px 0", fontSize: 10, borderRadius: 4, cursor: "pointer",
                  border: "1px solid", fontWeight: 600, fontFamily: "inherit",
                  background: topic.disposition === "keep_as_is" ? "#e9f0ff" : "white",
                  borderColor: topic.disposition === "keep_as_is" ? "#0052cc" : "#dfe1e6",
                  color: topic.disposition === "keep_as_is" ? "#0052cc" : "#5e6c84" }}
              >
                Keep as-is
              </button>
              <button
                onClick={() => onChange({ ...topic, disposition: "archive" })}
                style={{ flex: 1, padding: "4px 0", fontSize: 10, borderRadius: 4, cursor: "pointer",
                  border: "1px solid", fontWeight: 600, fontFamily: "inherit",
                  background: topic.disposition === "archive" ? "#fff4e6" : "white",
                  borderColor: topic.disposition === "archive" ? "#ff8b00" : "#dfe1e6",
                  color: topic.disposition === "archive" ? "#974f0c" : "#5e6c84" }}
              >
                Archive
              </button>
            </div>
          )}
        </>
      )}

      {/* Expanded edit controls */}
      {expanded && !callIsLocked && (
        <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 8 }}>

          {/* Link to existing picker */}
          {showPicker && bucket === "new_topics" && (
            <div style={{ border: "1px solid #dfe1e6", borderRadius: 6, padding: 8, background: "#fafbfc" }}>
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search existing topics…"
                autoFocus
                style={{ width: "100%", fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "4px 7px", fontFamily: "inherit", boxSizing: "border-box" }}
              />
              <div style={{ maxHeight: 120, overflowY: "auto", marginTop: 6 }}>
                {filtered.length === 0 && <p style={{ fontSize: 11, color: "#97a0af", padding: 4, margin: 0 }}>No matches</p>}
                {filtered.map((t) => (
                  <button key={t.topic_id} onClick={() => { if (t.topic_id) { onLink(t.topic_id, t.name); setShowPicker(false); setSearch(""); } }}
                    style={{ display: "block", width: "100%", textAlign: "left", padding: "5px 8px", fontSize: 11,
                      border: "none", background: "none", cursor: "pointer", borderRadius: 4, color: "#172b4d", fontFamily: "inherit" }}>
                    {t.name}
                  </button>
                ))}
              </div>
              <button onClick={() => setShowPicker(false)} style={{ fontSize: 10, color: "#97a0af", border: "none", background: "none", cursor: "pointer", marginTop: 4 }}>
                Cancel
              </button>
            </div>
          )}

          {/* Dropdowns */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <select value={topic.status} onChange={(e) => onChange({ ...topic, status: e.target.value as TopicStatus })} style={SEL}>
              <option value="open">Open</option>
              <option value="in_progress">In Progress</option>
              <option value="resolved">Resolved</option>
            </select>
            <select value={topic.owner} onChange={(e) => onChange({ ...topic, owner: e.target.value as TopicOwner })} style={SEL}>
              <option value="Us">Us</option>
              <option value="Client">Client</option>
              <option value="Both">Both</option>
            </select>
            <select value={topic.sentiment} onChange={(e) => onChange({ ...topic, sentiment: e.target.value as TopicSentiment })} style={SEL}>
              <option value="positive">Positive</option>
              <option value="neutral">Neutral</option>
              <option value="concern">Concern</option>
            </select>
          </div>

          {/* Summary */}
          <textarea
            value={topic.summary}
            onChange={(e) => onChange({ ...topic, summary: e.target.value })}
            placeholder="Summary…"
            rows={2}
            style={{ fontSize: 12, color: "#172b4d", border: "1px solid #dfe1e6", borderRadius: 4,
              padding: "6px 8px", resize: "vertical", fontFamily: "inherit", width: "100%", boxSizing: "border-box" }}
          />

          {/* Follow-ups */}
          <div>
            {(topic.follow_up_items ?? []).map((item, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                <span style={{ color: "#97a0af", fontSize: 11 }}>→</span>
                <input
                  value={item}
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
                onClick={() => { if (newFollowUp.trim()) { onChange({ ...topic, follow_up_items: [...(topic.follow_up_items ?? []), newFollowUp.trim()] }); setNewFollowUp(""); } }}
                style={{ fontSize: 11, color: "#0052cc", background: "none", border: "1px solid #b3c6e8", borderRadius: 4, padding: "3px 10px", cursor: "pointer" }}
              >Add</button>
            </div>
          </div>

          {/* Not-discussed disposition in expanded mode too */}
          {bucket === "not_discussed" && (
            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={() => onChange({ ...topic, disposition: "keep_as_is" })}
                style={{ flex: 1, padding: "4px 0", fontSize: 10, borderRadius: 4, cursor: "pointer",
                  border: "1px solid", fontWeight: 600, fontFamily: "inherit",
                  background: topic.disposition === "keep_as_is" ? "#e9f0ff" : "white",
                  borderColor: topic.disposition === "keep_as_is" ? "#0052cc" : "#dfe1e6",
                  color: topic.disposition === "keep_as_is" ? "#0052cc" : "#5e6c84" }}
              >Keep as-is</button>
              <button
                onClick={() => onChange({ ...topic, disposition: "archive" })}
                style={{ flex: 1, padding: "4px 0", fontSize: 10, borderRadius: 4, cursor: "pointer",
                  border: "1px solid", fontWeight: 600, fontFamily: "inherit",
                  background: topic.disposition === "archive" ? "#fff4e6" : "white",
                  borderColor: topic.disposition === "archive" ? "#ff8b00" : "#dfe1e6",
                  color: topic.disposition === "archive" ? "#974f0c" : "#5e6c84" }}
              >Archive</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Bucket section header ──────────────────────────────────────────────────────

function BucketHeader({ label, count, color }: { label: string; count: number; color: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 20px 6px",
      borderBottom: "1px solid #f0f1f3", background: "#fafbfc" }}>
      <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase",
        letterSpacing: ".06em", color: "#5e6c84" }}>{label}</span>
      <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
        padding: "2px 6px", borderRadius: 3, background: color, color: "white" }}>{count}</span>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function ProjectTopicsStage({ call, initialResult, onValidated }: Props) {
  const [result, setResult] = useState<AggregateResult | null>(initialResult);
  const [followed, setFollowed] = useState<EditableTopic[]>([]);
  const [notDiscussed, setNotDiscussed] = useState<EditableTopic[]>([]);
  const [newTopics, setNewTopics] = useState<EditableTopic[]>([]);
  const [existingTopics, setExistingTopics] = useState<TopicData[]>([]);
  const [loading, setLoading] = useState(!initialResult);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!result) return;
    setFollowed((result.followed_up ?? []).map((t) => ({ ...t })));
    setNotDiscussed((result.not_discussed ?? []).map((t) => ({ ...t, disposition: undefined })));
    setNewTopics((result.new_topics ?? []).map((t) => ({ ...t })));
  }, [result]);

  useEffect(() => {
    topicsAPI.listForProject(call.project_id).then(setExistingTopics).catch(() => {});
  }, [call.project_id]);

  const reAggregate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      logger.info("Re-running Step 1+2 (state lost)", { component: "ProjectTopicsStage" });
      const step1 = await topicsAPI.extractCall(call.id);
      const step2 = await topicsAPI.aggregate(call.id, step1);
      setResult(step2);
    } catch (err) {
      logger.error("Re-aggregation failed", { component: "ProjectTopicsStage", data: err });
      setError(err instanceof Error ? err.message : "Failed to load topics");
    } finally {
      setLoading(false);
    }
  }, [call.id]);

  useEffect(() => {
    if (!initialResult) reAggregate();
  }, [initialResult, reAggregate]);

  function handleLink(newTopicIdx: number, topicId: string, topicName: string) {
    const linked = { ...newTopics[newTopicIdx], topic_id: topicId, name: topicName };
    setFollowed((prev) => [...prev, linked]);
    setNewTopics((prev) => prev.filter((_, i) => i !== newTopicIdx));
  }

  const unacknowledgedCount = notDiscussed.filter((t) => !t.disposition).length;
  const totalCount = followed.length + notDiscussed.length + newTopics.length;
  const canValidate = !validating && unacknowledgedCount === 0 && totalCount > 0;

  async function handleValidate() {
    setValidating(true);
    setError(null);
    try {
      const allTopics: TopicSavePayload[] = [
        ...followed.map((t) => ({ ...t, topic_id: t.topic_id ?? null, disposition: null })),
        ...notDiscussed.map((t) => ({ ...t, topic_id: t.topic_id ?? null, disposition: (t.disposition ?? null) as TopicDisposition })),
        ...newTopics.map((t) => ({ ...t, topic_id: null, disposition: null })),
      ];
      await topicsAPI.save(call.id, allTopics);
      await topicsAPI.validate(call.id);
      onValidated();
    } catch (err) {
      logger.error("Validate failed", { component: "ProjectTopicsStage", data: err });
      setError(err instanceof Error ? err.message : "Validation failed");
    } finally {
      setValidating(false);
    }
  }

  if (loading) return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <p style={{ fontSize: 13, color: "#5e6c84" }}>Matching topics with project history…</p>
    </div>
  );

  if (error && !result) return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 12 }}>
      <p style={{ fontSize: 13, color: "#ae2a19" }}>{error}</p>
      <button onClick={reAggregate} style={{ fontSize: 12, color: "#0052cc", textDecoration: "underline", border: "none", background: "none", cursor: "pointer" }}>
        Retry
      </button>
    </div>
  );

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

      {/* Header */}
      <div style={{ padding: "16px 20px 12px", borderBottom: "1px solid #dfe1e6", flexShrink: 0 }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", margin: "0 0 4px" }}>Project Topics</h2>
        <p style={{ fontSize: 12, color: "#5e6c84", margin: 0, lineHeight: 1.5 }}>
          Step 2 of 2 — Review how this call relates to the project&apos;s topic history.
          Link any missed matches using the &quot;Link →&quot; button.
        </p>
      </div>

      {/* Error banner */}
      {error && (
        <div style={{ margin: "0 20px", marginTop: 12, background: "#fff1f0", border: "1px solid #ffbdad",
          borderRadius: 6, padding: "10px 14px", fontSize: 12, color: "#ae2a19", flexShrink: 0 }}>
          {error}
        </div>
      )}

      {/* Scrollable buckets */}
      <div style={{ flex: 1, overflowY: "auto" }}>

        {followed.length > 0 && (
          <>
            <BucketHeader label="Followed Up" count={followed.length} color="#36b37e" />
            {followed.map((t, i) => (
              <TopicRow key={i} topic={t} bucket="followed_up" existingTopics={existingTopics}
                onChange={(u) => { const n = [...followed]; n[i] = u; setFollowed(n); }}
                onDelete={() => setFollowed((prev) => prev.filter((_, idx) => idx !== i))}
                onLink={() => {}}
                callIsLocked={call.is_locked} />
            ))}
          </>
        )}

        {notDiscussed.length > 0 && (
          <>
            <BucketHeader label="Not Discussed" count={notDiscussed.length} color="#97a0af" />
            {notDiscussed.map((t, i) => (
              <TopicRow key={i} topic={t} bucket="not_discussed" existingTopics={existingTopics}
                onChange={(u) => { const n = [...notDiscussed]; n[i] = u; setNotDiscussed(n); }}
                onDelete={() => setNotDiscussed((prev) => prev.filter((_, idx) => idx !== i))}
                onLink={() => {}}
                callIsLocked={call.is_locked} />
            ))}
          </>
        )}

        {newTopics.length > 0 && (
          <>
            <BucketHeader label="New Topics" count={newTopics.length} color="#0052cc" />
            {newTopics.map((t, i) => (
              <TopicRow key={i} topic={t} bucket="new_topics" existingTopics={existingTopics}
                onChange={(u) => { const n = [...newTopics]; n[i] = u; setNewTopics(n); }}
                onDelete={() => setNewTopics((prev) => prev.filter((_, idx) => idx !== i))}
                onLink={(topicId, topicName) => handleLink(i, topicId, topicName)}
                callIsLocked={call.is_locked} />
            ))}
          </>
        )}

        {totalCount === 0 && (
          <p style={{ fontSize: 12, color: "#97a0af", padding: "12px 20px" }}>No topics to review.</p>
        )}
      </div>

      {/* Action bar */}
      {!call.is_locked && (
        <div style={{ padding: "12px 20px", borderTop: "1px solid #dfe1e6", background: "white",
          display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
          <span style={{ fontSize: 11, color: "#97a0af" }}>
            {unacknowledgedCount > 0
              ? `${unacknowledgedCount} not-discussed topic${unacknowledgedCount > 1 ? "s" : ""} need a disposition`
              : ""}
          </span>
          <button
            onClick={handleValidate}
            disabled={!canValidate}
            style={{
              padding: "8px 22px", borderRadius: 6, border: "none", fontSize: 13, fontWeight: 600,
              background: canValidate ? "#36b37e" : "#f4f5f7",
              color: canValidate ? "white" : "#97a0af",
              cursor: canValidate ? "pointer" : "default",
            }}
          >
            {validating ? "Validating…" : "Validate & Continue →"}
          </button>
        </div>
      )}
    </div>
  );
}
