"use client";

import { useEffect, useMemo, useState } from "react";
import { callsAPI, libraryAPI, topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call, TopicData, TaskData, LibraryEntry } from "@/types";
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
    if (
      call.extraction_status === "done" &&
      call.extraction_cache &&
      call.extraction_cache.length > 0 &&
      !extracted
    ) {
      setTopics(call.extraction_cache);
      setExtracted(true);
    }
    if (call.extraction_status === "failed" && !extracted) {
      setError("Extraction failed in background. Please try again.");
    }
  }, [call.extraction_status, call.extraction_cache, extracted]);

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

  const deleteTopic = async (idx: number) => {
    const topic = topics[idx];
    const id = topic.id ?? topic.topic_id;
    if (!confirm(`Delete topic "${topic.name}"?`)) return;
    setTopics((prev) => prev.filter((_, i) => i !== idx));
    if (!id) return;
    try {
      await topicsAPI.deleteTopic(id);
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
    try {
      logger.info("[CallTopicsStage] re-extracting call topics", { data: { callId: call.id } });
      await topicsAPI.extractCall(call.id);
      setPolling(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Extraction failed";
      logger.error("[CallTopicsStage] re-extraction failed", { data: err });
      if (msg.includes("wait a moment")) setRateLimited(true);
      setError(msg);
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
  const callTitle = call.title ?? "Untitled";
  const callDate = (call.created_at ?? "").slice(0, 10);

  // ── Render ──
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

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
              ? `Extracted tasks (${taskCount} task${taskCount === 1 ? "" : "s"} across ${topics.length} topic${topics.length === 1 ? "" : "s"})`
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
        /* ── Topic table ── */
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
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: 13,
                  tableLayout: "fixed",
                }}
              >
                <colgroup>
                  <col style={{ width: 280 }} />
                  <col />
                  <col style={{ width: 260 }} />
                  <col style={{ width: 92 }} />
                  <col style={{ width: 108 }} />
                  <col style={{ width: 46 }} />
                  <col style={{ width: 50 }} />
                </colgroup>
                <thead>
                  <tr
                    style={{
                      background: "#fafbfc",
                      color: "#5e6c84",
                      fontSize: 10,
                      textTransform: "uppercase",
                      letterSpacing: ".05em",
                    }}
                  >
                    <th style={th}>Topic / key terms</th>
                    <th style={th}>Task</th>
                    <th style={th}>Next step</th>
                    <th style={th}>Owner</th>
                    <th style={th}>Status</th>
                    <th style={{ ...th, textAlign: "center" }}>Ev.</th>
                    <th style={{ ...th, textAlign: "center" }}></th>
                  </tr>
                </thead>
                <tbody>
                  {topics.flatMap((topic, ti) => {
                    const importance = topic.importance ?? "medium";
                    const keyTerms = topic.key_terms ?? [];
                    const evidence = topic.evidence ?? [];
                    const tasks = topic.tasks ?? [];

                    const rows = tasks.map((task, taskIdx) => (
                      <tr
                        key={`${ti}-${task.task_id}`}
                        style={
                          taskIdx === 0
                            ? { borderTop: "2px solid #dfe1e6" }
                            : undefined
                        }
                      >
                        {/* Topic + key terms — repeated on every task row per spec Q2(c) */}
                        <td
                          style={{
                            ...td,
                            verticalAlign: "top",
                            borderRight: "1px solid #f0f1f3",
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 6,
                              marginBottom: 8,
                            }}
                          >
                            <input
                              value={topic.name}
                              onChange={(e) =>
                                patchTopic(ti, { name: e.target.value })
                              }
                              style={topicNameStyle}
                            />
                            <select
                              value={importance}
                              onChange={(e) =>
                                patchTopic(ti, {
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
                          </div>
                          <KeyTermChips
                            terms={keyTerms}
                            editable
                            onChange={(next) =>
                              patchTopic(ti, { key_terms: next })
                            }
                          />
                        </td>

                        {/* Task */}
                        <td style={td}>
                          <input
                            value={task.task}
                            onChange={(e) =>
                              updateTasks(
                                ti,
                                tasks.map((t, i) =>
                                  i === taskIdx
                                    ? { ...t, task: e.target.value }
                                    : t
                                )
                              )
                            }
                            style={cellInput}
                            placeholder="Describe task…"
                          />
                        </td>

                        {/* Next step */}
                        <td style={td}>
                          <input
                            value={task.next_step}
                            onChange={(e) =>
                              updateTasks(
                                ti,
                                tasks.map((t, i) =>
                                  i === taskIdx
                                    ? { ...t, next_step: e.target.value }
                                    : t
                                )
                              )
                            }
                            style={cellInput}
                            placeholder="Next action…"
                          />
                        </td>

                        {/* Owner */}
                        <td style={td}>
                          <input
                            value={task.owner}
                            placeholder="— add"
                            onChange={(e) =>
                              updateTasks(
                                ti,
                                tasks.map((t, i) =>
                                  i === taskIdx
                                    ? { ...t, owner: e.target.value }
                                    : t
                                )
                              )
                            }
                            style={cellInput}
                          />
                        </td>

                        {/* Status */}
                        <td style={td}>
                          <select
                            value={task.status}
                            onChange={(e) =>
                              updateTasks(
                                ti,
                                tasks.map((t, i) =>
                                  i === taskIdx
                                    ? {
                                        ...t,
                                        status: e.target.value as TaskData["status"],
                                      }
                                    : t
                                )
                              )
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

                        {/* Evidence popover */}
                        <td style={{ ...td, textAlign: "center" }}>
                          <EvidenceRefPopover evidence={evidence} />
                        </td>

                        {/* Delete task */}
                        <td style={{ ...td, textAlign: "center" }}>
                          <button
                            type="button"
                            onClick={() =>
                              updateTasks(
                                ti,
                                tasks.filter((_, i) => i !== taskIdx)
                              )
                            }
                            style={iconBtn}
                            title="Delete task"
                          >
                            ×
                          </button>
                        </td>
                      </tr>
                    ));

                    // Footer row: + Add task / Delete topic
                    rows.push(
                      <tr
                        key={`${ti}-footer`}
                        style={{ background: "#fafbfc" }}
                      >
                        {/* Topic cell always present — footer is its own row, not covered by any rowSpan */}
                        <td
                          style={{
                            ...td,
                            borderTop: tasks.length === 0 ? "2px solid #dfe1e6" : undefined,
                            borderRight: "1px solid #f0f1f3",
                          }}
                        >
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 6,
                              marginBottom: 8,
                            }}
                          >
                            <input
                              value={topic.name}
                              onChange={(e) =>
                                patchTopic(ti, { name: e.target.value })
                              }
                              style={topicNameStyle}
                            />
                            <select
                              value={importance}
                              onChange={(e) =>
                                patchTopic(ti, {
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
                          </div>
                          <KeyTermChips
                            terms={keyTerms}
                            editable
                            onChange={(next) =>
                              patchTopic(ti, { key_terms: next })
                            }
                          />
                        </td>
                        <td
                          colSpan={6}
                          style={{ padding: "7px 14px" }}
                        >
                          <button
                            type="button"
                            onClick={() =>
                              updateTasks(ti, [
                                ...tasks,
                                {
                                  task_id: crypto.randomUUID(),
                                  task: "",
                                  next_step: "",
                                  status: "open",
                                  owner: "",
                                },
                              ])
                            }
                            style={addTaskBtn}
                          >
                            + Add task to &ldquo;{topic.name}&rdquo;
                          </button>
                          <button
                            type="button"
                            onClick={() => deleteTopic(ti)}
                            style={{
                              ...iconBtn,
                              marginLeft: 8,
                              color: "#bf2600",
                              fontSize: 11,
                            }}
                          >
                            Delete topic
                          </button>
                        </td>
                      </tr>
                    );

                    return rows;
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Style constants ────────────────────────────────────────────────────────────

const th: React.CSSProperties = {
  padding: "10px 12px",
  textAlign: "left",
  fontWeight: 600,
  borderBottom: "1px solid #dfe1e6",
};
const td: React.CSSProperties = {
  padding: "11px 12px",
  verticalAlign: "top",
};
const cellInput: React.CSSProperties = {
  width: "100%",
  border: "none",
  background: "transparent",
  fontSize: 13,
  padding: 2,
  color: "#172b4d",
  fontFamily: "inherit",
};
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
const addTaskBtn: React.CSSProperties = {
  fontSize: 11,
  color: "#0052cc",
  background: "none",
  border: "1px dashed #c1c7d0",
  padding: "5px 12px",
  borderRadius: 4,
  cursor: "pointer",
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
