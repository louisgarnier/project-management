"use client";

import { useCallback, useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import type {
  TopicEvidence,
  EvidenceCall,
  EvidenceLineageNode,
  EvidenceRawExtract,
  EvidenceMatchGroup,
  EvidenceVerification,
  TopicData,
} from "@/types";
import { CALL_COLORS } from "@/utils/callColors";
import ProvenancePill from "./ProvenancePill";

// Drawer supports three modes:
//  - "lineage": fetches /api/topics/{id}/evidence, renders per-call chronology
//    with ancestor provenance (Story 10.4). Used on Project Updates + Timeline.
//  - "call_topic": no fetch — renders a single pending-topic card showing the
//    transcript excerpt that caused the extraction (Story 10.7). Used on
//    Call Topics stage where topics have no topic_id yet.
//  - "matching": side-by-side view (Story 10.8) — left column shows existing
//    project topic's lineage (fetched, like lineage mode); right column shows
//    the current call's extraction (pending_topic). Used on Project Matching
//    stage. Classification (followed_up/new/not_discussed) drives which side
//    is empty and the footer explanation.
type MatchingKind = "followed_up" | "new" | "not_discussed";

type Props =
  | {
      open: boolean;
      topicId: string | null;
      onClose: () => void;
      mode?: "lineage";
      pendingTopic?: undefined;
    }
  | {
      open: boolean;
      onClose: () => void;
      mode: "call_topic";
      pendingTopic: TopicData | null;
      topicId?: undefined;
    }
  | {
      open: boolean;
      onClose: () => void;
      mode: "matching";
      topicId: string | null;
      pendingTopic: TopicData | null;
      kind: MatchingKind;
    };

// Shared palette: aligned with ProjectUpdatesStage.tsx
const STATUS_BADGE: Record<string, React.CSSProperties> = {
  open:        { background: "#e9f0ff", color: "#0052cc" },
  in_progress: { background: "#fff4e6", color: "#974f0c" },
  resolved:    { background: "#e3fcef", color: "#006644" },
};

const BADGE_BASE: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  textTransform: "uppercase",
  padding: "2px 6px",
  borderRadius: 3,
  whiteSpace: "nowrap",
  letterSpacing: ".04em",
};

function formatDate(iso: string | null): string {
  if (!iso) return "";
  // Backend returns ISO date (YYYY-MM-DD) or ISO datetime; display as YYYY-MM-DD.
  return iso.slice(0, 10);
}

function LineageChip({ lineage, currentTopicId }: { lineage: EvidenceLineageNode[]; currentTopicId: string }) {
  if (lineage.length <= 1) return null;
  const ancestors = lineage.filter((n) => n.topic_id !== currentTopicId);
  if (ancestors.length === 0) return null;
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 11,
        color: "#5e6c84",
        background: "#f4f5f7",
        border: "1px solid #dfe1e6",
        borderRadius: 4,
        padding: "4px 10px",
        marginTop: 8,
      }}
    >
      <span style={{ fontWeight: 700, color: "#172b4d" }}>Merged from:</span>
      <span>{ancestors.map((n) => n.name).join(", ")}</span>
    </div>
  );
}

function Collapsible({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ marginTop: 8 }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          background: "none",
          border: "none",
          padding: 0,
          cursor: "pointer",
          fontSize: 11,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: ".04em",
          color: "#5e6c84",
          fontFamily: "inherit",
        }}
      >
        {open ? "▾" : "▸"} {title}
      </button>
      {open && <div style={{ marginTop: 6, paddingLeft: 14 }}>{children}</div>}
    </div>
  );
}

