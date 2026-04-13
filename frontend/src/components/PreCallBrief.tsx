"use client";

import { useState } from "react";
import { topicsAPI } from "@/api/client";
import type { CallBrief, BriefItem } from "@/types";

type Props = { callId: string };

const SENT_BADGE: Record<string, React.CSSProperties> = {
  concern:  { background: "#fff1f0", color: "#ae2a19" },
  neutral:  { background: "#f4f5f7", color: "#5e6c84" },
  positive: { background: "#e3fcef", color: "#006644" },
};

function StaleBadge({ n }: { n: number }) {
  if (n < 2) return null;
  return (
    <span style={{ background: "#fff4e6", color: "#974f0c", fontSize: 9, fontWeight: 700,
      textTransform: "uppercase", padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap" }}>
      Open · {n} calls
    </span>
  );
}

function BriefRow({ item }: { item: BriefItem }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "5px 8px",
      borderRadius: 4, background: item.sentiment === "concern" ? "#fff1f0" : "#f4f5f7",
      marginBottom: 4, fontSize: 11, color: "#172b4d" }}>
      <span style={{ flex: 1 }}>{item.name}</span>
      <StaleBadge n={item.calls_open} />
      <span style={{ ...SENT_BADGE[item.sentiment], fontSize: 9, fontWeight: 700,
        textTransform: "uppercase", padding: "2px 6px", borderRadius: 3 }}>
        {item.sentiment}
      </span>
    </div>
  );
}

export default function PreCallBrief({ callId }: Props) {
  const [open, setOpen]     = useState(false);
  const [brief, setBrief]   = useState<CallBrief | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleOpen() {
    if (!open && !brief) {
      setLoading(true);
      try {
        const data = await topicsAPI.brief(callId);
        setBrief(data);
      } finally {
        setLoading(false);
      }
    }
    setOpen((v) => !v);
  }

  const isEmpty = brief &&
    brief.priority_topics.length === 0 &&
    brief.decisions_to_confirm.length === 0 &&
    brief.watch_list.length === 0;

  return (
    <div style={{ background: "white", border: "1px solid #dfe1e6",
      borderLeft: "3px solid #0052cc", borderRadius: 8, marginBottom: 16, overflow: "hidden" }}>
      <button
        onClick={handleOpen}
        style={{ width: "100%", display: "flex", alignItems: "center",
          justifyContent: "space-between", padding: "10px 14px",
          background: "none", border: "none", cursor: "pointer" }}
      >
        <span style={{ fontSize: 12, fontWeight: 700, color: "#172b4d", display: "flex",
          alignItems: "center", gap: 8 }}>
          📋 Pre-call Brief
          {brief && brief.priority_topics.length > 0 && (
            <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
              background: "#e9f0ff", color: "#0052cc", padding: "2px 6px", borderRadius: 3 }}>
              {brief.priority_topics.length} open · {brief.watch_list.length} concern
            </span>
          )}
        </span>
        <span style={{ fontSize: 11, color: "#97a0af" }}>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div style={{ borderTop: "1px solid #f4f5f7", padding: "12px 14px" }}>
          {loading && <p style={{ fontSize: 12, color: "#5e6c84" }}>Loading…</p>}
          {isEmpty && <p style={{ fontSize: 12, color: "#5e6c84" }}>No prior topics — this is your first call.</p>}
          {brief && !isEmpty && (
            <div style={{ display: "flex", gap: 20 }}>
              {brief.priority_topics.length > 0 && (
                <div style={{ flex: 1 }}>
                  <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase",
                    letterSpacing: "0.05em", color: "#5e6c84", marginBottom: 8 }}>
                    Priority Topics
                  </p>
                  {brief.priority_topics.map((t) => <BriefRow key={t.topic_id} item={t} />)}
                </div>
              )}
              {brief.decisions_to_confirm.length > 0 && (
                <div style={{ flex: 1 }}>
                  <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase",
                    letterSpacing: "0.05em", color: "#5e6c84", marginBottom: 8 }}>
                    Decisions to Confirm
                  </p>
                  {brief.decisions_to_confirm.map((d, i) => (
                    <div key={i} style={{ fontSize: 11, color: "#172b4d", padding: "4px 8px",
                      background: "#f4f5f7", borderRadius: 4, marginBottom: 4 }}>
                      <span style={{ color: "#97a0af" }}>{d.topic_name}: </span>{d.text}
                    </div>
                  ))}
                </div>
              )}
              {brief.watch_list.length > 0 && (
                <div style={{ flex: 1 }}>
                  <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase",
                    letterSpacing: "0.05em", color: "#5e6c84", marginBottom: 8 }}>
                    Watch List
                  </p>
                  {brief.watch_list.map((t) => <BriefRow key={t.topic_id} item={t} />)}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
