"use client";

import { useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type {
  Call,
  TopicData,
  OpenQuestionData,
  DecisionData,
} from "@/types";
import KeyTermChips from "./KeyTermChips";
import EvidenceRefPopover from "./EvidenceRefPopover";

type Props = {
  callId: string;
  call?: Call;
};

// ── Style constants (mirrored from CallTopicsStage) ───────────────────────────

const STATUS_BG = { open: "#e9f0ff", in_progress: "#fff4e6", resolved: "#e3fcef" } as const;
const STATUS_FG = { open: "#0052cc", in_progress: "#974f0c", resolved: "#006644" } as const;
const IMP_BG    = { high: "#ffebe5", medium: "#fffae6", low: "#f4f5f7" } as const;
const IMP_FG    = { high: "#bf2600", medium: "#974f0c", low: "#5e6c84" } as const;

const TABLE_TH_STYLE: React.CSSProperties = {
  padding: "6px 8px",
  textAlign: "left",
  fontWeight: 600,
  borderBottom: "1px solid #dfe1e6",
};
const TABLE_TD_STYLE: React.CSSProperties = {
  padding: "8px",
  verticalAlign: "top",
  color: "#172b4d",
};
const EMPTY_CELL_STYLE: React.CSSProperties = {
  fontSize: 11,
  color: "#97a0af",
  fontStyle: "italic",
  padding: "2px 0",
};
const READ_ONLY_TEXT_STYLE: React.CSSProperties = {
  fontSize: 12,
  color: "#172b4d",
  padding: "2px 4px",
  lineHeight: 1.4,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};
const STATUS_BADGE_STYLE: React.CSSProperties = {
  fontSize: 9,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: ".04em",
  padding: "2px 6px",
  borderRadius: 3,
  display: "inline-block",
};
const IMP_BADGE_STYLE: React.CSSProperties = {
  fontSize: 9,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: ".04em",
  padding: "2px 6px",
  borderRadius: 3,
  display: "inline-block",
};

// ── Back-compat adapters (mirrored from CallTopicsStage) ──────────────────────

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

// ── Component ─────────────────────────────────────────────────────────────────

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

      <div style={{ flex: 1, overflowY: "auto", padding: 20 }}>
        {topics.length === 0 ? (
          <div style={{ color: "#5e6c84", fontSize: 13, textAlign: "center", padding: "32px 0" }}>
            No topics recorded for this call.
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
              {/* NO delete column (read-only) */}
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
                const importance = topic.importance ?? "medium";
                return Array.from({ length: rowCount }, (_, ri) => {
                  const isFirstRow = ri === 0;
                  const isLastRowOfTopic = ri === rowCount - 1;
                  const task = tasks[ri]; // undefined if rowCount > tasks.length (topic with no tasks)
                  const borderBottom = !isLastRowOfTopic
                    ? "1px solid #f1f2f4"  // inner — between tasks of same topic
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
                          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                            <div style={{
                              fontSize: 13,
                              fontWeight: 600,
                              color: "#172b4d",
                              padding: "2px 4px",
                              wordBreak: "break-word",
                            }}>
                              {topic.name}
                            </div>
                            <span style={{
                              ...IMP_BADGE_STYLE,
                              background: IMP_BG[importance],
                              color: IMP_FG[importance],
                              alignSelf: "flex-start",
                            }}>
                              {importance === "medium" ? "MED" : importance.toUpperCase()}
                            </span>
                          </div>
                        )}
                      </td>
                      {/* Key terms — only first row */}
                      <td style={TABLE_TD_STYLE}>
                        {isFirstRow && keyTerms.length > 0 && (
                          <KeyTermChips terms={keyTerms} />
                        )}
                      </td>
                      {/* Task / Next step / Owner / Status — per task */}
                      <td style={TABLE_TD_STYLE}>
                        {task && <div style={READ_ONLY_TEXT_STYLE}>{task.task}</div>}
                      </td>
                      <td style={TABLE_TD_STYLE}>
                        {task && <div style={READ_ONLY_TEXT_STYLE}>{task.next_step}</div>}
                      </td>
                      <td style={TABLE_TD_STYLE}>
                        {task && (
                          <div style={READ_ONLY_TEXT_STYLE}>{task.owner || "—"}</div>
                        )}
                      </td>
                      <td style={TABLE_TD_STYLE}>
                        {task && (
                          <span style={{
                            ...STATUS_BADGE_STYLE,
                            background: STATUS_BG[task.status] ?? STATUS_BG.open,
                            color: STATUS_FG[task.status] ?? STATUS_FG.open,
                          }}>
                            {task.status.replace("_", " ")}
                          </span>
                        )}
                      </td>
                      {/* Open questions — only first row */}
                      <td style={TABLE_TD_STYLE}>
                        {isFirstRow && (
                          oqs.length === 0 ? (
                            <div style={EMPTY_CELL_STYLE}>— no open questions in this call</div>
                          ) : (
                            <ul style={{ margin: 0, paddingLeft: 16, listStyle: "disc" }}>
                              {oqs.map((q, qi) => (
                                <li key={q.id || qi} style={{ marginBottom: 4, fontSize: 12, color: "#172b4d", lineHeight: 1.4 }}>
                                  <div style={{ wordBreak: "break-word" }}>{q.text}</div>
                                  {(q.owner || q.status) && (
                                    <div style={{ fontSize: 10, color: "#7a869a", marginTop: 2, display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
                                      {q.owner && <span>{q.owner}</span>}
                                      {q.owner && q.status && <span>·</span>}
                                      {q.status && (
                                        <span style={{
                                          ...STATUS_BADGE_STYLE,
                                          background: STATUS_BG[q.status] ?? STATUS_BG.open,
                                          color: STATUS_FG[q.status] ?? STATUS_FG.open,
                                        }}>
                                          {q.status.replace("_", " ")}
                                        </span>
                                      )}
                                    </div>
                                  )}
                                </li>
                              ))}
                            </ul>
                          )
                        )}
                      </td>
                      {/* Decisions — only first row */}
                      <td style={TABLE_TD_STYLE}>
                        {isFirstRow && (
                          decisions.length === 0 ? (
                            <div style={EMPTY_CELL_STYLE}>— no decisions in this call</div>
                          ) : (
                            <ul style={{ margin: 0, paddingLeft: 16, listStyle: "disc" }}>
                              {decisions.map((d, di) => (
                                <li key={d.id || di} style={{ marginBottom: 4, fontSize: 12, color: "#172b4d", lineHeight: 1.4, wordBreak: "break-word" }}>
                                  {d.text}
                                </li>
                              ))}
                            </ul>
                          )
                        )}
                      </td>
                      {/* Evidence — first row only (topic-level indicator) */}
                      <td style={{ ...TABLE_TD_STYLE, textAlign: "center" }}>
                        {isFirstRow && topic.evidence && topic.evidence.length > 0 && (
                          <EvidenceRefPopover evidence={topic.evidence} />
                        )}
                      </td>
                    </tr>
                  );
                });
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
