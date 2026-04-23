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

const IMPORTANCE_COLOR: Record<"high" | "medium" | "low", string> = {
  high:   "#ae2a19",
  medium: "#ff991f",
  low:    "#97a0af",
};

function ReadOnlySectionBlock({
  label, count, bg, color, items, prefix, renderItem,
}: {
  label: string;
  count: number;
  bg: string;
  color: string;
  items: string[];
  prefix: string;
  renderItem?: (item: string) => React.ReactNode;
}) {
  return (
    <div style={{ background: bg, borderRadius: 4, padding: "9px 11px", marginBottom: 6 }}>
      <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color, letterSpacing: ".05em", marginBottom: 5 }}>
        {label} ({count})
      </div>
      <div style={{ fontSize: 11.5, color: "#172b4d", lineHeight: 1.55 }}>
        {items.map((item, i) => (
          <div key={i}>
            {prefix}{renderItem ? renderItem(item) : item}
          </div>
        ))}
      </div>
    </div>
  );
}

function ReadOnlyTopicRow({ topic }: { topic: TopicData }) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const parked = topic.is_parked;
  const dotColor = parked ? "#97a0af" : IMPORTANCE_COLOR[topic.importance ?? "medium"] ?? "#ff991f";
  const borderColor = parked ? "#97a0af" : "#0052cc";
  const background = parked ? "#fafbfc" : "white";
  const decisionsCount = topic.decisions?.length ?? 0;
  const actionsCount = parked ? 0 : (topic.follow_up_items?.length ?? 0);
  const questionsCount = topic.open_questions?.length ?? 0;
  const totalCount = decisionsCount + actionsCount + questionsCount;

  const renderOwnerHighlight = (text: string): React.ReactNode => {
    const m = text.match(/^([A-Z][a-z]+(?:\s[A-Z][a-z]+)?):\s*(.*)$/);
    if (!m) return text;
    return (<><strong>{m[1]}:</strong> {m[2]}</>);
  };

  return (
    <div style={{
      borderBottom: "1px solid #f0f1f3",
      padding: "14px 18px",
      borderLeft: `3px solid ${borderColor}`,
      background,
      opacity: parked ? 0.92 : 1,
    }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flex: 1, minWidth: 0 }}>
          <span
            title={topic.rationale || "No rationale provided"}
            style={{ width: 8, height: 8, borderRadius: "50%", background: dotColor, display: "inline-block", flexShrink: 0 }}
          />
          <strong style={{ fontSize: 13, color: "#172b4d" }}>{topic.name}</strong>
          {parked ? (
            <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", background: "#f4f5f7", color: "#5e6c84", borderRadius: 3 }}>
              ⏸ PARKED
            </span>
          ) : (
            <span style={{
              fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 3,
              ...(STATUS_BADGE[topic.status ?? "open"] ?? STATUS_BADGE.open),
            }}>
              {(topic.status ?? "open").replace("_", " ")}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
          <span style={{ fontSize: 10, color: "#5e6c84" }}>
            {topic.sentiment?.toUpperCase()} · {topic.owner?.toUpperCase()}
          </span>
          {totalCount > 0 && (
            <button
              type="button"
              onClick={() => setDetailsOpen((v) => !v)}
              title={detailsOpen ? "Collapse details" : "Expand details"}
              style={{ background: "none", border: "none", cursor: "pointer", fontSize: 13, color: "#5e6c84", padding: "0 2px" }}
            >{detailsOpen ? "▴" : "▾"}</button>
          )}
        </div>
      </div>

      {/* Summary */}
      {topic.summary && (
        <p style={{ fontSize: 12, color: "#172b4d", margin: "6px 0 10px", lineHeight: 1.5 }}>
          {topic.summary}
        </p>
      )}

      {/* Collapsed: compact counts row */}
      {!detailsOpen && totalCount > 0 && (
        <button
          type="button"
          onClick={() => setDetailsOpen(true)}
          style={{
            display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap",
            width: "100%", background: "none", border: "none", padding: "4px 0",
            fontSize: 11, cursor: "pointer", textAlign: "left", fontFamily: "inherit",
          }}
        >
          {decisionsCount > 0 && (
            <span style={{ color: "#5e6c84" }}>✓ {decisionsCount} decision{decisionsCount > 1 ? "s" : ""}</span>
          )}
          {actionsCount > 0 && (
            <span style={{ color: "#974f0c" }}>→ {actionsCount} action{actionsCount > 1 ? "s" : ""}</span>
          )}
          {questionsCount > 0 && (
            <span style={{ color: "#0052cc" }}>? {questionsCount} open question{questionsCount > 1 ? "s" : ""}</span>
          )}
          <span style={{ color: "#97a0af", marginLeft: "auto" }}>Show details ▾</span>
        </button>
      )}

      {/* Expanded details */}
      {detailsOpen && (
        <>
          {decisionsCount > 0 && (
            <ReadOnlySectionBlock
              label="Decisions" count={decisionsCount}
              bg="#f4f5f7" color="#5e6c84"
              items={topic.decisions} prefix="✓ "
            />
          )}
          {actionsCount > 0 && (
            <ReadOnlySectionBlock
              label="Actions" count={actionsCount}
              bg="#fff8e6" color="#974f0c"
              items={topic.follow_up_items} prefix="→ "
              renderItem={renderOwnerHighlight}
            />
          )}
          {questionsCount > 0 && (
            <ReadOnlySectionBlock
              label="Open questions" count={questionsCount}
              bg="#eef5ff" color="#0052cc"
              items={topic.open_questions} prefix="? "
            />
          )}
        </>
      )}
    </div>
  );
}

export default function CallTopicsHistoricalView({ callId, call }: Props) {
  const [topics, setTopics] = useState<TopicData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Preference order:
    //   1. pending_topics (Call 2+ — the raw extraction, matches what was shown
    //      on Call Topics stage originally; keeps parity with Project Matching
    //      view which also renders pending_topics)
    //   2. extraction_cache (pre-aggregate snapshot, if still present)
    //   3. listForCall / topic_updates (Call 1 auto-advance path, where pending
    //      is never persisted because matching is skipped)
    topicsAPI.getPending(callId)
      .then((pending) => {
        if (pending.length > 0) {
          setTopics(pending);
          logger.info("[CallTopicsHistoricalView] Loaded from pending_topics", {
            component: "CallTopicsHistoricalView",
            data: { count: pending.length },
          });
          return;
        }
        const cache = call?.extraction_cache ?? [];
        if (cache.length > 0) {
          setTopics(cache);
          logger.info("[CallTopicsHistoricalView] Loaded from extraction_cache", {
            component: "CallTopicsHistoricalView",
            data: { count: cache.length },
          });
          return;
        }
        return topicsAPI.listForCall(callId).then((data) => {
          setTopics(data);
          logger.info("[CallTopicsHistoricalView] Loaded from listForCall fallback", {
            component: "CallTopicsHistoricalView",
            data: { count: data.length },
          });
        });
      })
      .catch((err) => {
        logger.error("[CallTopicsHistoricalView] Failed to load", { component: "CallTopicsHistoricalView", data: err });
        setError("Failed to load call topics");
      })
      .finally(() => setLoading(false));
  }, [callId, call]);

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
            <ReadOnlyTopicRow key={(t as { topic_id?: string }).topic_id ?? i} topic={t} />
          ))
        )}
      </div>
    </div>
  );
}
