"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { callsAPI, libraryAPI, topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type {
  Call,
  TopicData,
  TaskData,
  TopicStatus,
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
  // We only allow the polling loop to KILL polling once we've confirmed the
  // parent has fetched fresh data showing the backend is actually working
  // (i.e. extraction_status transitioned through "processing"). Without this
  // gate, clicking Re-extract reads the parent's STALE "done" + immediately
  // kills polling — masking the spinner until the user hits refresh. See
  // workflow/ERRORS.md ERR-005.
  const sawProcessingRef = useRef(false);
  useEffect(() => {
    if (call.extraction_status === "processing") {
      sawProcessingRef.current = true;
    }
  }, [call.extraction_status]);

  useEffect(() => {
    if (!polling) {
      sawProcessingRef.current = false;
      return;
    }
    // Only honor a "done"/"failed" status after the parent has refreshed at
    // least once into "processing". Otherwise a fresh click on Re-extract
    // would read the pre-click stale "done" and abort polling instantly.
    if (
      sawProcessingRef.current &&
      (call.extraction_status === "done" ||
        call.extraction_status === "failed")
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

  // Resolve the effective prompt + model: selected, else seeded-default.
  // Defensive category filter: libraryPrompts SHOULD be pre-filtered to
  // call_topics by listByCategory, but the backend list endpoint used to
  // ignore the query param — keep the guard so this can't drift again.
  const effectivePrompt = useMemo(() => {
    const callTopicsPrompts = libraryPrompts.filter(
      (p) => p.category === "call_topics",
    );
    if (selectedPromptId) {
      return callTopicsPrompts.find((p) => p.id === selectedPromptId) ?? null;
    }
    return callTopicsPrompts.find((p) => p.seeded_by_default) ?? null;
  }, [selectedPromptId, libraryPrompts]);

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
          {effectivePrompt && (
            <>
              {" · "}
              <span style={{ color: "#42526e", textTransform: "none", letterSpacing: 0 }}>
                {effectivePrompt.name}
              </span>
              {effectivePrompt.model && (
                <span style={{ color: "#7a869a", textTransform: "none", letterSpacing: 0 }}>
                  {" "}({effectivePrompt.llm ?? "?"}/{effectivePrompt.model})
                </span>
              )}
            </>
          )}
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
      {/* Spinner takes priority over `extracted` so a click on Re-extract
          flips the UI to Generating… immediately, no matter what the parent
          `call` prop still claims. Otherwise the old topic table can linger
          until the parent re-fetches (3s polling tick), masking the click. */}
      {polling || extracting ? (
        <div style={{ padding: 20 }}>
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
        </div>
      ) : !extracted ? (
        <div style={{ padding: 20 }}>
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
        </div>
      ) : (
        /* ── Flat table: one row per task, topic-level cells on first row ── */
        <div style={{ flex: 1, overflowY: "auto", padding: 20 }}>
          {loading ? (
            <div style={{ color: "#5e6c84", fontSize: 13 }}>Loading topics…</div>
          ) : topics.length === 0 ? (
            <div style={{ color: "#5e6c84", fontSize: 13 }}>
              No topics extracted. Click Re-extract to run the prompt.
            </div>
          ) : (
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: 12.5,
                tableLayout: "fixed",
                background: "white",
                border: "1px solid #dfe1e6",
                borderRadius: 6,
              }}
            >
              <colgroup>
                <col style={{ width: 200 }} /> {/* Topic */}
                <col style={{ width: 180 }} /> {/* Key terms */}
                <col />                        {/* Task — auto */}
                <col />                        {/* Next step — auto */}
                <col style={{ width: 90 }} />  {/* Owner */}
                <col style={{ width: 110 }} /> {/* Status */}
                <col style={{ width: 240 }} /> {/* Open questions */}
                <col style={{ width: 220 }} /> {/* Decisions */}
                <col style={{ width: 44 }} />  {/* Evidence */}
                <col style={{ width: 36 }} />  {/* Delete */}
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
                  <th style={TABLE_TH_STYLE}>Topic</th>
                  <th style={TABLE_TH_STYLE}>Key terms</th>
                  <th style={TABLE_TH_STYLE}>Task</th>
                  <th style={TABLE_TH_STYLE}>Next step</th>
                  <th style={TABLE_TH_STYLE}>Owner</th>
                  <th style={TABLE_TH_STYLE}>Status</th>
                  <th style={TABLE_TH_STYLE}>Open questions</th>
                  <th style={TABLE_TH_STYLE}>Decisions</th>
                  <th style={{ ...TABLE_TH_STYLE, textAlign: "center" }}>Ev.</th>
                  <th style={{ ...TABLE_TH_STYLE, textAlign: "center" }}></th>
                </tr>
              </thead>
              <tbody>
                {topics.flatMap((topic, ti) => {
                  const tasks = topic.tasks ?? [];
                  const oqs = normalizeOpenQuestions(topic.open_questions);
                  const decisions = normalizeDecisions(topic.decisions);
                  const keyTerms = topic.key_terms ?? [];
                  // Topic must have at least one row even if no tasks — so topic-level cells stay visible.
                  const rowCount = Math.max(tasks.length, 1);
                  const isLastTopic = ti === topics.length - 1;
                  return Array.from({ length: rowCount }, (_, ri) => {
                    const isFirstRow = ri === 0;
                    const isLastRowOfTopic = ri === rowCount - 1;
                    const task = tasks[ri]; // undefined if rowCount > tasks.length (topic with no tasks)
                    const borderBottom = !isLastRowOfTopic
                      ? "1px solid #f1f2f4" // inner — between tasks of same topic
                      : isLastTopic
                        ? "none"
                        : "2px solid #dfe1e6"; // topic separator
                    return (
                      <tr
                        key={`${topic.id ?? topic.topic_id ?? ti}-${task?.task_id ?? `empty-${ri}`}`}
                        style={{ borderBottom }}
                      >
                        {/* Topic name + importance — only first row */}
                        <td style={TABLE_TD_STYLE}>
                          {isFirstRow && (
                            <TopicNameCell
                              topic={topic}
                              onPatchTopic={(p) => patchTopic(ti, p)}
                              onContextMenu={(e) => {
                                e.preventDefault();
                                setMenu({ ti, x: e.clientX, y: e.clientY });
                              }}
                            />
                          )}
                        </td>
                        {/* Key terms — only first row */}
                        <td style={TABLE_TD_STYLE}>
                          {isFirstRow && (
                            <KeyTermChips
                              terms={keyTerms}
                              editable
                              onChange={(next) => patchTopic(ti, { key_terms: next })}
                            />
                          )}
                        </td>
                        {/* Task / Next step / Owner / Status — per task */}
                        <td style={TABLE_TD_STYLE}>
                          {task && (
                            <input
                              key={task.task_id}
                              type="text"
                              defaultValue={task.task}
                              placeholder="Describe task…"
                              onBlur={(e) => {
                                if (e.target.value !== task.task)
                                  updateTasks(
                                    ti,
                                    tasks.map((t, i) =>
                                      i === ri ? { ...t, task: e.target.value } : t,
                                    ),
                                  );
                              }}
                              style={INLINE_INPUT_STYLE}
                            />
                          )}
                        </td>
                        <td style={TABLE_TD_STYLE}>
                          {task && (
                            <input
                              key={`${task.task_id}-ns`}
                              type="text"
                              defaultValue={task.next_step}
                              placeholder="Next action…"
                              onBlur={(e) => {
                                if (e.target.value !== task.next_step)
                                  updateTasks(
                                    ti,
                                    tasks.map((t, i) =>
                                      i === ri ? { ...t, next_step: e.target.value } : t,
                                    ),
                                  );
                              }}
                              style={INLINE_INPUT_STYLE}
                            />
                          )}
                        </td>
                        <td style={TABLE_TD_STYLE}>
                          {task && (
                            <input
                              key={`${task.task_id}-ow`}
                              type="text"
                              defaultValue={task.owner}
                              placeholder="— add"
                              onBlur={(e) => {
                                if (e.target.value !== task.owner)
                                  updateTasks(
                                    ti,
                                    tasks.map((t, i) =>
                                      i === ri ? { ...t, owner: e.target.value } : t,
                                    ),
                                  );
                              }}
                              style={INLINE_INPUT_STYLE}
                            />
                          )}
                        </td>
                        <td style={TABLE_TD_STYLE}>
                          {task && (
                            <select
                              value={task.status}
                              onChange={(e) =>
                                updateTasks(
                                  ti,
                                  tasks.map((t, i) =>
                                    i === ri
                                      ? { ...t, status: e.target.value as TopicStatus }
                                      : t,
                                  ),
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
                          )}
                        </td>
                        {/* Open questions — only first row */}
                        <td style={TABLE_TD_STYLE}>
                          {isFirstRow && (
                            <OpenQuestionsCell
                              oqs={oqs}
                              onUpdate={(next) => updateOpenQuestions(ti, next)}
                            />
                          )}
                        </td>
                        {/* Decisions — only first row */}
                        <td style={TABLE_TD_STYLE}>
                          {isFirstRow && (
                            <DecisionsCell
                              decisions={decisions}
                              onUpdate={(next) => updateDecisions(ti, next)}
                            />
                          )}
                        </td>
                        {/* Evidence — first row only (topic-level indicator) */}
                        <td style={{ ...TABLE_TD_STYLE, textAlign: "center" }}>
                          {isFirstRow && topic.evidence && topic.evidence.length > 0 && (
                            <EvidenceRefPopover evidence={topic.evidence} />
                          )}
                        </td>
                        {/* Delete task; falls back to delete topic on first row of empty-tasks topic */}
                        <td style={{ ...TABLE_TD_STYLE, textAlign: "center" }}>
                          {task ? (
                            <button
                              type="button"
                              onClick={() =>
                                updateTasks(
                                  ti,
                                  tasks.filter((_, i) => i !== ri),
                                )
                              }
                              style={iconBtn}
                              title="Delete task"
                            >
                              ×
                            </button>
                          ) : isFirstRow ? (
                            <button
                              type="button"
                              onClick={() => deleteTopic(ti)}
                              style={iconBtn}
                              title="Delete topic"
                            >
                              ×
                            </button>
                          ) : null}
                        </td>
                      </tr>
                    );
                  });
                })}
              </tbody>
            </table>
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

// ── Flat-table cell style constants ────────────────────────────────────────────

const TABLE_TH_STYLE: React.CSSProperties = {
  padding: "6px 8px",
  textAlign: "left",
  fontWeight: 600,
  borderBottom: "1px solid #dfe1e6",
};
const TABLE_TD_STYLE: React.CSSProperties = {
  padding: "8px",
  verticalAlign: "top",
};
const INLINE_INPUT_STYLE: React.CSSProperties = {
  fontSize: 12,
  border: "1px solid transparent",
  background: "transparent",
  padding: "2px 4px",
  borderRadius: 3,
  width: "100%",
  fontFamily: "inherit",
  color: "#172b4d",
  outline: "none",
};
const EMPTY_CELL_STYLE: React.CSSProperties = {
  fontSize: 11,
  color: "#97a0af",
  fontStyle: "italic",
  padding: "2px 0",
};
const STATUS_MINI_SELECT_STYLE: React.CSSProperties = {
  fontSize: 9,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: ".04em",
  padding: "1px 4px",
  borderRadius: 3,
  border: "1px solid #dfe1e6",
  background: "white",
  color: "#0052cc",
  cursor: "pointer",
};
const ADD_CELL_BUTTON_STYLE: React.CSSProperties = {
  marginTop: 4,
  fontSize: 10,
  color: "#0052cc",
  background: "none",
  border: "1px dashed #c1c7d0",
  padding: "2px 8px",
  borderRadius: 3,
  cursor: "pointer",
  alignSelf: "flex-start",
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

// ── TopicNameCell ──────────────────────────────────────────────────────────────

function TopicNameCell({
  topic,
  onPatchTopic,
  onContextMenu,
}: {
  topic: TopicData;
  onPatchTopic: (partial: Partial<TopicData>) => void;
  onContextMenu: (e: React.MouseEvent) => void;
}) {
  const importance = topic.importance ?? "medium";
  return (
    <div
      onContextMenu={onContextMenu}
      style={{ display: "flex", flexDirection: "column", gap: 4 }}
    >
      <input
        defaultValue={topic.name}
        key={topic.id ?? topic.topic_id ?? "new"}
        onBlur={(e) => {
          if (e.target.value !== topic.name) onPatchTopic({ name: e.target.value });
        }}
        style={{
          fontSize: 13,
          fontWeight: 600,
          border: "1px solid transparent",
          background: "transparent",
          padding: "2px 4px",
          borderRadius: 3,
          color: "#172b4d",
          fontFamily: "inherit",
          width: "100%",
          outline: "none",
        }}
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
          alignSelf: "flex-start",
        }}
      >
        <option value="high">HIGH</option>
        <option value="medium">MED</option>
        <option value="low">LOW</option>
      </select>
    </div>
  );
}

// ── OpenQuestionsCell ──────────────────────────────────────────────────────────

function OpenQuestionsCell({
  oqs,
  onUpdate,
}: {
  oqs: OpenQuestionData[];
  onUpdate: (next: OpenQuestionData[]) => void;
}) {
  const update = (i: number, patch: Partial<OpenQuestionData>) =>
    onUpdate(oqs.map((q, idx) => (idx === i ? { ...q, ...patch } : q)));
  const remove = (i: number) => onUpdate(oqs.filter((_, idx) => idx !== i));
  const add = () =>
    onUpdate([
      ...oqs,
      { id: crypto.randomUUID(), text: "", owner: "", status: "open" },
    ]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {oqs.length === 0 && (
        <div style={EMPTY_CELL_STYLE}>— no open questions in this call</div>
      )}
      {oqs.map((q, i) => (
        <div
          key={q.id || `new-${i}`}
          style={{ display: "flex", gap: 4, alignItems: "flex-start" }}
        >
          <span style={{ color: "#5e6c84", marginTop: 4, fontSize: 10 }}>•</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <input
              key={`${q.id || `new-${i}`}-txt`}
              type="text"
              defaultValue={q.text}
              onBlur={(e) => {
                if (e.target.value !== q.text) update(i, { text: e.target.value });
              }}
              placeholder="open question"
              style={INLINE_INPUT_STYLE}
            />
            <div
              style={{
                display: "flex",
                gap: 4,
                alignItems: "center",
                marginTop: 2,
              }}
            >
              <input
                key={`${q.id || `new-${i}`}-ow`}
                type="text"
                defaultValue={q.owner}
                onBlur={(e) => {
                  if (e.target.value !== q.owner) update(i, { owner: e.target.value });
                }}
                placeholder="owner"
                style={{ ...INLINE_INPUT_STYLE, width: 70, fontSize: 10 }}
              />
              <select
                value={q.status}
                onChange={(e) =>
                  update(i, { status: e.target.value as TopicStatus })
                }
                style={STATUS_MINI_SELECT_STYLE}
              >
                <option value="open">OPEN</option>
                <option value="in_progress">IN_PROG</option>
                <option value="resolved">RESOLVED</option>
              </select>
            </div>
          </div>
          <button
            type="button"
            onClick={() => remove(i)}
            style={iconBtn}
            title="Remove open question"
          >
            ×
          </button>
        </div>
      ))}
      <button type="button" onClick={add} style={ADD_CELL_BUTTON_STYLE}>
        + add open question
      </button>
    </div>
  );
}

// ── DecisionsCell ──────────────────────────────────────────────────────────────

function DecisionsCell({
  decisions,
  onUpdate,
}: {
  decisions: DecisionData[];
  onUpdate: (next: DecisionData[]) => void;
}) {
  const update = (i: number, patch: Partial<DecisionData>) =>
    onUpdate(decisions.map((d, idx) => (idx === i ? { ...d, ...patch } : d)));
  const remove = (i: number) => onUpdate(decisions.filter((_, idx) => idx !== i));
  const add = () =>
    onUpdate([...decisions, { id: crypto.randomUUID(), text: "" }]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {decisions.length === 0 && (
        <div style={EMPTY_CELL_STYLE}>— no decisions in this call</div>
      )}
      {decisions.map((d, i) => (
        <div
          key={d.id || `new-${i}`}
          style={{ display: "flex", gap: 4, alignItems: "flex-start" }}
        >
          <span style={{ color: "#5e6c84", marginTop: 4, fontSize: 10 }}>•</span>
          <input
            key={`${d.id || `new-${i}`}-txt`}
            type="text"
            defaultValue={d.text}
            onBlur={(e) => {
              if (e.target.value !== d.text) update(i, { text: e.target.value });
            }}
            placeholder="decision"
            style={{ ...INLINE_INPUT_STYLE, flex: 1 }}
          />
          <button
            type="button"
            onClick={() => remove(i)}
            style={iconBtn}
            title="Remove decision"
          >
            ×
          </button>
        </div>
      ))}
      <button type="button" onClick={add} style={ADD_CELL_BUTTON_STYLE}>
        + add decision
      </button>
    </div>
  );
}
