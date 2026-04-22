"use client";

import { useState } from "react";
import type { TopicData, TopicStatus, TopicOwner, TopicSentiment, TopicDisposition } from "@/types";

type Props = {
  topic: TopicData;
  bucket: "followed_up" | "not_discussed" | "new";
  disposition: TopicDisposition;
  onUpdate: (updated: TopicData) => void;
  onDisposition: (d: TopicDisposition) => void;
  onRemove: () => void;
};

const STATUS_BADGE: Record<TopicStatus, React.CSSProperties> = {
  open:        { background: "#fff4e6", color: "#974f0c" },
  in_progress: { background: "#e9f0ff", color: "#0052cc" },
  resolved:    { background: "#bbf7d0", color: "#15803d" },
};
const STATUS_LABEL: Record<TopicStatus, string> = {
  open: "Open", in_progress: "In Progress", resolved: "Resolved",
};
const SENT_BADGE: Record<TopicSentiment, React.CSSProperties> = {
  concern:  { background: "#fff1f0", color: "#ae2a19" },
  neutral:  { background: "#f4f5f7", color: "#5e6c84" },
  positive: { background: "#e3fcef", color: "#006644" },
};
const BADGE_BASE: React.CSSProperties = {
  fontSize: 9, fontWeight: 700, textTransform: "uppercase",
  padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap",
};

