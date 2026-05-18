"use client";

import { useState } from "react";
import type { EvidenceRef } from "@/types";

type Props = { evidence: EvidenceRef[] };

export default function EvidenceRefPopover({ evidence }: Props) {
  const [open, setOpen] = useState(false);

  const refs = evidence ?? [];
  if (refs.length === 0) {
    return <span style={{ color: "#c1c7d0", fontSize: 14 }} title="No evidence">📄</span>;
  }

  return (
    <span
      style={{ position: "relative", display: "inline-block", cursor: "help", fontSize: 14, color: "#7a869a" }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      📄
      {open && (
        <span
          role="tooltip"
          style={{
            position: "absolute",
            right: 0,
            top: 24,
            zIndex: 50,
            width: 460,
            background: "white",
            border: "1px solid #c1c7d0",
            borderRadius: 6,
            boxShadow: "0 6px 20px rgba(9,30,66,.16)",
            padding: "12px 14px",
            textAlign: "left",
            color: "#172b4d",
          }}
        >
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              color: "#5e6c84",
              textTransform: "uppercase",
              letterSpacing: ".05em",
              marginBottom: 8,
            }}
          >
            Evidence · {refs.length} reference{refs.length === 1 ? "" : "s"}
          </div>
          {refs.map((e, i) => (
            <div
              key={i}
              style={{
                padding: "8px 0",
                borderBottom: i < refs.length - 1 ? "1px solid #f1f2f4" : "none",
                ...(i === 0 ? { paddingTop: 0 } : {}),
                ...(i === refs.length - 1 ? { paddingBottom: 0 } : {}),
              }}
            >
              <div style={{ fontSize: 11, fontWeight: 600, color: "#172b4d", marginBottom: 2 }}>{e.speaker}</div>
              <div style={{ fontSize: 12, lineHeight: 1.5, fontStyle: "italic", color: "#172b4d" }}>
                &quot;{e.quote}&quot;
              </div>
              <div style={{ fontSize: 10, color: "#7a869a", marginTop: 4 }}>{e.citation}</div>
            </div>
          ))}
        </span>
      )}
    </span>
  );
}
