"use client";

import { useCallback, useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { TopicData, TopicStatus, TopicSentiment } from "@/types";

type Props = { projectId: string };

type StatusFilter = "all" | TopicStatus;

const BADGE: React.CSSProperties = {
  fontSize: 9, fontWeight: 700, textTransform: "uppercase",
  padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap",
};
const STATUS_STYLE: Record<TopicStatus, React.CSSProperties> = {
  open:        { background: "#fff4e6", color: "#974f0c" },
  in_progress: { background: "#e9f0ff", color: "#0052cc" },
  resolved:    { background: "#bbf7d0", color: "#15803d" },
};
const SENT_STYLE: Record<TopicSentiment, React.CSSProperties> = {
  concern:  { background: "#fff1f0", color: "#ae2a19" },
  neutral:  { background: "#f4f5f7", color: "#5e6c84" },
  positive: { background: "#e3fcef", color: "#006644" },
};
const STATUS_LABEL: Record<TopicStatus, string> = {
  open: "Open", in_progress: "In Progress", resolved: "Resolved",
};

export default function TopicsDashboard({ projectId }: Props) {
  const [topics, setTopics]     = useState<TopicData[]>([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);
  const [filter, setFilter]     = useState<StatusFilter>("all");
  const [staleFirst, setStaleFirst] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      logger.info("Loading topics dashboard", { component: "TopicsDashboard", data: { projectId } });
      const data = await topicsAPI.listForProject(projectId);
      setTopics(data);
    } catch (err) {
      logger.error("Failed to load topics", { component: "TopicsDashboard", data: err });
      setError("Failed to load topics.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <p style={{ fontSize: 13, color: "#5e6c84" }}>Loading…</p>
    </div>
  );

  if (error) return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <p style={{ fontSize: 13, color: "#ae2a19" }}>{error}</p>
    </div>
  );

  let filtered = filter === "all" ? topics : topics.filter((t) => t.status === filter);
  if (staleFirst) filtered = [...filtered].sort((a, b) => (b.calls_open ?? 0) - (a.calls_open ?? 0));

  return (
    <div style={{ padding: 16, flex: 1, overflowY: "auto" }}>
      {/* Filter bar */}
      <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "center" }}>
        {(["all", "open", "in_progress", "resolved"] as StatusFilter[]).map((s) => (
          <button key={s} onClick={() => setFilter(s)}
            style={{ fontSize: 11, fontWeight: 600, padding: "4px 10px", borderRadius: 4,
              border: "1px solid", cursor: "pointer",
              background: filter === s ? "#0052cc" : "white",
              color: filter === s ? "white" : "#5e6c84",
              borderColor: filter === s ? "#0052cc" : "#dfe1e6" }}>
            {s === "all" ? "All" : STATUS_LABEL[s as TopicStatus]}
          </button>
        ))}
        <button onClick={() => setStaleFirst((v) => !v)}
          style={{ fontSize: 11, fontWeight: 600, padding: "4px 10px", borderRadius: 4,
            border: "1px solid", cursor: "pointer", marginLeft: "auto",
            background: staleFirst ? "#fff4e6" : "white",
            color: staleFirst ? "#974f0c" : "#5e6c84",
            borderColor: staleFirst ? "#ff8b00" : "#dfe1e6" }}>
          {staleFirst ? "✓ Stale first" : "Stale first"}
        </button>
      </div>

      {filtered.length === 0 && (
        <p style={{ fontSize: 13, color: "#5e6c84", textAlign: "center", padding: 32 }}>
          {topics.length === 0 ? "No topics yet." : "No topics match this filter."}
        </p>
      )}

      {filtered.length > 0 && (
        <table style={{ width: "100%", borderCollapse: "collapse",
          background: "white", border: "1px solid #dfe1e6", borderRadius: 8, overflow: "hidden" }}>
          <thead>
            <tr style={{ background: "#f4f5f7" }}>
              {["Topic", "Status", "Owner", "Sentiment", "Follow-ups", "Decisions", ""].map((h) => (
                <th key={h} style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                  letterSpacing: "0.06em", color: "#97a0af", padding: "8px 12px",
                  textAlign: "left", borderBottom: "1px solid #dfe1e6" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((t, i) => {
              const isResolved = t.status === "resolved";
              const rowStyle: React.CSSProperties = {
                opacity: isResolved ? 0.6 : 1,
                borderBottom: i < filtered.length - 1 ? "1px solid #f4f5f7" : "none",
              };
              return (
                <tr key={t.topic_id ?? i} style={rowStyle}>
                  <td style={{ padding: "9px 12px", verticalAlign: "top" }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "#172b4d",
                      display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                      {t.name}
                      {(t.calls_open ?? 0) >= 2 && (
                        <span style={{ ...BADGE, background: "#fff4e6", color: "#974f0c" }}>
                          Open · {t.calls_open} calls
                        </span>
                      )}
                    </div>
                    {t.summary && (
                      <div style={{ fontSize: 10, color: "#5e6c84", lineHeight: 1.4, maxWidth: 280 }}>
                        {t.summary}
                      </div>
                    )}
                  </td>
                  <td style={{ padding: "9px 12px", verticalAlign: "top" }}>
                    <span style={{ ...BADGE, ...STATUS_STYLE[t.status] }}>
                      {STATUS_LABEL[t.status]}
                    </span>
                  </td>
                  <td style={{ padding: "9px 12px", fontSize: 11, color: "#172b4d",
                    verticalAlign: "top", whiteSpace: "nowrap" }}>
                    {t.owner}
                  </td>
                  <td style={{ padding: "9px 12px", verticalAlign: "top" }}>
                    <span style={{ ...BADGE, ...SENT_STYLE[t.sentiment ?? "neutral"] }}>
                      {t.sentiment}
                    </span>
                  </td>
                  <td style={{ padding: "9px 12px", verticalAlign: "top", maxWidth: 200 }}>
                    {(t.follow_up_items ?? []).length === 0 ? (
                      <span style={{ fontSize: 10, color: "#97a0af" }}>—</span>
                    ) : (
                      (t.follow_up_items ?? []).map((item, fi) => (
                        <div key={fi} style={{ fontSize: 10, color: "#5e6c84",
                          display: "flex", gap: 4, marginBottom: 2 }}>
                          <span style={{ color: "#97a0af" }}>→</span>{item}
                        </div>
                      ))
                    )}
                  </td>
                  <td style={{ padding: "9px 12px", verticalAlign: "top" }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                      {(t.decisions ?? []).length > 0 ? (
                        <span style={{ fontSize: 10, color: "#36b37e" }}>
                          ✓ {t.decisions!.length}
                        </span>
                      ) : (
                        <span style={{ fontSize: 10, color: "#97a0af" }}>—</span>
                      )}
                      {(t.open_questions?.length ?? 0) > 0 && (
                        <span style={{ fontSize: 10, color: "#0052cc" }}>
                          {t.open_questions!.length} open Q
                        </span>
                      )}
                      {t.is_parked && (
                        <span style={{ fontSize: 9, fontWeight: 700, padding: "1px 5px", background: "#f4f5f7",
                          color: "#5e6c84", borderRadius: 3, alignSelf: "flex-start" }}>
                          ⏸ PARKED
                        </span>
                      )}
                    </div>
                  </td>
                  <td style={{ padding: "9px 12px", verticalAlign: "top" }}>
                    <span style={{ fontSize: 9, color: "#97a0af", background: "#f4f5f7",
                      padding: "1px 5px", borderRadius: 3 }}>
                      {t.topic_id ? t.topic_id.slice(0, 6) : "new"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
