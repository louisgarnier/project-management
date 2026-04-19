"use client";

import { useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call, TopicData } from "@/types";

type Props = {
  callId: string;
  call?: Call;
};

const STATUS_BADGE: Record<string, React.CSSProperties> = {
  open:        { background: "#e9f0ff", color: "#0052cc" },
  in_progress: { background: "#fff4e6", color: "#974f0c" },
  resolved:    { background: "#e3fcef", color: "#006644" },
};

const SENTIMENT_COLOR: Record<string, string> = {
  positive: "#216e4e", neutral: "#5e6c84", concern: "#ae2a19",
};

export default function CallTopicsHistoricalView({ callId, call }: Props) {
  const [topics, setTopics] = useState<TopicData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    topicsAPI.listForCall(callId)
      .then((data) => {
        if (data.length > 0) {
          setTopics(data);
        } else {
          // Fallback: use pending_topics or extraction_cache from the call object
          const fallback = call?.pending_topics ?? call?.extraction_cache ?? [];
          setTopics(fallback);
        }
        logger.info("[CallTopicsHistoricalView] Loaded", {
          component: "CallTopicsHistoricalView",
          data: { count: data.length },
        });
      })
      .catch((err) => {
        logger.error("[CallTopicsHistoricalView] Failed to load", { component: "CallTopicsHistoricalView", data: err });
        setError("Failed to load call topics");
      })
      .finally(() => setLoading(false));
  }, [callId]);

  if (loading) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <p style={{ fontSize: 13, color: "#5e6c84" }}>Loading…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <p style={{ fontSize: 13, color: "#ae2a19" }}>{error}</p>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

      {/* Header */}
      <div style={{ padding: "16px 20px 12px", borderBottom: "1px solid #dfe1e6", flexShrink: 0 }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", margin: "0 0 4px" }}>
          Call Topics
        </h2>
        <div style={{ fontSize: 12, color: "#5e6c84", marginBottom: 8 }}>
          {topics.length} topic{topics.length !== 1 ? "s" : ""} extracted from this call
        </div>
        <div style={{
          background: "#f4f5f7", border: "1px solid #dfe1e6", borderRadius: 6,
          padding: "8px 12px", fontSize: 12, color: "#5e6c84",
          display: "flex", alignItems: "center", gap: 6,
        }}>
          <span style={{ fontSize: 14 }}>🔒</span>
          <span>Read-only — call topics were confirmed</span>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: "auto" }}>
        {topics.length === 0 ? (
          <div style={{ padding: "32px 20px", textAlign: "center", color: "#97a0af", fontSize: 13 }}>
            No topics recorded for this call.
          </div>
        ) : (
          topics.map((t, i) => (
            <div key={(t as { topic_id?: string }).topic_id ?? i} style={{
              borderBottom: "1px solid #f0f1f3",
              paddingLeft: 20, paddingRight: 20, paddingTop: 10, paddingBottom: 10,
              borderLeft: "3px solid transparent", background: "white",
            }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 2 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: "#172b4d" }}>{t.name}</span>
                <span style={{
                  fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                  padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap", flexShrink: 0,
                  ...(STATUS_BADGE[t.status ?? "open"] ?? STATUS_BADGE.open),
                }}>
                  {(t.status ?? "open").replace("_", " ")}
                </span>
                <span style={{
                  fontSize: 10, fontWeight: 700, textTransform: "uppercase",
                  color: SENTIMENT_COLOR[t.sentiment ?? "neutral"] ?? "#5e6c84", marginLeft: "auto",
                }}>
                  {t.sentiment}
                </span>
              </div>
              {t.summary && (
                <p style={{ fontSize: 12, color: "#5e6c84", margin: "3px 0 0", lineHeight: 1.5 }}>{t.summary}</p>
              )}
              {(t.follow_up_items ?? []).map((item, j) => (
                <div key={j} style={{ fontSize: 11, color: "#5e6c84", paddingTop: 2 }}>→ {item}</div>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
