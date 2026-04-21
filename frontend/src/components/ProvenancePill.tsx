"use client";

import { callColor } from "@/utils/callColors";

// Compact pill rendering the originating call for a single follow-up or
// decision item. `callIndex` is 0-based (cycles palette); displayed label is
// 1-based for user readability ("C1", "C2", ...). When callIndex is null we
// render a muted "?" fallback indicating the item couldn't be matched against
// the topic's history (usually LLM rewording).
type Props = {
  callIndex: number | null;
  callTitle: string | null;
};

export default function ProvenancePill({ callIndex, callTitle }: Props) {
  if (callIndex === null || callTitle === null) {
    return (
      <span
        title="Origin call not found in this topic's history (item may have been reworded during merge)"
        style={{
          display: "inline-block",
          minWidth: 18,
          textAlign: "center",
          fontSize: 9,
          fontWeight: 700,
          padding: "2px 5px",
          borderRadius: 3,
          background: "#e5e7eb",
          color: "#97a0af",
          cursor: "help",
          flexShrink: 0,
          marginTop: 2,
        }}
      >
        ?
      </span>
    );
  }
  const { bg, text } = callColor(callIndex);
  const label = `C${callIndex + 1}`;
  return (
    <span
      title={callTitle}
      style={{
        display: "inline-block",
        minWidth: 18,
        textAlign: "center",
        fontSize: 9,
        fontWeight: 700,
        padding: "2px 5px",
        borderRadius: 3,
        background: bg,
        color: text,
        cursor: "help",
        flexShrink: 0,
        marginTop: 2,
      }}
    >
      {label}
    </span>
  );
}