function RawExtractSection({ raw }: { raw: EvidenceRawExtract }) {
  return (
    <Collapsible title="Raw extract (pre-merge)">
      <div style={{ fontSize: 12, color: "#172b4d", lineHeight: 1.5 }}>
        <div style={{ marginBottom: 6 }}>
          <span style={{ fontWeight: 700, color: "#5e6c84", fontSize: 10, textTransform: "uppercase" }}>
            Summary
          </span>
          <div style={{ marginTop: 2 }}>{raw.summary || <em style={{ color: "#97a0af" }}>(empty)</em>}</div>
        </div>
        <div style={{ marginBottom: 6 }}>
          <span style={{ fontWeight: 700, color: "#5e6c84", fontSize: 10, textTransform: "uppercase" }}>
            Follow-ups
          </span>
          {raw.follow_up_items.length === 0 ? (
            <div style={{ color: "#97a0af", fontStyle: "italic", marginTop: 2 }}>(none)</div>
          ) : (
            <ul style={{ margin: "2px 0 0", paddingLeft: 20 }}>
              {raw.follow_up_items.map((f, i) => (
                <li key={i} style={{ fontSize: 12, color: "#172b4d", lineHeight: 1.5 }}>{f}</li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <span style={{ fontWeight: 700, color: "#5e6c84", fontSize: 10, textTransform: "uppercase" }}>
            Decisions
          </span>
          {raw.decisions.length === 0 ? (
            <div style={{ color: "#97a0af", fontStyle: "italic", marginTop: 2 }}>(none)</div>
          ) : (
            <ul style={{ margin: "2px 0 0", paddingLeft: 20 }}>
              {raw.decisions.map((d, i) => (
                <li key={i} style={{ fontSize: 12, color: "#172b4d", lineHeight: 1.5 }}>{d}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Collapsible>
  );
}

function MatchGroupSection({ group }: { group: EvidenceMatchGroup }) {
  const projectCount = group.project_topic_ids.length;
  const callCount = group.call_topic_names.length;
  return (
    <Collapsible title="Match group">
      <div style={{ fontSize: 12, color: "#172b4d", lineHeight: 1.5 }}>
        Matched {projectCount} existing topic{projectCount === 1 ? "" : "s"} +{" "}
        {callCount} call topic{callCount === 1 ? "" : "s"}:
        <div style={{ marginTop: 4 }}>
          <span style={{ color: "#5e6c84", fontSize: 11 }}>Project topic ids: </span>
          <span>{projectCount === 0 ? <em style={{ color: "#97a0af" }}>(none)</em> : group.project_topic_ids.join(", ")}</span>
        </div>
        <div style={{ marginTop: 2 }}>
          <span style={{ color: "#5e6c84", fontSize: 11 }}>Call topics: </span>
          <span>{callCount === 0 ? <em style={{ color: "#97a0af" }}>(none)</em> : group.call_topic_names.join(", ")}</span>
        </div>
      </div>
    </Collapsible>
  );
}

function VerificationSection({ v }: { v: EvidenceVerification }) {
  return (
    <Collapsible title="Not-discussed verification">
      <div style={{ fontSize: 12, color: "#172b4d", lineHeight: 1.5 }}>
        <span
          style={{
            ...BADGE_BASE,
            background: v.discussed ? "#fff4e6" : "#e3fcef",
            color: v.discussed ? "#974f0c" : "#006644",
          }}
        >
          {v.discussed ? "⚠ Discussed" : "✓ Confirmed not discussed"}
        </span>
        {v.transcript_excerpt && (
          <div
            style={{
              marginTop: 6,
              fontStyle: "italic",
              color: "#5e6c84",
              borderLeft: "3px solid #dfe1e6",
              paddingLeft: 8,
              whiteSpace: "pre-wrap",
            }}
          >
            “{v.transcript_excerpt}”
          </div>
        )}
        {v.reasoning && (
          <div style={{ marginTop: 6, color: "#172b4d" }}>
            <span style={{ fontWeight: 700, color: "#5e6c84", fontSize: 10, textTransform: "uppercase" }}>
              Reasoning:{" "}
            </span>
            {v.reasoning}
          </div>
        )}
      </div>
    </Collapsible>
  );
}

function CallCard({
  call,
  index,
  currentTopicId,
}: {
  call: EvidenceCall;
  index: number;
  currentTopicId: string;
}) {
  const color = CALL_COLORS[index % CALL_COLORS.length];
  const isFromAncestor = call.source_topic_id !== currentTopicId;

  return (
    <div
      style={{
        border: "1px solid #dfe1e6",
        borderRadius: 6,
        background: "white",
        borderLeft: `6px solid ${color}`,
        marginBottom: 12,
        overflow: "hidden",
      }}
    >
      <div style={{ padding: "12px 14px" }}>
        {/* Header row */}
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            flexWrap: "wrap",
            gap: 8,
            marginBottom: 8,
          }}
        >
          <span style={{ fontSize: 13, fontWeight: 700, color: "#172b4d" }}>{call.call_title}</span>
          {call.call_date && (
            <span style={{ fontSize: 11, color: "#5e6c84" }}>· {formatDate(call.call_date)}</span>
          )}
          {isFromAncestor && (
            <span
              style={{
                ...BADGE_BASE,
                background: "#f0d3ff",
                color: "#5f2d7a",
              }}
              title={`This call came from ancestor topic: ${call.source_topic_name}`}
            >
              from: {call.source_topic_name}
            </span>
          )}
          {call.is_not_discussed && (
            <span style={{ ...BADGE_BASE, background: "#f4f5f7", color: "#5e6c84" }}>Not discussed</span>
          )}
        </div>

        {/* Transcript excerpt */}
        {call.transcript_excerpt ? (
          <div
            style={{
              fontSize: 12,
              color: "#172b4d",
              fontStyle: "italic",
              borderLeft: "3px solid #dfe1e6",
              paddingLeft: 10,
              whiteSpace: "pre-wrap",
              lineHeight: 1.5,
              marginBottom: 10,
            }}
          >
            “{call.transcript_excerpt}”
          </div>
        ) : (
          <div style={{ fontSize: 11, color: "#97a0af", fontStyle: "italic", marginBottom: 10 }}>
            (No excerpt captured for this call)
          </div>
        )}

        {/* After this call */}
        <div style={{ marginBottom: 8 }}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              textTransform: "uppercase",
              color: "#5e6c84",
              letterSpacing: ".04em",
              marginBottom: 3,
            }}
          >
            After this call:
          </div>
          <div style={{ fontSize: 12, color: "#172b4d", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
            {call.merged_summary || <em style={{ color: "#97a0af" }}>(empty)</em>}
          </div>
        </div>

        {/* Follow-ups */}
        <div style={{ marginBottom: 8 }}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              textTransform: "uppercase",
              color: "#5e6c84",
              letterSpacing: ".04em",
              marginBottom: 3,
            }}
          >
            Follow-ups
          </div>
          {call.follow_up_items.length === 0 ? (
            <div style={{ fontSize: 12, color: "#97a0af", fontStyle: "italic" }}>(none)</div>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none" }}>
              {call.follow_up_items.map((f, i) => (
                <li key={i} style={{ fontSize: 12, color: "#172b4d", lineHeight: 1.5,
                  display: "flex", alignItems: "flex-start", gap: 6, marginBottom: 2 }}>
                  <ProvenancePill callIndex={index} callTitle={call.call_title} />
                  <span>{f}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Decisions */}
        <div style={{ marginBottom: 8 }}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              textTransform: "uppercase",
              color: "#5e6c84",
              letterSpacing: ".04em",
              marginBottom: 3,
            }}
          >
            Decisions
          </div>
          {call.decisions.length === 0 ? (
            <div style={{ fontSize: 12, color: "#97a0af", fontStyle: "italic" }}>(none)</div>
          ) : (
            <ul style={{ margin: 0, paddingLeft: 0, listStyle: "none" }}>
              {call.decisions.map((d, i) => (
                <li key={i} style={{ fontSize: 12, color: "#172b4d", lineHeight: 1.5,
                  display: "flex", alignItems: "flex-start", gap: 6, marginBottom: 2 }}>
                  <ProvenancePill callIndex={index} callTitle={call.call_title} />
                  <span>{d}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Status badge */}
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {call.status && (
            <span
              style={{
                ...BADGE_BASE,
                ...(STATUS_BADGE[call.status] ?? STATUS_BADGE.open),
              }}
            >
              {call.status.replace("_", " ")}
            </span>
          )}
        </div>

        {/* Collapsibles */}
        {call.raw_extract && <RawExtractSection raw={call.raw_extract} />}
        {call.match_group && <MatchGroupSection group={call.match_group} />}
        {call.not_discussed_verification && (
          <VerificationSection v={call.not_discussed_verification} />
        )}
      </div>
    </div>
  );
}

function PendingTopicCard({ topic }: { topic: TopicData }) {
  return (
    <div
      style={{
        border: "1px solid #dfe1e6",
        borderRadius: 6,
        background: "white",
        borderLeft: `6px solid ${CALL_COLORS[0]}`,
        marginBottom: 12,
        padding: "14px 16px",
      }}
    >
      {topic.transcript_excerpt ? (
        <div style={{ marginBottom: 12 }}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              textTransform: "uppercase",
              color: "#5e6c84",
              letterSpacing: ".04em",
              marginBottom: 4,
            }}
          >
            Extracted from transcript
          </div>
          <div
            style={{
              fontSize: 13,
              color: "#172b4d",
              fontStyle: "italic",
              borderLeft: "3px solid #dfe1e6",
              paddingLeft: 10,
              whiteSpace: "pre-wrap",
              lineHeight: 1.5,
            }}
          >
            “{topic.transcript_excerpt}”
          </div>
        </div>
      ) : (
        <div style={{ fontSize: 11, color: "#97a0af", fontStyle: "italic", marginBottom: 12 }}>
          (No transcript excerpt captured for this topic)
        </div>
      )}

      <div style={{ marginBottom: 10 }}>
        <div
          style={{
            fontSize: 10,
            fontWeight: 700,
            textTransform: "uppercase",
            color: "#5e6c84",
            letterSpacing: ".04em",
            marginBottom: 3,
          }}
        >
          Summary
        </div>
        <div style={{ fontSize: 13, color: "#172b4d", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
          {topic.summary || <em style={{ color: "#97a0af" }}>(empty)</em>}
        </div>
      </div>

      <div style={{ marginBottom: 10 }}>
        <div
          style={{
            fontSize: 10,
            fontWeight: 700,
            textTransform: "uppercase",
            color: "#5e6c84",
            letterSpacing: ".04em",
            marginBottom: 3,
          }}
        >
          Follow-ups
        </div>
        {(topic.follow_up_items ?? []).length === 0 ? (
          <div style={{ fontSize: 13, color: "#97a0af", fontStyle: "italic" }}>(none)</div>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {(topic.follow_up_items ?? []).map((f, i) => (
              <li key={i} style={{ fontSize: 13, color: "#172b4d", lineHeight: 1.5 }}>
                {f}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div style={{ marginBottom: 10 }}>
        <div
          style={{
            fontSize: 10,
            fontWeight: 700,
            textTransform: "uppercase",
            color: "#5e6c84",
            letterSpacing: ".04em",
            marginBottom: 3,
          }}
        >
          Decisions
        </div>
        {(topic.decisions ?? []).length === 0 ? (
          <div style={{ fontSize: 13, color: "#97a0af", fontStyle: "italic" }}>(none)</div>
        ) : (
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {(topic.decisions ?? []).map((d, i) => (
              <li key={i} style={{ fontSize: 13, color: "#172b4d", lineHeight: 1.5 }}>
                {d}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {topic.status && (
          <span style={{ ...BADGE_BASE, ...(STATUS_BADGE[topic.status] ?? STATUS_BADGE.open) }}>
            {topic.status.replace("_", " ")}
          </span>
        )}
        {topic.owner && (
          <span style={{ ...BADGE_BASE, background: "#f4f5f7", color: "#5e6c84" }}>{topic.owner}</span>
        )}
        {topic.sentiment && (
          <span style={{ ...BADGE_BASE, background: "#f4f5f7", color: "#5e6c84" }}>
            {topic.sentiment}
          </span>
        )}
      </div>
    </div>
  );
}

export default function TopicEvidenceDrawer(props: Props) {
  const { open, onClose } = props;
  const isCallTopicMode = props.mode === "call_topic";
  const isMatchingMode = props.mode === "matching";
  const isLineageMode = !isCallTopicMode && !isMatchingMode;
  const topicId = isCallTopicMode
    ? null
    : isMatchingMode
    ? props.topicId
    : (props as Extract<Props, { mode?: "lineage" }>).topicId;
  const pendingTopic = isCallTopicMode
    ? props.pendingTopic
    : isMatchingMode
    ? props.pendingTopic
    : null;
  const matchingKind: MatchingKind | null = isMatchingMode ? props.kind : null;

  const [data, setData] = useState<TopicEvidence | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchEvidence = useCallback(async () => {
    // Fetch when we need a lineage for the left-column (lineage mode or
    // matching mode with a topicId). call_topic mode never fetches.
    if (!open || isCallTopicMode) return;
    if (!topicId) {
      // Matching mode with no existing topic (kind="new"): nothing to fetch.
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const result = await topicsAPI.getEvidence(topicId);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load evidence");
    } finally {
      setLoading(false);
    }
  }, [open, topicId, isCallTopicMode]);

  useEffect(() => {
    fetchEvidence();
  }, [fetchEvidence]);

  // Esc closes
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  if (isCallTopicMode && !pendingTopic) return null;
  if (isLineageMode && !topicId) return null;
  // Matching mode: need at least one side populated
  if (isMatchingMode && !topicId && !pendingTopic) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(23,43,77,0.4)",
        zIndex: 1000,
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        padding: "5vh 20px",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "white",
          borderRadius: 8,
          boxShadow: "0 16px 40px rgba(9,30,66,0.25)",
          width: "100%",
          maxWidth: isMatchingMode ? 1200 : 960,
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "14px 20px",
            borderBottom: "1px solid #dfe1e6",
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: 16,
            flexShrink: 0,
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2
              style={{
                fontSize: 18,
                fontWeight: 700,
                color: "#172b4d",
                margin: 0,
                lineHeight: 1.3,
              }}
            >
              {isCallTopicMode
                ? (pendingTopic?.name ?? "Topic source")
                : isMatchingMode
                ? (() => {
                    const existingName = data?.topic_name ?? null;
                    const pendingName = pendingTopic?.name ?? null;
                    if (existingName && pendingName) {
                      return `Match evidence: ${existingName} ↔ ${pendingName}`;
                    }
                    if (existingName) {
                      return `Match evidence: ${existingName}`;
                    }
                    if (pendingName) {
                      return `Match evidence: ${pendingName}`;
                    }
                    return loading ? "Loading…" : "Match evidence";
                  })()
                : (data?.topic_name ?? (loading ? "Loading…" : "Topic evidence"))}
            </h2>
            {(isLineageMode || isMatchingMode) && data && (
              <LineageChip lineage={data.lineage} currentTopicId={data.topic_id} />
            )}
            {isCallTopicMode && (
              <div style={{ fontSize: 11, color: "#5e6c84", marginTop: 6 }}>
                Source data from this call&apos;s extraction
              </div>
            )}
            {isMatchingMode && matchingKind && (
              <div style={{ fontSize: 11, color: "#5e6c84", marginTop: 6, textTransform: "uppercase", letterSpacing: ".04em", fontWeight: 700 }}>
                {matchingKind === "followed_up" && "Followed up"}
                {matchingKind === "new" && "New topic"}
                {matchingKind === "not_discussed" && "Not discussed"}
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              background: "none",
              border: "none",
              fontSize: 20,
              lineHeight: 1,
              color: "#5e6c84",
              cursor: "pointer",
              padding: "4px 8px",
              fontFamily: "inherit",
            }}
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px", background: "#f4f5f7" }}>
          {isCallTopicMode && pendingTopic && <PendingTopicCard topic={pendingTopic} />}
          {isLineageMode && loading && (
            <div style={{ fontSize: 13, color: "#5e6c84", textAlign: "center", padding: 40 }}>
              Loading evidence…
            </div>
          )}
          {isLineageMode && error && !loading && (
            <div
              style={{
                background: "#fff1f0",
                border: "1px solid #ffbdad",
                borderRadius: 6,
                padding: 14,
                fontSize: 12,
                color: "#ae2a19",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 12,
              }}
            >
              <span>{error}</span>
              <button
                onClick={fetchEvidence}
                style={{
                  fontSize: 12,
                  padding: "6px 12px",
                  borderRadius: 4,
                  border: "1px solid #ae2a19",
                  background: "white",
                  color: "#ae2a19",
                  cursor: "pointer",
                  fontFamily: "inherit",
                  fontWeight: 600,
                }}
              >
                Retry
              </button>
            </div>
          )}
          {isLineageMode && !loading && !error && data && data.calls.length === 0 && (
            <div style={{ fontSize: 13, color: "#5e6c84", textAlign: "center", padding: 40 }}>
              No evidence available for this topic.
            </div>
          )}
          {isLineageMode && !loading && !error && data && data.calls.length > 0 && (
            <div>
              {data.calls.map((c, i) => (
                <CallCard key={`${c.call_id}-${c.source_topic_id}-${i}`} call={c} index={i} currentTopicId={data.topic_id} />
              ))}
            </div>
          )}
          {isMatchingMode && (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                {/* LEFT — existing project topic's lineage */}
                <div style={{ minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      textTransform: "uppercase",
                      color: "#5e6c84",
                      letterSpacing: ".04em",
                      marginBottom: 8,
                    }}
                  >
                    Existing project topic
                  </div>
                  {!topicId ? (
                    <div
                      style={{
                        fontSize: 12,
                        color: "#5e6c84",
                        fontStyle: "italic",
                        background: "white",
                        border: "1px dashed #dfe1e6",
                        borderRadius: 6,
                        padding: 20,
                        textAlign: "center",
                      }}
                    >
                      No existing project topic matches this subject
                    </div>
                  ) : loading ? (
                    <div style={{ fontSize: 12, color: "#5e6c84", textAlign: "center", padding: 20 }}>
                      Loading evidence…
                    </div>
                  ) : error ? (
                    <div
                      style={{
                        background: "#fff1f0",
                        border: "1px solid #ffbdad",
                        borderRadius: 6,
                        padding: 12,
                        fontSize: 12,
                        color: "#ae2a19",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 10,
                      }}
                    >
                      <span>{error}</span>
                      <button
                        onClick={fetchEvidence}
                        style={{
                          fontSize: 12,
                          padding: "4px 10px",
                          borderRadius: 4,
                          border: "1px solid #ae2a19",
                          background: "white",
                          color: "#ae2a19",
                          cursor: "pointer",
                          fontFamily: "inherit",
                          fontWeight: 600,
                        }}
                      >
                        Retry
                      </button>
                    </div>
                  ) : data && data.calls.length === 0 ? (
                    <div style={{ fontSize: 12, color: "#5e6c84", textAlign: "center", padding: 20, fontStyle: "italic" }}>
                      No evidence available for this topic.
                    </div>
                  ) : data ? (
                    <div>
                      {data.calls.map((c, i) => (
                        <CallCard
                          key={`${c.call_id}-${c.source_topic_id}-${i}`}
                          call={c}
                          index={i}
                          currentTopicId={data.topic_id}
                        />
                      ))}
                    </div>
                  ) : null}
                </div>

                {/* RIGHT — current call's extraction */}
                <div style={{ minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      textTransform: "uppercase",
                      color: "#5e6c84",
                      letterSpacing: ".04em",
                      marginBottom: 8,
                    }}
                  >
                    This call&apos;s extraction
                  </div>
                  {pendingTopic ? (
                    <PendingTopicCard topic={pendingTopic} />
                  ) : (
                    <div
                      style={{
                        fontSize: 12,
                        color: "#5e6c84",
                        fontStyle: "italic",
                        background: "white",
                        border: "1px dashed #dfe1e6",
                        borderRadius: 6,
                        padding: 20,
                        textAlign: "center",
                      }}
                    >
                      Not extracted from this call
                    </div>
                  )}
                </div>
              </div>

              {/* Footer classification strip */}
              {matchingKind && (
                <div
                  style={{
                    marginTop: 16,
                    background: "white",
                    border: "1px solid #dfe1e6",
                    borderLeft: "4px solid #0052cc",
                    borderRadius: 6,
                    padding: "12px 14px",
                    fontSize: 12,
                    color: "#172b4d",
                    lineHeight: 1.5,
                  }}
                >
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: 700,
                      textTransform: "uppercase",
                      color: "#5e6c84",
                      letterSpacing: ".04em",
                      marginRight: 8,
                    }}
                  >
                    Why this classification:
                  </span>
                  {matchingKind === "followed_up" && (
                    <>
                      Matched because the same subject appears across{" "}
                      <strong>{data?.calls.length ?? 0}</strong> prior call
                      {(data?.calls.length ?? 0) === 1 ? "" : "s"}, and this call&apos;s extraction aligns with that subject.
                    </>
                  )}
                  {matchingKind === "new" && (
                    <>Marked new because no existing project topic matches the subject of this call&apos;s extraction.</>
                  )}
                  {matchingKind === "not_discussed" && (
                    <>Marked not-discussed because the LLM found no call topic on this subject in this call.</>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
