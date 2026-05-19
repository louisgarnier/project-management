"use client";

import { useEffect, useMemo, useState } from "react";
import { callsAPI, libraryAPI, topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type {
  Call,
  TopicData,
  TaskData,
  OpenQuestionData,
  DecisionData,
  LibraryEntry,
} from "@/types";
import KeyTermChips from "./KeyTermChips";
import EvidenceRefPopover from "./EvidenceRefPopover";

// ── Constants ──────────────────────────────────────────────────────────────────

const STATUS_BG = { open: "#e9f0ff", in_progress: "#fff4e6", resolved: "#e3fcef" } as const;
const STATUS_FG = { open: "#0052cc", in_progress: "#974f0c", resolved: "#006644" } as const;
const IMP_BG    = { high: "#ffebe5", medium: "#fffae6", low: "#f4f5f7" } as const;
const IMP_FG    = { high: "#bf2600", medium: "#974f0c", low: "#5e6c84" } as const;

// ── Props ──────────────────────────────────────────────────────────────────────

type Props = {
  call: Call;
  onAggregateComplete: () => void;
  onAutoAdvanced: () => void;
  onPollCall?: () => Promise<void>;
};

// ── Main component ─────────────────────────────────────────────────────────────

export default function CallTopicsStage({ call, onAggregateComplete, onAutoAdvanced, onPollCall }: Props) {
  // ── State ──
  const alreadyExtracted =
    call.extraction_status === "done" && !!(call.extraction_cache?.length);

  const [topics, setTopics] = useState<TopicData[]>(() =>
    alreadyExtracted ? (call.extraction_cache ?? []) : []
  );
  const [libraryPrompts, setLibraryPrompts] = useState<LibraryEntry[]>([]);
  const [selectedPromptId, setSelectedPromptId] = useState<string | null>(
    call.call_topics_prompt_id ?? null
  );
  const [loading, setLoading] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [aggregating, setAggregating] = useState(false);
  const [extracted, setExtracted] = useState(alreadyExtracted);
  const [error, setError] = useState<string | null>(null);
  const [rateLimited, setRateLimited] = useState(false);
  const [polling, setPolling] = useState(
    () => call.extraction_status === "processing"
  );
  const [menu, setMenu] = useState<{ ti: number; x: number; y: number } | null>(null);

  // ── Load library prompts ──
  useEffect(() => {
    libraryAPI
      .listByCategory("call_topics")
      .then(setLibraryPrompts)
      .catch((e: unknown) => {
        logger.error("[CallTopicsStage] library load failed", { data: e });
      });
  }, []);

  // ── Sync extraction_cache → topics when call prop updates ──
  useEffect(() => {
    // Don't auto-restore from a stale parent `call` prop while the user is
    // mid-re-extract. Otherwise clicking Re-extract immediately gets clobbered
    // by the previous (still-cached) extraction_status="done" + extraction_cache.
    if (extracting || polling) return;
    if (
      call.extraction_status === "done" &&
      call.extraction_cache &&
      call.extraction_cache.length > 0 &&
      !extracted
    ) {
      // Detect stale stripped cache (rollback rebuild written before the
      // EPIC-15 fix that widened the SELECT). If every topic has no tasks AND
      // no evidence AND no key_terms, the cache lost its EPIC-15 data —
      // bypass it and fetch fresh from topic_updates via listForCall.
      const cacheLooksStripped = call.extraction_cache.every(
        (t) =>
          (!t.tasks || t.tasks.length === 0) &&
          (!t.evidence || t.evidence.length === 0) &&
          (!t.key_terms || t.key_terms.length === 0),
      );
      if (cacheLooksStripped) {
        logger.info("[CallTopicsStage] stale stripped cache detected — falling back to listForCall");
        setExtracted(true);
        refresh();
      } else {
        setTopics(call.extraction_cache);
        setExtracted(true);
      }
    }
    if (call.extraction_status === "failed" && !extracted) {
      setError("Extraction failed in background. Please try again.");
    }
  }, [call.extraction_status, call.extraction_cache, extracted, extracting, polling]);

  // ── Polling loop ──
  useEffect(() => {
    if (!polling) return;
    if (
      call.extraction_status === "done" ||
      call.extraction_status === "failed"
    ) {
      setPolling(false);
      return;
    }
    const timer = setInterval(() => {
      onPollCall?.();
    }, 3000);
    return () => clearInterval(timer);
  }, [polling, call.extraction_status, onPollCall]);

  // ── Load topics from DB (after re-extract completes) ──
  const refresh = async () => {
    setLoading(true);
    try {
      const data = await topicsAPI.listForCall(call.id);
      setTopics(data);
    } catch (e: unknown) {
      logger.error("[CallTopicsStage] topics load failed", { data: e });
    } finally {
      setLoading(false);
    }
  };

  // ── Patch helpers ──
  const patchTopic = async (idx: number, partial: Partial<TopicData>) => {
    const topic = topics[idx];
    const id = topic.id ?? topic.topic_id;
    // Optimistic local update
    setTopics((prev) => prev.map((t, i) => (i === idx ? { ...t, ...partial } : t)));
    if (!id) return;
    try {
      await topicsAPI.patch(id, partial as Parameters<typeof topicsAPI.patch>[1]);
    } catch (e: unknown) {
      logger.error("[CallTopicsStage] patch topic failed", { data: e });
    }
  };

  const updateTasks = async (idx: number, newTasks: TaskData[]) => {
    const topic = topics[idx];
    const id = topic.id ?? topic.topic_id;
    setTopics((prev) =>
      prev.map((t, i) => (i === idx ? { ...t, tasks: newTasks } : t))
    );
    if (!id) return;
    try {
      await topicsAPI.patch(id, { tasks: newTasks });
    } catch (e: unknown) {
      logger.error("[CallTopicsStage] tasks patch failed", { data: e });
    }
  };

  const updateOpenQuestions = async (
    idx: number,
    newOQ: OpenQuestionData[],
  ) => {
    const topic = topics[idx];
    const id = topic.id ?? topic.topic_id;
    setTopics((prev) =>
      prev.map((t, i) => (i === idx ? { ...t, open_questions: newOQ } : t))
    );
    if (!id) return;
    try {
      await topicsAPI.patch(id, { open_questions: newOQ });
    } catch (e: unknown) {
      logger.error("[CallTopicsStage] open_questions patch failed", { data: e });
    }
  };

  const updateDecisions = async (
    idx: number,
    newDec: DecisionData[],
  ) => {
    const topic = topics[idx];
    const id = topic.id ?? topic.topic_id;
    setTopics((prev) =>
      prev.map((t, i) => (i === idx ? { ...t, decisions: newDec } : t))
    );
    if (!id) return;
    try {
      await topicsAPI.patch(id, { decisions: newDec });
    } catch (e: unknown) {
      logger.error("[CallTopicsStage] decisions patch failed", { data: e });
    }
  };

  const deleteTopic = async (idx: number) => {
    const topic = topics[idx];
    // Backend DELETE endpoint takes topics.id (parent table FK), not topic_updates.id.
    const topicTableId = topic.topic_id;
    if (!confirm(`Delete topic "${topic.name}"?`)) return;
    setTopics((prev) => prev.filter((_, i) => i !== idx));
    if (!topicTableId) return;
    try {
      await topicsAPI.deleteTopic(call.id, topicTableId);
    } catch (e: unknown) {
      logger.error("[CallTopicsStage] delete topic failed", { data: e });
    }
  };

  const onPromptChange = async (id: string | null) => {
    setSelectedPromptId(id);
    try {
      await callsAPI.patchPromptSelection(call.id, id);
    } catch (e: unknown) {
      logger.error("[CallTopicsStage] prompt selection failed", { data: e });
    }
  };

  // ── Extract ──
  const handleExtract = async () => {
    setExtracting(true);
    setError(null);
    setRateLimited(false);
    try {
      logger.info("[CallTopicsStage] extracting call topics", { data: { callId: call.id } });
      await topicsAPI.extractCall(call.id);
      setPolling(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Extraction failed";
      logger.error("[CallTopicsStage] extraction failed", { data: err });
      if (msg.includes("wait a moment")) setRateLimited(true);
      setError(msg);
    } finally {
      setExtracting(false);
    }
  };

  // ── Re-extract (reset + start fresh extraction) ──
  const handleReExtract = async () => {
    setExtracted(false);
    setTopics([]);
    setError(null);
    setRateLimited(false);
    setExtracting(true);
    // Flip polling on IMMEDIATELY so the "Generating…" UI shows during the
    // ~57s LLM round-trip — don't wait for the API POST to return first.
    setPolling(true);
    try {
      logger.info("[CallTopicsStage] re-extracting call topics", { data: { callId: call.id } });
      await topicsAPI.extractCall(call.id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Extraction failed";
      logger.error("[CallTopicsStage] re-extraction failed", { data: err });
      if (msg.includes("wait a moment")) setRateLimited(true);
      setError(msg);
      setPolling(false);  // unset on error so the user can retry
    } finally {
      setExtracting(false);
    }
  };

  // ── Aggregate / advance ──
  const handleContinue = async () => {
    setAggregating(true);
    setError(null);
    try {
      logger.info("[CallTopicsStage] aggregating topics (Step 2)", { data: { callId: call.id } });
      const result = await topicsAPI.aggregate(call.id, topics);
      if (result.auto_advanced) {
        logger.info("[CallTopicsStage] Call 1 auto-advanced to artifacts");
        onAutoAdvanced();
      } else {
        onAggregateComplete();
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Aggregation failed";
      logger.error("[CallTopicsStage] aggregation failed", { data: err });
      if (msg.includes("wait a moment")) setRateLimited(true);
      setError(msg);
    } finally {
      setAggregating(false);
    }
  };

  // ── Derived ──
  const taskCount = useMemo(
    () => topics.reduce((n, t) => n + (t.tasks?.length ?? 0), 0),
    [topics]
  );
  const oqCount = useMemo(
    () => topics.reduce((n, t) => n + (t.open_questions?.length ?? 0), 0),
    [topics]
  );
  const decisionCount = useMemo(
    () => topics.reduce((n, t) => n + (t.decisions?.length ?? 0), 0),
    [topics]
  );
  const callTitle = call.title ?? "Untitled";
  const callDate = (call.created_at ?? "").slice(0, 10);

  // ── Render ──
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" }}>

      {/* ── Header ── */}
      <div
        style={{
          padding: "14px 20px 12px",
          borderBottom: "1px solid #dfe1e6",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            fontSize: 10,
            color: "#5e6c84",
            textTransform: "uppercase",
            letterSpacing: ".06em",
            marginBottom: 4,
          }}
        >
          Call Topics · {callTitle} · {callDate}
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <h2 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", margin: 0 }}>
            {extracted
              ? `Extracted (${topics.length} topic${topics.length === 1 ? "" : "s"} · ${taskCount} task${taskCount === 1 ? "" : "s"} · ${oqCount} open question${oqCount === 1 ? "" : "s"} · ${decisionCount} decision${decisionCount === 1 ? "" : "s"})`
              : "Call Topics"}
          </h2>

          {extracted && (
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              {/* Prompt selector */}
              <label style={{ fontSize: 11, color: "#5e6c84" }}>Prompt:</label>
              <select
                value={selectedPromptId ?? ""}
                onChange={(e) => onPromptChange(e.target.value || null)}
                style={{
                  fontSize: 12,
                  padding: "4px 8px",
                  border: "1px solid #dfe1e6",
                  borderRadius: 4,
                  background: "white",
                  color: "#172b4d",
                  fontFamily: "inherit",
                }}
              >
                <option value="">(library default)</option>
                {libraryPrompts.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>

              <button
                onClick={handleReExtract}
                disabled={extracting || polling}
                style={{
                  ...btn,
                  opacity: extracting || polling ? 0.6 : 1,
                  cursor: extracting || polling ? "default" : "pointer",
                }}
              >
                {extracting || polling ? "Re-extracting…" : "Re-extract"}
              </button>

              <button
                onClick={handleContinue}
                disabled={aggregating || topics.length === 0}
                style={{
                  ...primaryBtn,
                  opacity: aggregating || topics.length === 0 ? 0.6 : 1,
                  cursor: aggregating || topics.length === 0 ? "default" : "pointer",
                }}
              >
                {aggregating ? "Matching with project…" : "Save & Continue →"}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── Error banner ── */}
      {error && (
        <div
          style={{
            margin: "0 20px",
            marginTop: 12,
            background: "#fff1f0",
            border: "1px solid #ffbdad",
            borderRadius: 6,
            padding: "10px 14px",
            fontSize: 12,
            color: "#ae2a19",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            flexShrink: 0,
          }}
        >
          <span>{error}</span>
          {rateLimited && (
            <button
              onClick={extracted ? handleContinue : handleExtract}
              style={{
                padding: "4px 12px",
                borderRadius: 4,
                border: "1px solid #ae2a19",
                background: "transparent",
                color: "#ae2a19",
                fontSize: 11,
                fontWeight: 600,
                cursor: "pointer",
                whiteSpace: "nowrap",
              }}
            >
              Retry
            </button>
          )}
        </div>
      )}

      {/* ── Pre-extraction state ── */}
      {!extracted ? (
        <div style={{ padding: 20 }}>
          {polling ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <svg
                className="animate-spin"
                style={{ width: 16, height: 16, color: "#ff8b00" }}
                viewBox="0 0 24 24"
                fill="none"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8v8H4z"
                />
              </svg>
              <span style={{ fontSize: 13, color: "#5e6c84" }}>Generating…</span>
            </div>
          ) : (
            <button
              onClick={handleExtract}
              disabled={extracting}
              style={{
                padding: "10px 22px",
                borderRadius: 6,
                border: "none",
                background: extracting ? "#f4f5f7" : "#0052cc",
                color: extracting ? "#97a0af" : "white",
                cursor: extracting ? "default" : "pointer",
                fontSize: 13,
                fontWeight: 600,
              }}
            >
              {extracting ? "Starting extraction…" : "Extract this call's topics"}
            </button>
          )}
        </div>
      ) : (
        /* ── Per-topic blocks (Tasks / Open questions / Decisions) ── */
        <div style={{ flex: 1, overflowY: "auto", padding: 20 }}>
          {loading ? (
            <div style={{ color: "#5e6c84", fontSize: 13 }}>Loading topics…</div>
          ) : topics.length === 0 ? (
            <div style={{ color: "#5e6c84", fontSize: 13 }}>
              No topics extracted. Click Re-extract to run the prompt.
            </div>
          ) : (
            <div
              style={{
                background: "white",
                border: "1px solid #dfe1e6",
                borderRadius: 6,
                overflow: "visible",
              }}
            >
              {topics.map((topic, ti) => (
                <TopicBlock
                  key={topic.id ?? topic.topic_id ?? `topic-${ti}`}
                  topic={topic}
                  isLast={ti === topics.length - 1}
                  onPatchTopic={(partial) => patchTopic(ti, partial)}
                  onUpdateTasks={(next) => updateTasks(ti, next)}
                  onUpdateOpenQuestions={(next) => updateOpenQuestions(ti, next)}
                  onUpdateDecisions={(next) => updateDecisions(ti, next)}
                  onContextMenuTopic={(e) => {
                    e.preventDefault();
                    setMenu({ ti, x: e.clientX, y: e.clientY });
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Right-click context menu ── */}
      {menu && (
        <>
          {/* Backdrop — closes menu on outside click */}
          <div
            onClick={() => setMenu(null)}
            style={{ position: "fixed", inset: 0, zIndex: 99 }}
          />
          <div
            style={{
              position: "fixed",
              top: menu.y,
              left: menu.x,
              zIndex: 100,
              background: "white",
              border: "1px solid #c1c7d0",
              borderRadius: 4,
              boxShadow: "0 4px 12px rgba(9,30,66,.15)",
              padding: 4,
              minWidth: 180,
            }}
          >
            <button
              type="button"
              onClick={() => {
                const topic = topics[menu.ti];
                updateTasks(menu.ti, [
                  ...(topic.tasks ?? []),
                  { task_id: crypto.randomUUID(), task: "", next_step: "", status: "open", owner: "" },
                ]);
                setMenu(null);
              }}
              style={menuItem}
            >
              + Add task
            </button>
            <button
              type="button"
              onClick={() => {
                const ti = menu.ti;
                setMenu(null);
                deleteTopic(ti);
              }}
              style={{ ...menuItem, color: "#bf2600" }}
            >
              🗑 Delete topic
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ── Style constants ────────────────────────────────────────────────────────────

const topicNameStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  border: "none",
  background: "transparent",
  padding: 2,
  color: "#172b4d",
  fontFamily: "inherit",
  flex: 1,
  minWidth: 0,
};
const statusSelect: React.CSSProperties = {
  fontSize: 9,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: ".04em",
  padding: "3px 18px 3px 7px",
  borderRadius: 3,
  border: "none",
  cursor: "pointer",
  appearance: "none",
  WebkitAppearance: "none",
};
const impSelect: React.CSSProperties = {
  fontSize: 9,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: ".04em",
  padding: "2px 16px 2px 5px",
  borderRadius: 3,
  border: "none",
  cursor: "pointer",
  appearance: "none",
  WebkitAppearance: "none",
  flexShrink: 0,
};
const iconBtn: React.CSSProperties = {
  background: "none",
  border: "none",
  cursor: "pointer",
  color: "#7a869a",
  padding: "2px 4px",
  borderRadius: 3,
  fontSize: 13,
};
const menuItem: React.CSSProperties = {
  display: "block",
  width: "100%",
  textAlign: "left",
  padding: "6px 10px",
  border: "none",
  background: "none",
  fontSize: 12,
  color: "#172b4d",
  cursor: "pointer",
  borderRadius: 3,
};
const btn: React.CSSProperties = {
  fontSize: 11,
  padding: "5px 10px",
  border: "1px solid #dfe1e6",
  background: "white",
  color: "#172b4d",
  borderRadius: 4,
  cursor: "pointer",
};
const primaryBtn: React.CSSProperties = {
  fontSize: 11,
  padding: "5px 12px",
  border: "none",
  background: "#0052cc",
  color: "white",
  borderRadius: 4,
  cursor: "pointer",
  fontWeight: 600,
};

// ── Per-topic block sub-components ─────────────────────────────────────────────

const OQ_ROW_TINT       = "#fff8e6";
const DECISION_ROW_TINT = "#f1f8ee";

const SECTION_LABEL_STYLE: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  textTransform: "uppercase",
  color: "#5e6c84",
  letterSpacing: ".05em",
  marginBottom: 6,
};
const EMPTY_SECTION_STYLE: React.CSSProperties = {
  fontSize: 11,
  color: "#97a0af",
  fontStyle: "italic",
  padding: "4px 8px",
};
const ADD_ROW_BUTTON_STYLE: React.CSSProperties = {
  marginTop: 6,
  fontSize: 11,
  color: "#0052cc",
  background: "none",
  border: "1px dashed #c1c7d0",
  padding: "4px 10px",
  borderRadius: 4,
  cursor: "pointer",
};
const MINI_TABLE_STYLE: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: 12.5,
};
const MINI_TH: React.CSSProperties = {
  padding: "6px 8px",
  textAlign: "left",
  fontWeight: 600,
};
const MINI_TD: React.CSSProperties = {
  padding: "8px",
  verticalAlign: "top",
};
const MINI_CELL_INPUT: React.CSSProperties = {
  width: "100%",
  border: "none",
  background: "transparent",
  fontSize: 12.5,
  padding: 0,
  color: "#172b4d",
  fontFamily: "inherit",
};

// Back-compat adapters: legacy DB rows may store decisions/open_questions as
// plain string[]. Coerce to structured shapes for editing.
function normalizeOpenQuestions(
  raw: (string | OpenQuestionData)[] | undefined,
): OpenQuestionData[] {
  return (raw ?? []).map((q) =>
    typeof q === "string"
      ? { id: "", text: q, owner: "", status: "open" as const }
      : q,
  );
}
function normalizeDecisions(
  raw: (string | DecisionData)[] | undefined,
): DecisionData[] {
  return (raw ?? []).map((d) =>
    typeof d === "string" ? { id: "", text: d } : d,
  );
}

// ── TopicBlock ────────────────────────────────────────────────────────────────

function TopicBlock({
  topic,
  isLast,
  onPatchTopic,
  onUpdateTasks,
  onUpdateOpenQuestions,
  onUpdateDecisions,
  onContextMenuTopic,
}: {
  topic: TopicData;
  isLast: boolean;
  onPatchTopic: (partial: Partial<TopicData>) => void;
  onUpdateTasks: (next: TaskData[]) => void;
  onUpdateOpenQuestions: (next: OpenQuestionData[]) => void;
  onUpdateDecisions: (next: DecisionData[]) => void;
  onContextMenuTopic: (e: React.MouseEvent) => void;
}) {
  const importance = topic.importance ?? "medium";
  const keyTerms = topic.key_terms ?? [];
  const evidence = topic.evidence ?? [];
  const tasks = topic.tasks ?? [];
  const openQuestions = normalizeOpenQuestions(topic.open_questions);
  const decisions = normalizeDecisions(topic.decisions);

  return (
    <div
      style={{
        borderBottom: isLast ? "none" : "2px solid #dfe1e6",
      }}
    >
      {/* Topic header row */}
      <div
        style={{
          padding: "14px 16px 8px 16px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 12,
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            onContextMenu={onContextMenuTopic}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              marginBottom: 6,
            }}
          >
            <input
              value={topic.name}
              onChange={(e) => onPatchTopic({ name: e.target.value })}
              style={topicNameStyle}
            />
            <select
              value={importance}
              onChange={(e) =>
                onPatchTopic({
                  importance: e.target.value as TopicData["importance"],
                })
              }
              style={{
                ...impSelect,
                background: IMP_BG[importance],
                color: IMP_FG[importance],
              }}
            >
              <option value="high">HIGH</option>
              <option value="medium">MED</option>
              <option value="low">LOW</option>
            </select>
            <EvidenceRefPopover evidence={evidence} />
          </div>

          <KeyTermChips
            terms={keyTerms}
            editable
            onChange={(next) => onPatchTopic({ key_terms: next })}
          />
        </div>
      </div>

      {/* Tasks section */}
      <TasksSection tasks={tasks} onUpdate={onUpdateTasks} />

      {/* Open questions section */}
      <OpenQuestionsSection
        openQuestions={openQuestions}
        onUpdate={onUpdateOpenQuestions}
      />

      {/* Decisions section */}
      <DecisionsSection
        decisions={decisions}
        onUpdate={onUpdateDecisions}
      />
    </div>
  );
}

// ── TasksSection ──────────────────────────────────────────────────────────────

function TasksSection({
  tasks,
  onUpdate,
}: {
  tasks: TaskData[];
  onUpdate: (next: TaskData[]) => void;
}) {
  const updateAt = (i: number, patch: Partial<TaskData>) =>
    onUpdate(tasks.map((t, idx) => (idx === i ? { ...t, ...patch } : t)));
  const deleteAt = (i: number) =>
    onUpdate(tasks.filter((_, idx) => idx !== i));
  const add = () =>
    onUpdate([
      ...tasks,
      {
        task_id: crypto.randomUUID(),
        task: "",
        next_step: "",
        status: "open",
        owner: "",
      },
    ]);

  return (
    <div style={{ padding: "6px 16px 8px 16px" }}>
      <div style={SECTION_LABEL_STYLE}>Tasks ({tasks.length})</div>
      {tasks.length === 0 ? (
        <div style={EMPTY_SECTION_STYLE}>— no tasks in this call</div>
      ) : (
        <table style={MINI_TABLE_STYLE}>
          <thead>
            <tr
              style={{
                color: "#5e6c84",
                fontSize: 10,
                textTransform: "uppercase",
                letterSpacing: ".04em",
                background: "#fafbfc",
              }}
            >
              <th style={{ ...MINI_TH, width: "32%" }}>Task</th>
              <th style={MINI_TH}>Next step</th>
              <th style={{ ...MINI_TH, width: 80 }}>Owner</th>
              <th style={{ ...MINI_TH, width: 108 }}>Status</th>
              <th style={{ ...MINI_TH, width: 32 }}></th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((task, i) => (
              <tr
                key={task.task_id || `new-${i}`}
                style={{ borderTop: "1px solid #f1f2f4" }}
              >
                <td style={MINI_TD}>
                  <input
                    key={task.task_id}
                    type="text"
                    defaultValue={task.task}
                    onBlur={(e) => {
                      if (e.target.value !== task.task)
                        updateAt(i, { task: e.target.value });
                    }}
                    style={MINI_CELL_INPUT}
                    placeholder="Describe task…"
                  />
                </td>
                <td style={{ ...MINI_TD, color: "#42526e" }}>
                  <input
                    key={task.task_id + "-ns"}
                    type="text"
                    defaultValue={task.next_step}
                    onBlur={(e) => {
                      if (e.target.value !== task.next_step)
                        updateAt(i, { next_step: e.target.value });
                    }}
                    style={MINI_CELL_INPUT}
                    placeholder="Next action…"
                  />
                </td>
                <td style={MINI_TD}>
                  <input
                    key={task.task_id + "-ow"}
                    type="text"
                    defaultValue={task.owner}
                    placeholder="— add"
                    onBlur={(e) => {
                      if (e.target.value !== task.owner)
                        updateAt(i, { owner: e.target.value });
                    }}
                    style={MINI_CELL_INPUT}
                  />
                </td>
                <td style={MINI_TD}>
                  <select
                    value={task.status}
                    onChange={(e) =>
                      updateAt(i, {
                        status: e.target.value as TaskData["status"],
                      })
                    }
                    style={{
                      ...statusSelect,
                      background: STATUS_BG[task.status] ?? STATUS_BG.open,
                      color: STATUS_FG[task.status] ?? STATUS_FG.open,
                    }}
                  >
                    <option value="open">OPEN</option>
                    <option value="in_progress">IN PROGRESS</option>
                    <option value="resolved">RESOLVED</option>
                  </select>
                </td>
                <td style={{ ...MINI_TD, textAlign: "center" }}>
                  <button
                    type="button"
                    onClick={() => deleteAt(i)}
                    style={iconBtn}
                    title="Delete task"
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <button
        type="button"
        onClick={add}
        style={ADD_ROW_BUTTON_STYLE}
        title="Add task"
      >
        + Add task
      </button>
    </div>
  );
}

// ── OpenQuestionsSection ──────────────────────────────────────────────────────

function OpenQuestionsSection({
  openQuestions,
  onUpdate,
}: {
  openQuestions: OpenQuestionData[];
  onUpdate: (next: OpenQuestionData[]) => void;
}) {
  const updateAt = (i: number, patch: Partial<OpenQuestionData>) =>
    onUpdate(
      openQuestions.map((q, idx) => (idx === i ? { ...q, ...patch } : q)),
    );
  const deleteAt = (i: number) =>
    onUpdate(openQuestions.filter((_, idx) => idx !== i));
  const add = () =>
    onUpdate([
      ...openQuestions,
      { id: crypto.randomUUID(), text: "", owner: "", status: "open" },
    ]);

  return (
    <div style={{ padding: "6px 16px 8px 16px" }}>
      <div style={SECTION_LABEL_STYLE}>
        Open questions ({openQuestions.length})
      </div>
      {openQuestions.length === 0 ? (
        <div style={EMPTY_SECTION_STYLE}>— no open questions in this call</div>
      ) : (
        <table style={MINI_TABLE_STYLE}>
          <tbody>
            {openQuestions.map((q, i) => (
              <tr
                key={q.id || `new-${i}`}
                style={{
                  borderTop: "1px solid #f1f2f4",
                  background: OQ_ROW_TINT,
                }}
              >
                <td style={MINI_TD}>
                  <input
                    key={q.id + "-txt"}
                    type="text"
                    defaultValue={q.text}
                    onBlur={(e) => {
                      if (e.target.value !== q.text)
                        updateAt(i, { text: e.target.value });
                    }}
                    style={MINI_CELL_INPUT}
                    placeholder="Open question…"
                  />
                </td>
                <td style={{ ...MINI_TD, width: 80 }}>
                  <input
                    key={q.id + "-ow"}
                    type="text"
                    defaultValue={q.owner}
                    placeholder="— add owner"
                    onBlur={(e) => {
                      if (e.target.value !== q.owner)
                        updateAt(i, { owner: e.target.value });
                    }}
                    style={MINI_CELL_INPUT}
                  />
                </td>
                <td style={{ ...MINI_TD, width: 108 }}>
                  <select
                    value={q.status}
                    onChange={(e) =>
                      updateAt(i, {
                        status: e.target.value as OpenQuestionData["status"],
                      })
                    }
                    style={{
                      ...statusSelect,
                      background: STATUS_BG[q.status] ?? STATUS_BG.open,
                      color: STATUS_FG[q.status] ?? STATUS_FG.open,
                    }}
                  >
                    <option value="open">OPEN</option>
                    <option value="in_progress">IN PROGRESS</option>
                    <option value="resolved">RESOLVED</option>
                  </select>
                </td>
                <td style={{ ...MINI_TD, width: 32, textAlign: "center" }}>
                  <button
                    type="button"
                    onClick={() => deleteAt(i)}
                    style={iconBtn}
                    title="Delete open question"
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <button
        type="button"
        onClick={add}
        style={ADD_ROW_BUTTON_STYLE}
        title="Add open question"
      >
        + Add open question
      </button>
    </div>
  );
}

// ── DecisionsSection ──────────────────────────────────────────────────────────

function DecisionsSection({
  decisions,
  onUpdate,
}: {
  decisions: DecisionData[];
  onUpdate: (next: DecisionData[]) => void;
}) {
  const updateAt = (i: number, patch: Partial<DecisionData>) =>
    onUpdate(decisions.map((d, idx) => (idx === i ? { ...d, ...patch } : d)));
  const deleteAt = (i: number) =>
    onUpdate(decisions.filter((_, idx) => idx !== i));
  const add = () => onUpdate([...decisions, { id: crypto.randomUUID(), text: "" }]);

  return (
    <div style={{ padding: "6px 16px 12px 16px" }}>
      <div style={SECTION_LABEL_STYLE}>Decisions ({decisions.length})</div>
      {decisions.length === 0 ? (
        <div style={EMPTY_SECTION_STYLE}>— no decisions in this call</div>
      ) : (
        <table style={MINI_TABLE_STYLE}>
          <tbody>
            {decisions.map((d, i) => (
              <tr
                key={d.id || `new-${i}`}
                style={{
                  borderTop: "1px solid #f1f2f4",
                  background: DECISION_ROW_TINT,
                }}
              >
                <td style={MINI_TD}>
                  <input
                    key={d.id + "-txt"}
                    type="text"
                    defaultValue={d.text}
                    onBlur={(e) => {
                      if (e.target.value !== d.text)
                        updateAt(i, { text: e.target.value });
                    }}
                    style={MINI_CELL_INPUT}
                    placeholder="Decision…"
                  />
                </td>
                <td style={{ ...MINI_TD, width: 32, textAlign: "center" }}>
                  <button
                    type="button"
                    onClick={() => deleteAt(i)}
                    style={iconBtn}
                    title="Delete decision"
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <button
        type="button"
        onClick={add}
        style={ADD_ROW_BUTTON_STYLE}
        title="Add decision"
      >
        + Add decision
      </button>
    </div>
  );
}
