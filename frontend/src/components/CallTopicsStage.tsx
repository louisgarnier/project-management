"use client";

import { useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call, TopicData, AggregateResult, TopicStatus, TopicOwner, TopicSentiment } from "@/types";

type Props = {
  call: Call;
  onAggregateComplete: (result: AggregateResult) => void;
  onAutoAdvanced: () => void;
};

const FIELD_STYLE: React.CSSProperties = {
  width: "100%", fontSize: 11, padding: "4px 6px", borderRadius: 4,
  border: "1px solid #dfe1e6", fontFamily: "inherit",
};

function TopicCard({
  topic,
  onChange,
}: {
  topic: TopicData;
  onChange: (updated: TopicData) => void;
}) {
  return (
    <div style={{
      background: "white", border: "1px solid #dfe1e6", borderRadius: 8,
      padding: 12, display: "flex", flexDirection: "column", gap: 8,
    }}>
      <input
        value={topic.name}
        onChange={(e) => onChange({ ...topic, name: e.target.value })}
        placeholder="Topic name"
        style={{ ...FIELD_STYLE, fontWeight: 600, fontSize: 13 }}
      />
      <textarea
        value={topic.summary}
        onChange={(e) => onChange({ ...topic, summary: e.target.value })}
        placeholder="Summary"
        rows={2}
        style={{ ...FIELD_STYLE, resize: "vertical" }}
      />
      <div style={{ display: "flex", gap: 8 }}>
        <select
          value={topic.status}
          onChange={(e) => onChange({ ...topic, status: e.target.value as TopicStatus })}
          style={{ ...FIELD_STYLE, flex: 1 }}
        >
          <option value="open">Open</option>
          <option value="in_progress">In Progress</option>
          <option value="resolved">Resolved</option>
        </select>
        <select
          value={topic.owner}
          onChange={(e) => onChange({ ...topic, owner: e.target.value as TopicOwner })}
          style={{ ...FIELD_STYLE, flex: 1 }}
        >
          <option value="Us">Us</option>
          <option value="Client">Client</option>
          <option value="Both">Both</option>
        </select>
        <select
          value={topic.sentiment}
          onChange={(e) => onChange({ ...topic, sentiment: e.target.value as TopicSentiment })}
          style={{ ...FIELD_STYLE, flex: 1 }}
        >
          <option value="positive">Positive</option>
          <option value="neutral">Neutral</option>
          <option value="concern">Concern</option>
        </select>
      </div>
    </div>
  );
}

export default function CallTopicsStage({ call, onAggregateComplete, onAutoAdvanced }: Props) {
  const [topics, setTopics] = useState<TopicData[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [aggregating, setAggregating] = useState(false);
  const [extracted, setExtracted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExtract() {
    setExtracting(true);
    setError(null);
    try {
      logger.info("Extracting call topics (Step 1)", { component: "CallTopicsStage" });
      const result = await topicsAPI.extractCall(call.id);
      setTopics(result);
      setExtracted(true);
      logger.info(`Extracted ${result.length} topics`, { component: "CallTopicsStage" });
    } catch (err) {
      logger.error("Step 1 extraction failed", { component: "CallTopicsStage", data: err });
      setError(err instanceof Error ? err.message : "Extraction failed");
    } finally {
      setExtracting(false);
    }
  }

  async function handleContinue() {
    setAggregating(true);
    setError(null);
    try {
      logger.info("Aggregating topics (Step 2)", { component: "CallTopicsStage" });
      const result = await topicsAPI.aggregate(call.id, topics);
      if (result.auto_advanced) {
        logger.info("Call 1 auto-advanced to artifacts", { component: "CallTopicsStage" });
        onAutoAdvanced();
      } else {
        onAggregateComplete(result);
      }
    } catch (err) {
      logger.error("Step 2 aggregation failed", { component: "CallTopicsStage", data: err });
      setError(err instanceof Error ? err.message : "Aggregation failed");
    } finally {
      setAggregating(false);
    }
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
      <div>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", marginBottom: 4 }}>
          Call Topics
        </h2>
        <p style={{ fontSize: 12, color: "#5e6c84", lineHeight: 1.5 }}>
          Step 1 of 2 — Extract topics from this call only, without any previous context.
          Review and edit before continuing to match against project topics.
        </p>
      </div>

      {error && (
        <div style={{ background: "#fff1f0", border: "1px solid #ffbdad",
          borderRadius: 6, padding: "10px 14px", fontSize: 12, color: "#ae2a19" }}>
          {error}
        </div>
      )}

      {!extracted ? (
        <button
          onClick={handleExtract}
          disabled={extracting}
          style={{
            alignSelf: "flex-start", padding: "10px 20px", borderRadius: 6,
            background: extracting ? "#f4f5f7" : "#0052cc", color: extracting ? "#97a0af" : "white",
            border: "none", cursor: extracting ? "default" : "pointer",
            fontSize: 13, fontWeight: 600,
          }}
        >
          {extracting ? "Extracting…" : "Extract this call's topics"}
        </button>
      ) : (
        <>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {topics.map((t, i) => (
              <TopicCard
                key={i}
                topic={t}
                onChange={(updated) => {
                  const next = [...topics];
                  next[i] = updated;
                  setTopics(next);
                }}
              />
            ))}
          </div>
          {topics.length === 0 && (
            <p style={{ fontSize: 12, color: "#97a0af" }}>No topics extracted. Try again or add topics manually.</p>
          )}
          <div style={{ display: "flex", gap: 10, paddingTop: 4 }}>
            <button
              onClick={() => { setExtracted(false); setTopics([]); }}
              style={{ padding: "8px 16px", borderRadius: 6, border: "1px solid #dfe1e6",
                background: "white", color: "#5e6c84", fontSize: 12, cursor: "pointer" }}
            >
              Re-extract
            </button>
            <button
              onClick={handleContinue}
              disabled={aggregating || topics.length === 0}
              style={{
                padding: "8px 20px", borderRadius: 6, border: "none",
                background: aggregating || topics.length === 0 ? "#f4f5f7" : "#0052cc",
                color: aggregating || topics.length === 0 ? "#97a0af" : "white",
                fontSize: 13, fontWeight: 600,
                cursor: aggregating || topics.length === 0 ? "default" : "pointer",
              }}
            >
              {aggregating ? "Matching with project…" : "Continue →"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
