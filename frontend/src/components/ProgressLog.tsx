"use client";

import { useEffect, useRef } from "react";

export type ProgressEntry = {
  ts: string;
  msg: string;
};

type Props = {
  entries: ProgressEntry[];
  active: boolean;  // true while the pass is still processing (shows live indicator)
};

export default function ProgressLog({ entries, active }: Props) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to the latest entry as new ones arrive
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [entries.length]);

  if (!entries || entries.length === 0) {
    if (active) {
      return (
        <div style={containerStyle}>
          <div style={{ ...rowStyle, color: "#5e6c84", fontStyle: "italic" }}>
            Starting…
          </div>
        </div>
      );
    }
    return null;
  }

  return (
    <div style={containerStyle}>
      {entries.map((e, i) => (
        <div key={i} style={rowStyle}>
          <span style={tsStyle}>{e.ts.slice(11, 19)}</span>
          <span style={msgStyle}>{e.msg}</span>
        </div>
      ))}
      {active && (
        <div style={{ ...rowStyle, color: "#5e6c84", fontStyle: "italic" }}>
          <span style={tsStyle}>•••</span>
          <span style={msgStyle}>working…</span>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
}

const containerStyle: React.CSSProperties = {
  marginTop: 8,
  marginBottom: 12,
  padding: "8px 10px",
  background: "#fafbfc",
  border: "1px solid #dfe1e6",
  borderRadius: 4,
  fontSize: 11,
  fontFamily: "ui-monospace, Menlo, monospace",
  color: "#42526e",
  maxHeight: 200,
  overflowY: "auto",
};

const rowStyle: React.CSSProperties = {
  display: "flex",
  gap: 8,
  padding: "2px 0",
  lineHeight: 1.4,
};

const tsStyle: React.CSSProperties = {
  color: "#97a0af",
  flexShrink: 0,
  fontSize: 10,
};

const msgStyle: React.CSSProperties = {
  flex: 1,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};
