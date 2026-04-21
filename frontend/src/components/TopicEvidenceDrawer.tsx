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
} from "@/types";

type Props = {
  open: boolean;
  topicId: string | null;
  onClose: () => void;
};

// 8-color pastel palette — one band per call, cycled by index
const CALL_COLORS = [
  "#dfe7ff", // blue
  "#daf5e4", // green
  "#fff7d6", // yellow
  "#ffe0d3", // orange
  "#f0d3ff", // purple
  "#d3f0ff", // cyan
  "#ffd3e6", // pink
  "#e8e8e8", // gray
];

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
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {call.follow_up_items.map((f, i) => (
                <li key={i} style={{ fontSize: 12, color: "#172b4d", lineHeight: 1.5 }}>{f}</li>
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
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {call.decisions.map((d, i) => (
                <li key={i} style={{ fontSize: 12, color: "#172b4d", lineHeight: 1.5 }}>{d}</li>
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

export default function TopicEvidenceDrawer({ open, topicId, onClose }: Props) {
  const [data, setData] = useState<TopicEvidence | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchEvidence = useCallback(async () => {
    if (!open || !topicId) return;
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
  }, [open, topicId]);

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

  if (!open || !topicId) return null;

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
          maxWidth: 960,
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
              {data?.topic_name ?? (loading ? "Loading…" : "Topic evidence")}
            </h2>
            {data && <LineageChip lineage={data.lineage} currentTopicId={data.topic_id} />}
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
          {loading && (
            <div style={{ fontSize: 13, color: "#5e6c84", textAlign: "center", padding: 40 }}>
              Loading evidence…
            </div>
          )}
          {error && !loading && (
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
          {!loading && !error && data && data.calls.length === 0 && (
            <div style={{ fontSize: 13, color: "#5e6c84", textAlign: "center", padding: 40 }}>
              No evidence available for this topic.
            </div>
          )}
          {!loading && !error && data && data.calls.length > 0 && (
            <div>
              {data.calls.map((c, i) => (
                <CallCard key={`${c.call_id}-${c.source_topic_id}-${i}`} call={c} index={i} currentTopicId={data.topic_id} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
