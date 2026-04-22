"use client";

import { useState } from "react";
import type { TopicData, TopicStatus, TopicOwner, TopicSentiment } from "@/types";

type Props = {
  onAdd: (topic: TopicData) => void;
};

export default function AddTopicForm({ onAdd }: Props) {
  const [name, setName]           = useState("");
  const [summary, setSummary]     = useState("");
  const [status, setStatus]       = useState<TopicStatus>("open");
  const [owner, setOwner]         = useState<TopicOwner>("Us");
  const [sentiment, setSentiment] = useState<TopicSentiment>("neutral");
  const [open, setOpen]           = useState(false);

  function handleAdd() {
    if (!name.trim()) return;
    onAdd({
      topic_id: null,
      name: name.trim(),
      summary: summary.trim(),
      follow_up_items: [],
      decisions: [],
      open_questions: [],
      status,
      owner,
      sentiment,
      is_parked: false,
      importance: "medium",
      rationale: "",
      calls_open: 0,
    });
    setName(""); setSummary(""); setStatus("open"); setOwner("Us"); setSentiment("neutral");
    setOpen(false);
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
        style={{ display: "block", width: "100%", textAlign: "center", fontSize: 11,
          color: "#0052cc", border: "1px dashed #b3c6e8", background: "white",
          padding: "6px 12px", borderRadius: 4, cursor: "pointer", margin: "8px 14px 10px" }}>
        + Add topic
      </button>
    );
  }

  return (
    <div style={{ padding: "12px 14px", borderTop: "1px solid #f4f5f7", background: "#f8f9ff" }}>
      <div style={{ marginBottom: 8 }}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Topic name *"
          style={{ width: "100%", fontSize: 12, fontWeight: 600, border: "1px solid #dfe1e6",
            borderRadius: 4, padding: "4px 8px", marginBottom: 6 }} />
        <textarea value={summary} onChange={(e) => setSummary(e.target.value)}
          placeholder="Summary (optional)" rows={2}
          style={{ width: "100%", fontSize: 11, color: "#5e6c84", border: "1px solid #dfe1e6",
            borderRadius: 4, padding: "4px 8px", resize: "vertical" }} />
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <select value={status} onChange={(e) => setStatus(e.target.value as TopicStatus)}
          style={{ fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "2px 6px" }}>
          <option value="open">Open</option>
          <option value="in_progress">In Progress</option>
          <option value="resolved">Resolved</option>
        </select>
        <select value={owner} onChange={(e) => setOwner(e.target.value as TopicOwner)}
          style={{ fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "2px 6px" }}>
          <option value="Us">Us</option>
          <option value="Client">Client</option>
          <option value="Both">Both</option>
        </select>
        <select value={sentiment} onChange={(e) => setSentiment(e.target.value as TopicSentiment)}
          style={{ fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "2px 6px" }}>
          <option value="neutral">Neutral</option>
          <option value="positive">Positive</option>
          <option value="concern">Concern</option>
        </select>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={handleAdd} disabled={!name.trim()}
          style={{ fontSize: 12, fontWeight: 600, background: "#0052cc", color: "white",
            border: "none", padding: "6px 14px", borderRadius: 4, cursor: "pointer",
            opacity: name.trim() ? 1 : 0.5 }}>
          Add
        </button>
        <button onClick={() => setOpen(false)}
          style={{ fontSize: 12, color: "#5e6c84", background: "none", border: "none", cursor: "pointer" }}>
          Cancel
        </button>
      </div>
    </div>
  );
}
