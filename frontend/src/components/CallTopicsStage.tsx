"use client";

import { useEffect, useState } from "react";
import { artifactTypesAPI, projectsAPI, topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call, TopicData, TopicStatus, TopicOwner, TopicSentiment, LLMProvider } from "@/types";

const LLM_LABELS: Record<LLMProvider, string> = {
  groq:     "Groq – Llama 3.3",
  deepseek: "DeepSeek Chat",
  claude:   "Claude Haiku",
  openai:   "GPT-4o mini",
};

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

type Props = {
  call: Call;
  onAggregateComplete: () => void;
  onAutoAdvanced: () => void;
  onPollCall?: () => Promise<void>;
};

// ── Topic row ──────────────────────────────────────────────────────────────────

function TopicRow({
  topic,
  onChange,
  onDelete,
}: {
  topic: TopicData;
  onChange: (updated: TopicData) => void;
  onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [newFollowUp, setNewFollowUp] = useState("");

  return (
    <div style={{
      borderBottom: "1px solid #f0f1f3",
      paddingLeft: expanded ? 17 : 20,
      paddingRight: 20,
      paddingTop: 10,
      paddingBottom: 10,
      borderLeft: expanded ? "3px solid #0052cc" : "3px solid transparent",
      background: expanded ? "#fafbfc" : "white",
      transition: "background .1s",
    }}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, flex: 1, minWidth: 0 }}>
          {expanded ? (
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
          <span style={{
            fontSize: 10, fontWeight: 700, textTransform: "uppercase",
            color: SENTIMENT_COLOR[topic.sentiment] ?? "#5e6c84",
          }}>
            {topic.sentiment}
          </span>
          <button
            onClick={() => setExpanded((v) => !v)}
            title="Edit"
            style={{
              background: "none", border: "none", cursor: "pointer", fontSize: 13, padding: "0 2px",
              color: expanded ? "#0052cc" : "#97a0af", lineHeight: 1,
            }}
          >
            ✎
          </button>
          <button
            onClick={onDelete}
            title="Remove"
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: 13, padding: "0 2px", color: "#bfc5ce", lineHeight: 1 }}
          >
            ✕
          </button>
        </div>
      </div>

      {/* Summary — always visible */}
      {!expanded && topic.summary && (
        <p style={{ fontSize: 12, color: "#5e6c84", margin: "3px 0 0", lineHeight: 1.5 }}>
          {topic.summary}
        </p>
      )}
      {!expanded && (topic.follow_up_items ?? []).map((item, i) => (
        <div key={i} style={{ fontSize: 11, color: "#5e6c84", paddingTop: 2 }}>→ {item}</div>
      ))}

      {/* Expanded edit controls */}
      {expanded && (
        <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 8 }}>
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

          {/* Summary textarea */}
          <textarea
            value={topic.summary}
            onChange={(e) => onChange({ ...topic, summary: e.target.value })}
            placeholder="Summary…"
            rows={2}
            style={{
              fontSize: 12, color: "#172b4d", border: "1px solid #dfe1e6", borderRadius: 4,
              padding: "6px 8px", resize: "vertical", fontFamily: "inherit",
              width: "100%", boxSizing: "border-box",
            }}
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
                <button
                  onClick={() => onChange({ ...topic, follow_up_items: (topic.follow_up_items ?? []).filter((_, idx) => idx !== i) })}
                  style={{ background: "none", border: "none", cursor: "pointer", color: "#bfc5ce", fontSize: 11 }}
                >✕</button>
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
                style={{ fontSize: 11, color: "#0052cc", background: "none", border: "1px solid #b3c6e8", borderRadius: 4, padding: "3px 10px", cursor: "pointer" }}
              >
                Add
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function CallTopicsStage({ call, onAggregateComplete, onAutoAdvanced, onPollCall }: Props) {
  const [topics, setTopics] = useState<TopicData[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [aggregating, setAggregating] = useState(false);
  const [extracted, setExtracted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rateLimited, setRateLimited] = useState(false);
  const [promptName, setPromptName] = useState<string | null>(null);
  const [effectiveLlm, setEffectiveLlm] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    Promise.all([
      artifactTypesAPI.list(call.project_id),
      projectsAPI.get(call.project_id),
    ]).then(([types, project]) => {
      const t = types.find((t) => t.category === "call_topics");
      if (t) {
        setPromptName(t.name);
        const llm = t.llm ?? project.default_llm;
        setEffectiveLlm(LLM_LABELS[llm] ?? llm);
      }
    }).catch(() => {});
  }, [call.project_id]);

  useEffect(() => {
    if (call.extraction_status === "done" && call.extraction_cache && call.extraction_cache.length > 0 && !extracted) {
      setTopics(call.extraction_cache);
      setExtracted(true);
    }
    if (call.extraction_status === "failed" && !extracted) {
      setError("Extraction failed in background. Please try again.");
    }
  }, [call.extraction_status, call.extraction_cache]);

  useEffect(() => {
    if (!polling) return;
    if (call.extraction_status === "done" || call.extraction_status === "failed") {
      setPolling(false);
      return;
    }
    const timer = setInterval(() => {
      onPollCall?.();
    }, 3000);
    return () => clearInterval(timer);
  }, [polling, call.extraction_status, onPollCall]);

  async function handleExtract() {
    setExtracting(true);
    setError(null);
    setRateLimited(false);
    try {
      logger.info("Extracting call topics (Step 1)", { component: "CallTopicsStage" });
      await topicsAPI.extractCall(call.id);
      setPolling(true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Extraction failed";
      logger.error("Step 1 extraction failed", { component: "CallTopicsStage", data: err });
      if (msg.includes("wait a moment")) setRateLimited(true);
      setError(msg);
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
        // Call 2+ advanced to project_matching
        onAggregateComplete();
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Aggregation failed";
      logger.error("Step 2 aggregation failed", { component: "CallTopicsStage", data: err });
      if (msg.includes("wait a moment")) setRateLimited(true);
      setError(msg);
    } finally {
      setAggregating(false);
    }
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

      {/* Header */}
      <div style={{ padding: "16px 20px 12px", borderBottom: "1px solid #dfe1e6", flexShrink: 0 }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", margin: "0 0 4px" }}>Call Topics</h2>
        <div style={{ fontSize: 12, color: "#5e6c84", lineHeight: 1.5, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span>Step 1 of 2 — Extract topics from this call only, without any previous context.</span>
          {promptName && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4, background: "#f4f5f7", borderRadius: 4, padding: "2px 8px", fontSize: 11, color: "#5e6c84" }}>
              Prompt: <strong style={{ color: "#172b4d" }}>{promptName}</strong>
              {effectiveLlm && <span>· {effectiveLlm}</span>}
            </span>
          )}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div style={{ margin: "0 20px", marginTop: 12, background: "#fff1f0", border: "1px solid #ffbdad",
          borderRadius: 6, padding: "10px 14px", fontSize: 12, color: "#ae2a19",
          display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexShrink: 0 }}>
          <span>{error}</span>
          {rateLimited && (
            <button onClick={extracted ? handleContinue : handleExtract}
              style={{ padding: "4px 12px", borderRadius: 4, border: "1px solid #ae2a19",
                background: "transparent", color: "#ae2a19", fontSize: 11, fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap" }}>
              Retry
            </button>
          )}
        </div>
      )}

      {/* Pre-extraction */}
      {!extracted ? (
        <div style={{ padding: 20 }}>
          {polling ? (
            <div style={{ fontSize: 13, color: "#5e6c84" }}>
              ⏳ Extracting in background… you can navigate away and come back.
            </div>
          ) : (
            <button
              onClick={handleExtract}
              disabled={extracting}
              style={{
                padding: "10px 22px", borderRadius: 6, border: "none",
                background: extracting ? "#f4f5f7" : "#0052cc",
                color: extracting ? "#97a0af" : "white",
                cursor: extracting ? "default" : "pointer",
                fontSize: 13, fontWeight: 600,
              }}
            >
              {extracting ? "Starting extraction…" : "Extract this call's topics"}
            </button>
          )}
        </div>
      ) : (
        <>
          {/* Topic count */}
          <div style={{ padding: "10px 20px 6px", fontSize: 11, fontWeight: 700, color: "#5e6c84",
            textTransform: "uppercase", letterSpacing: ".05em", borderBottom: "1px solid #f4f5f7", flexShrink: 0 }}>
            Topics ({topics.length})
          </div>

          {/* Scrollable list */}
          <div style={{ flex: 1, overflowY: "auto" }}>
            {topics.length === 0 ? (
              <p style={{ fontSize: 12, color: "#97a0af", padding: "12px 20px" }}>No topics extracted.</p>
            ) : (
              topics.map((t, i) => (
                <TopicRow
                  key={i}
                  topic={t}
                  onChange={(updated) => {
                    const next = [...topics];
                    next[i] = updated;
                    setTopics(next);
                  }}
                  onDelete={() => setTopics((prev) => prev.filter((_, idx) => idx !== i))}
                />
              ))
            )}
          </div>

          {/* Action bar */}
          <div style={{ padding: "12px 20px", borderTop: "1px solid #dfe1e6", background: "white",
            display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
            <button
              onClick={() => { setExtracted(false); setTopics([]); }}
              style={{ padding: "7px 16px", borderRadius: 6, border: "1px solid #dfe1e6",
                background: "white", color: "#5e6c84", fontSize: 12, cursor: "pointer" }}
            >
              Re-extract
            </button>
            <button
              onClick={handleContinue}
              disabled={aggregating || topics.length === 0}
              style={{
                padding: "8px 22px", borderRadius: 6, border: "none",
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
