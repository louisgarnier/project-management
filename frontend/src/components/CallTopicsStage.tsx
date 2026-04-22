"use client";

import { useEffect, useState } from "react";
import { artifactTypesAPI, projectsAPI, topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call, TopicData, TopicStatus, TopicOwner, TopicSentiment, LLMProvider } from "@/types";
import TopicEvidenceDrawer from "./TopicEvidenceDrawer";

const LLM_LABELS: Record<LLMProvider, string> = {
  groq:       "Groq – Llama 3.3",
  deepseek:   "DeepSeek Chat",
  claude:     "Claude Haiku",
  openai:     "GPT-4o mini",
  openrouter: "OpenRouter",
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

const IMPORTANCE_COLOR: Record<"high" | "medium" | "low", string> = {
  high:   "#ae2a19",
  medium: "#ff991f",
  low:    "#97a0af",
};

function SectionBlock({
  label, count, bg, color, items, prefix, editing, onChange, renderItem,
}: {
  label: string;
  count: number;
  bg: string;
  color: string;
  items: string[];
  prefix: string;
  editing: boolean;
  onChange: (items: string[]) => void;
  renderItem?: (item: string) => React.ReactNode;
}) {
  const [newText, setNewText] = useState("");
  return (
    <div style={{ background: bg, borderRadius: 4, padding: "9px 11px", marginBottom: 6 }}>
      <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color, letterSpacing: ".05em", marginBottom: 5 }}>
        {label} ({count})
      </div>
      <div style={{ fontSize: 11.5, color: "#172b4d", lineHeight: 1.55 }}>
        {items.map((item, i) => (
          editing ? (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
              <span style={{ color: "#97a0af", fontSize: 11 }}>{prefix}</span>
              <input
                value={item}
                onChange={(e) => {
                  const next = [...items];
                  next[i] = e.target.value;
                  onChange(next);
                }}
                style={{ flex: 1, fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "3px 6px", fontFamily: "inherit" }}
              />
              <button
                type="button"
                onClick={() => onChange(items.filter((_, idx) => idx !== i))}
                style={{ background: "none", border: "none", cursor: "pointer", color: "#bfc5ce", fontSize: 11 }}
              >✕</button>
            </div>
          ) : (
            <div key={i}>
              {prefix}{renderItem ? renderItem(item) : item}
            </div>
          )
        ))}
        {editing && (
          <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
            <input
              value={newText}
              onChange={(e) => setNewText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && newText.trim()) {
                  onChange([...items, newText.trim()]);
                  setNewText("");
                }
              }}
              placeholder={`Add ${label.toLowerCase().replace(/s$/, "")}…`}
              style={{ flex: 1, fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "3px 6px", fontFamily: "inherit" }}
            />
            <button
              type="button"
              onClick={() => {
                if (newText.trim()) { onChange([...items, newText.trim()]); setNewText(""); }
              }}
              style={{ fontSize: 11, color: "#0052cc", background: "none", border: "1px solid #b3c6e8", borderRadius: 4, padding: "3px 10px", cursor: "pointer" }}
            >
              Add
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function TopicRow({
  topic,
  onChange,
  onDelete,
  onViewSource,
}: {
  topic: TopicData;
  onChange: (updated: TopicData) => void;
  onDelete: () => void;
  onViewSource?: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const parked = topic.is_parked;
  const dotColor = parked ? "#97a0af" : IMPORTANCE_COLOR[topic.importance] ?? "#ff991f";
  const borderColor = parked ? "#97a0af" : "#0052cc";
  const background = parked ? "#fafbfc" : "white";

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
          {editing ? (
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
            <strong style={{ fontSize: 13, color: "#172b4d" }}>{topic.name}</strong>
          )}
          {parked ? (
            <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", background: "#f4f5f7", color: "#5e6c84", borderRadius: 3 }}>
              ⏸ PARKED
            </span>
          ) : (
            <span style={{
              fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 3,
              ...(STATUS_BADGE[topic.status] ?? STATUS_BADGE.open),
            }}>
              {topic.status?.replace("_", " ")}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
          <span style={{ fontSize: 10, color: "#5e6c84" }}>
            {topic.sentiment?.toUpperCase()} · {topic.owner?.toUpperCase()}
          </span>
          <button
            type="button"
            onClick={() => setEditing((v) => !v)}
            title={editing ? "Done editing" : "Edit"}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: 13, color: editing ? "#0052cc" : "#97a0af" }}
          >{editing ? "✓" : "✎"}</button>
          <button
            type="button"
            onClick={onDelete}
            title="Remove"
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: 13, color: "#bfc5ce" }}
          >✕</button>
        </div>
      </div>

      {/* Summary */}
      {editing ? (
        <textarea
          value={topic.summary}
          onChange={(e) => onChange({ ...topic, summary: e.target.value })}
          placeholder="3–6 sentence summary…"
          rows={5}
          style={{
            width: "100%", margin: "8px 0 10px", fontSize: 12, color: "#172b4d",
            border: "1px solid #dfe1e6", borderRadius: 4, padding: "6px 8px",
            fontFamily: "inherit", resize: "vertical", boxSizing: "border-box",
          }}
        />
      ) : (
        topic.summary && (
          <p style={{ fontSize: 12, color: "#172b4d", margin: "6px 0 10px", lineHeight: 1.5 }}>
            {topic.summary}
          </p>
        )
      )}

      {/* Decisions */}
      {(topic.decisions?.length ?? 0) > 0 && (
        <SectionBlock
          label="Decisions"
          count={topic.decisions.length}
          bg="#f4f5f7" color="#5e6c84"
          items={topic.decisions}
          prefix="✓ "
          editing={editing}
          onChange={(items) => onChange({ ...topic, decisions: items })}
        />
      )}

      {/* Actions — hidden for parked topics */}
      {!parked && (topic.follow_up_items?.length ?? 0) > 0 && (
        <SectionBlock
          label="Actions"
          count={topic.follow_up_items.length}
          bg="#fff8e6" color="#974f0c"
          items={topic.follow_up_items}
          prefix="→ "
          renderItem={renderOwnerHighlight}
          editing={editing}
          onChange={(items) => onChange({ ...topic, follow_up_items: items })}
        />
      )}

      {/* Open questions */}
      {(topic.open_questions?.length ?? 0) > 0 && (
        <SectionBlock
          label="Open questions"
          count={topic.open_questions.length}
          bg="#eef5ff" color="#0052cc"
          items={topic.open_questions}
          prefix="? "
          editing={editing}
          onChange={(items) => onChange({ ...topic, open_questions: items })}
        />
      )}

      {/* Footer strip */}
      <div style={{ display: "flex", gap: 10, paddingTop: 8, marginTop: 6, borderTop: "1px dashed #dfe1e6", alignItems: "center", flexWrap: "wrap" }}>
        {onViewSource && (
          <button
            type="button"
            onClick={onViewSource}
            style={{
              background: "none", border: "none", cursor: "pointer",
              fontSize: 11, color: "#0052cc", padding: 0, fontFamily: "inherit", textDecoration: "underline",
            }}
          >📄 Source excerpt ↗</button>
        )}
        {parked && (
          <button
            type="button"
            onClick={() => onChange({ ...topic, is_parked: false })}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: 11, color: "#5e6c84", textDecoration: "underline" }}
          >Un-park</button>
        )}
        {!parked && editing && (
          <button
            type="button"
            onClick={() => onChange({ ...topic, is_parked: true })}
            style={{ background: "none", border: "none", cursor: "pointer", fontSize: 11, color: "#5e6c84", textDecoration: "underline" }}
          >⏸ Park</button>
        )}
        {editing && (
          <div style={{ display: "flex", gap: 6 }}>
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
        )}
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function CallTopicsStage({ call, onAggregateComplete, onAutoAdvanced, onPollCall }: Props) {
  const alreadyExtracted = call.extraction_status === "done" && !!(call.extraction_cache?.length);
  const [topics, setTopics] = useState<TopicData[]>(() => alreadyExtracted ? (call.extraction_cache ?? []) : []);
  const [extracting, setExtracting] = useState(false);
  const [aggregating, setAggregating] = useState(false);
  const [extracted, setExtracted] = useState(alreadyExtracted);
  const [error, setError] = useState<string | null>(null);
  const [rateLimited, setRateLimited] = useState(false);
  const [promptName, setPromptName] = useState<string | null>(null);
  const [effectiveLlm, setEffectiveLlm] = useState<string | null>(null);
  const [polling, setPolling] = useState(() => call.extraction_status === "processing");
  const [sourceDrawerTopic, setSourceDrawerTopic] = useState<TopicData | null>(null);

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
    <>
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
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <svg className="animate-spin" style={{ width: 16, height: 16, color: "#ff8b00" }} viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              <span style={{ fontSize: 13, color: "#5e6c84" }}>Generating…</span>
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
                  onViewSource={() => setSourceDrawerTopic(t)}
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
              {aggregating ? "Matching with project…" : "Save & Continue →"}
            </button>
          </div>
        </>
      )}
    </div>
    <TopicEvidenceDrawer
      open={!!sourceDrawerTopic}
      mode="call_topic"
      pendingTopic={sourceDrawerTopic}
      onClose={() => setSourceDrawerTopic(null)}
    />
    </>
  );
}
