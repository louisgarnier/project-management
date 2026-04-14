"use client";

import { useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { TopicData } from "@/types";

type Props = {
  callId: string;
  onValidated: () => void;
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

function TopicRow({ topic, onChange }: { topic: TopicData; onChange: (t: TopicData) => void }) {
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

export default function ProjectUpdatesStage({ callId, onValidated }: Props) {
  const [topics, setTopics] = useState<TopicData[]>([]);
  const [loading, setLoading] = useState(false);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ran, setRan] = useState(false);

  async function handleRunMerge() {
    setLoading(true);
    setError(null);
    try {
      logger.info("Running merge preview", { component: "ProjectUpdatesStage" });
      const result = await topicsAPI.mergePreview(callId);
      setTopics(result);
      setRan(true);
      logger.info(`Merge preview: ${result.length} topics`, { component: "ProjectUpdatesStage" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Merge failed");
    } finally {
      setLoading(false);
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

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

      {/* Header */}
      <div style={{ padding: "16px 20px 12px", borderBottom: "1px solid #dfe1e6", flexShrink: 0 }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", margin: "0 0 4px" }}>
          Project Topic Updates
        </h2>
        <div style={{ fontSize: 12, color: "#5e6c84" }}>
          Step 2 of 2 — Review LLM-merged topic updates before saving to the project.
        </div>
      </div>

      {error && (
        <div style={{ margin: "0 20px", marginTop: 12, background: "#fff1f0", border: "1px solid #ffbdad",
          borderRadius: 6, padding: "10px 14px", fontSize: 12, color: "#ae2a19", flexShrink: 0 }}>
          {error}
        </div>
      )}

      {!ran ? (
        <div style={{ padding: 20, flexShrink: 0 }}>
          <p style={{ fontSize: 13, color: "#5e6c84", marginBottom: 16, marginTop: 0 }}>
            Run the merge to generate updated topic content based on your matching decisions.
            New topics will be created directly; matched topics will be merged with their existing summaries.
          </p>
          <button
            onClick={handleRunMerge}
            disabled={loading}
            style={{ padding: "10px 22px", borderRadius: 6, border: "none",
              background: loading ? "#f4f5f7" : "#0052cc",
              color: loading ? "#97a0af" : "white",
              cursor: loading ? "default" : "pointer",
              fontSize: 13, fontWeight: 600, fontFamily: "inherit" }}
          >
            {loading ? "Merging…" : "Run Merge"}
          </button>
        </div>
      ) : (
        <>
          {(() => {
            const discussed = topics.filter(t => !t.not_discussed);
            const notDiscussed = topics.filter(t => t.not_discussed);
            return (
              <>
                <div style={{ padding: "10px 20px 6px", fontSize: 11, fontWeight: 700, color: "#5e6c84",
                  textTransform: "uppercase", letterSpacing: ".05em", borderBottom: "1px solid #f4f5f7", flexShrink: 0 }}>
                  Topics ({discussed.length})
                </div>
                <div style={{ flex: 1, overflowY: "auto" }}>
                  {discussed.map((t) => {
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

                  {notDiscussed.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <div style={{ padding: "8px 20px 6px", borderTop: "1px solid #dfe1e6", borderBottom: "1px solid #dfe1e6",
                        background: "#f4f5f7" }}>
                        <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "#97a0af",
                          letterSpacing: ".05em" }}>
                          Not discussed in this call&nbsp;&nbsp;({notDiscussed.length} topic{notDiscussed.length !== 1 ? "s" : ""})
                        </div>
                        <div style={{ fontSize: 11, color: "#97a0af", marginTop: 2 }}>
                          These topics exist in the project but were not mentioned in this call. They carry over unchanged.
                        </div>
                      </div>
                      {notDiscussed.map((t, idx) => (
                        <div key={t.topic_id ?? t.name ?? idx}
                          style={{ opacity: 0.7, borderBottom: "1px solid #f0f1f3",
                            paddingLeft: 20, paddingRight: 20, paddingTop: 10, paddingBottom: 10,
                            borderLeft: "3px solid transparent", background: "white" }}>
                          <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                            <span style={{ color: "#97a0af", fontSize: 12 }}>•</span>
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
                            <p style={{ fontSize: 12, color: "#5e6c84", margin: "3px 0 0 18px", lineHeight: 1.5 }}>
                              {t.summary}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div style={{ padding: "12px 20px", borderTop: "1px solid #dfe1e6", background: "white",
                  display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
                  <button
                    onClick={handleRunMerge}
                    disabled={loading}
                    style={{ padding: "7px 16px", borderRadius: 6, border: "1px solid #dfe1e6",
                      background: "white", color: "#5e6c84", fontSize: 12, cursor: loading ? "default" : "pointer",
                      fontFamily: "inherit" }}
                  >
                    {loading ? "Re-running…" : "Re-run Merge"}
                  </button>
                  <button
                    onClick={handleValidate}
                    disabled={validating || discussed.length === 0}
                    style={{ padding: "8px 22px", borderRadius: 6, border: "none",
                      background: validating || discussed.length === 0 ? "#f4f5f7" : "#0052cc",
                      color: validating || discussed.length === 0 ? "#97a0af" : "white",
                      fontSize: 13, fontWeight: 600,
                      cursor: validating || discussed.length === 0 ? "default" : "pointer",
                      fontFamily: "inherit" }}
                  >
                    {validating ? "Saving…" : "Validate →"}
                  </button>
                </div>
              </>
            );
          })()}
        </>
      )}
    </div>
  );
}
