"use client";

import type { EvidenceTrailEntry, Call } from "@/types";

type Props = {
  entries: EvidenceTrailEntry[];
  callsById: Record<string, Pick<Call, "id" | "title" | "created_at">>;
};

export default function EvidenceTrail({ entries, callsById }: Props) {
  if (!entries || entries.length === 0) return null;

  const sortedCalls = Object.values(callsById).sort(
    (a, b) => (a.created_at ?? "").localeCompare(b.created_at ?? "")
  );

  return (
    <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid #dfe1e6" }}>
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: ".05em",
          color: "#5e6c84",
          marginBottom: 8,
        }}
      >
        Evidence trail (chronological)
      </div>
      {sortedCalls.map((call) => {
        const callEntries = entries.filter((e) => e.call_id === call.id);
        if (callEntries.length === 0) return null;
        return (
          <div key={call.id} style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#172b4d" }}>
              {call.title ?? "Untitled"} · {(call.created_at ?? "").slice(0, 10)}
            </div>
            {callEntries.map((e, i) => (
              <div
                key={`${call.id}-${i}`}
                id={`cit-${call.id}-${i}`}
                style={{
                  marginLeft: 12,
                  marginTop: 4,
                  fontSize: 12,
                  color: "#42526e",
                }}
              >
                <span style={{ color: "#7a869a", fontSize: 10 }}>
                  lines {e.citation.lines}
                </span>
                <div
                  style={{
                    fontStyle: "italic",
                    background: "#fafbfc",
                    padding: "4px 8px",
                    borderLeft: "2px solid #c1c7d0",
                    marginTop: 2,
                  }}
                >
                  &quot;{e.citation.quote}&quot;
                </div>
                <div style={{ color: "#0052cc", fontSize: 11, marginTop: 2 }}>
                  ↳ {e.action_label}
                </div>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}