export default function TopicEditor({ topic, bucket, disposition, onUpdate, onDisposition, onRemove }: Props) {
  const [editing, setEditing]     = useState(false);
  const [newDecision, setNewDecision] = useState("");
  const [newOpenQuestion, setNewOpenQuestion] = useState("");

  function set<K extends keyof TopicData>(key: K, val: TopicData[K]) {
    onUpdate({ ...topic, [key]: val });
  }

  function addDecision() {
    const trimmed = newDecision.trim();
    if (!trimmed) return;
    set("decisions", [...(topic.decisions ?? []), trimmed]);
    setNewDecision("");
  }

  function addFollowUp() {
    set("follow_up_items", [...(topic.follow_up_items ?? []), ""]);
  }

  function updateFollowUp(i: number, val: string) {
    const items = [...(topic.follow_up_items ?? [])];
    items[i] = val;
    set("follow_up_items", items);
  }

  function removeFollowUp(i: number) {
    set("follow_up_items", (topic.follow_up_items ?? []).filter((_, idx) => idx !== i));
  }

  function addOpenQuestion() {
    const trimmed = newOpenQuestion.trim();
    if (!trimmed) return;
    set("open_questions", [...(topic.open_questions ?? []), trimmed]);
    setNewOpenQuestion("");
  }

  function updateOpenQuestion(i: number, val: string) {
    const items = [...(topic.open_questions ?? [])];
    items[i] = val;
    set("open_questions", items);
  }

  function removeOpenQuestion(i: number) {
    set("open_questions", (topic.open_questions ?? []).filter((_, idx) => idx !== i));
  }

  const isNotDiscussed = bucket === "not_discussed";

  return (
    <div style={{ padding: "10px 14px", borderBottom: "1px solid #f4f5f7" }}>
      {/* Not-discussed amber banner */}
      {isNotDiscussed && (
        <div style={{ background: "#fff4e6", border: "1px solid #ffe0a0", borderRadius: 4,
          padding: "6px 10px", marginBottom: 8, fontSize: 10, color: "#974f0c" }}>
          ⚠ Not discussed this call — set a disposition before validating
        </div>
      )}

      {/* Topic header */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <div style={{ flex: 1 }}>
          {editing ? (
            <input
              value={topic.name}
              onChange={(e) => set("name", e.target.value)}
              style={{ fontSize: 12, fontWeight: 600, color: "#172b4d", border: "1px solid #dfe1e6",
                borderRadius: 4, padding: "2px 6px", width: "100%", marginBottom: 4 }}
            />
          ) : (
            <div style={{ fontSize: 12, fontWeight: 600, color: "#172b4d", marginBottom: 3 }}>
              {topic.name}
              {(topic.calls_open ?? 0) >= 2 && (
                <span style={{ ...BADGE_BASE, background: "#fff4e6", color: "#974f0c", marginLeft: 8 }}>
                  Open · {topic.calls_open} calls
                </span>
              )}
            </div>
          )}

          {/* Summary */}
          {editing ? (
            <textarea
              value={topic.summary}
              onChange={(e) => set("summary", e.target.value)}
              rows={2}
              style={{ fontSize: 10, color: "#5e6c84", border: "1px solid #dfe1e6", borderRadius: 4,
                padding: "4px 6px", width: "100%", resize: "vertical", marginBottom: 6 }}
            />
          ) : (
            <div style={{ fontSize: 10, color: "#5e6c84", lineHeight: 1.4, marginBottom: 6 }}>
              {topic.summary}
            </div>
          )}

          {/* Badges row */}
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginBottom: 6 }}>
            {editing ? (
              <>
                <select value={topic.status} onChange={(e) => set("status", e.target.value as TopicStatus)}
                  style={{ fontSize: 10, border: "1px solid #dfe1e6", borderRadius: 4, padding: "1px 4px" }}>
                  <option value="open">Open</option>
                  <option value="in_progress">In Progress</option>
                  <option value="resolved">Resolved</option>
                </select>
                <select value={topic.owner} onChange={(e) => set("owner", e.target.value as TopicOwner)}
                  style={{ fontSize: 10, border: "1px solid #dfe1e6", borderRadius: 4, padding: "1px 4px" }}>
                  <option value="Us">Us</option>
                  <option value="Client">Client</option>
                  <option value="Both">Both</option>
                </select>
                <select value={topic.sentiment} onChange={(e) => set("sentiment", e.target.value as TopicSentiment)}
                  style={{ fontSize: 10, border: "1px solid #dfe1e6", borderRadius: 4, padding: "1px 4px" }}>
                  <option value="positive">Positive</option>
                  <option value="neutral">Neutral</option>
                  <option value="concern">Concern</option>
                </select>
                <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#5e6c84" }}>
                  <input
                    type="checkbox"
                    checked={topic.is_parked ?? false}
                    onChange={(e) => set("is_parked", e.target.checked)}
                  />
                  Parked
                </label>
              </>
            ) : (
              <>
                <span style={{ ...BADGE_BASE, ...STATUS_BADGE[topic.status] }}>{STATUS_LABEL[topic.status]}</span>
                <span style={{ fontSize: 9, fontWeight: 600, background: "#f4f5f7", color: "#5e6c84",
                  padding: "2px 6px", borderRadius: 3 }}>{topic.owner}</span>
                <span style={{ ...BADGE_BASE, ...SENT_BADGE[topic.sentiment] }}>{topic.sentiment}</span>
                {topic.is_parked && (
                  <span style={{ ...BADGE_BASE, background: "#f4f5f7", color: "#5e6c84" }}>⏸ PARKED</span>
                )}
              </>
            )}
          </div>

          {/* Follow-ups */}
          {(editing || (topic.follow_up_items ?? []).length > 0) && (
            <div style={{ marginBottom: 6 }}>
              <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", color: "#97a0af",
                marginBottom: 4, letterSpacing: "0.05em" }}>Follow-ups</div>
              {(topic.follow_up_items ?? []).map((item, i) => (
                <div key={i} style={{ display: "flex", gap: 4, alignItems: "center", marginBottom: 2 }}>
                  <span style={{ color: "#97a0af", fontSize: 10 }}>→</span>
                  {editing ? (
                    <>
                      <input value={item} onChange={(e) => updateFollowUp(i, e.target.value)}
                        style={{ flex: 1, fontSize: 10, border: "1px solid #dfe1e6", borderRadius: 4,
                          padding: "1px 6px" }} />
                      <button onClick={() => removeFollowUp(i)}
                        style={{ fontSize: 10, color: "#97a0af", background: "none", border: "none",
                          cursor: "pointer" }}>✕</button>
                    </>
                  ) : (
                    <span style={{ fontSize: 10, color: "#5e6c84" }}>{item}</span>
                  )}
                </div>
              ))}
              {editing && (
                <button onClick={addFollowUp}
                  style={{ fontSize: 10, color: "#0052cc", background: "none", border: "none",
                    cursor: "pointer", marginTop: 2 }}>
                  + Add follow-up
                </button>
              )}
            </div>
          )}

          {/* Open Questions */}
          {(editing || (topic.open_questions ?? []).length > 0) && (
            <div style={{ marginBottom: 6 }}>
              <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", color: "#0052cc",
                marginBottom: 4, letterSpacing: "0.05em" }}>Open questions</div>
              {(topic.open_questions ?? []).map((item, i) => (
                <div key={i} style={{ display: "flex", gap: 4, alignItems: "center", marginBottom: 2,
                  background: "#eef5ff", borderRadius: 3, padding: "2px 6px" }}>
                  <span style={{ color: "#0052cc", fontSize: 10 }}>?</span>
                  {editing ? (
                    <>
                      <input value={item} onChange={(e) => updateOpenQuestion(i, e.target.value)}
                        style={{ flex: 1, fontSize: 10, border: "1px solid #b3c6e8", borderRadius: 4,
                          padding: "1px 6px", background: "transparent" }} />
                      <button onClick={() => removeOpenQuestion(i)}
                        style={{ fontSize: 10, color: "#0052cc", background: "none", border: "none",
                          cursor: "pointer" }}>✕</button>
                    </>
                  ) : (
                    <span style={{ fontSize: 10, color: "#0052cc" }}>{item}</span>
                  )}
                </div>
              ))}
              {editing && (
                <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
                  <input value={newOpenQuestion} onChange={(e) => setNewOpenQuestion(e.target.value)}
                    placeholder="Add open question…"
                    onKeyDown={(e) => e.key === "Enter" && addOpenQuestion()}
                    style={{ flex: 1, fontSize: 10, border: "1px solid #b3c6e8", borderRadius: 4,
                      padding: "2px 6px" }} />
                  <button onClick={addOpenQuestion}
                    style={{ fontSize: 10, color: "#0052cc", background: "none", border: "1px solid #b3c6e8",
                      borderRadius: 4, padding: "2px 8px", cursor: "pointer" }}>
                    Add
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Decisions (append-only) */}
          {((topic.decisions ?? []).length > 0 || editing) && (
            <div style={{ marginBottom: 6 }}>
              <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", color: "#97a0af",
                marginBottom: 4, letterSpacing: "0.05em" }}>Decisions</div>
              {(topic.decisions ?? []).map((d, i) => (
                <div key={i} style={{ fontSize: 10, color: "#36b37e", marginBottom: 2 }}>✓ {d}</div>
              ))}
              {editing && (
                <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
                  <input value={newDecision} onChange={(e) => setNewDecision(e.target.value)}
                    placeholder="Add decision…"
                    onKeyDown={(e) => e.key === "Enter" && addDecision()}
                    style={{ flex: 1, fontSize: 10, border: "1px solid #dfe1e6", borderRadius: 4,
                      padding: "2px 6px" }} />
                  <button onClick={addDecision}
                    style={{ fontSize: 10, color: "#0052cc", background: "none", border: "1px solid #b3c6e8",
                      borderRadius: 4, padding: "2px 8px", cursor: "pointer" }}>
                    Add
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Not-discussed disposition */}
          {isNotDiscussed && (
            <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
              {(["keep_as_is", "archive"] as TopicDisposition[]).map((d) => (
                <button key={d as string} onClick={() => onDisposition(disposition === d ? null : d)}
                  style={{ fontSize: 10, fontWeight: 600, border: "1px solid #dfe1e6",
                    background: disposition === d ? "#e9f0ff" : "white",
                    color: disposition === d ? "#0052cc" : "#172b4d",
                    borderColor: disposition === d ? "#0052cc" : "#dfe1e6",
                    padding: "3px 10px", borderRadius: 4, cursor: "pointer" }}>
                  {d === "keep_as_is" ? "Keep as-is" : "Archive"}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Edit / Remove icons */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4, paddingTop: 2 }}>
          <button onClick={() => setEditing((v) => !v)}
            style={{ fontSize: 11, color: editing ? "#0052cc" : "#97a0af", background: "none",
              border: "none", cursor: "pointer" }} title={editing ? "Done" : "Edit"}>
            {editing ? "✓" : "✎"}
          </button>
          <button onClick={onRemove}
            style={{ fontSize: 11, color: "#97a0af", background: "none", border: "none",
              cursor: "pointer" }} title="Remove">
            ✕
          </button>
        </div>
      </div>
    </div>
  );
}
