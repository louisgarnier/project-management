"use client";
import type { TopicWithCallHistory } from "@/types";

type Props = { topics: TopicWithCallHistory[] };

export default function DecisionsLogView({ topics }: Props) {
  type Row = { topic: string; text: string; decided_in: string };
  const rows: Row[] = [];
  const seen = new Set<string>();
  for (const t of topics) {
    for (const c of t.calls) {
      for (const d of c.decisions) {
        const key = `${d.id || d.text}::${t.name}`;
        if (seen.has(key)) continue;
        seen.add(key);
        rows.push({ topic: t.name, text: d.text, decided_in: c.call_date });
      }
    }
  }

  if (rows.length === 0) {
    return <div style={{ color: "#5e6c84", fontSize: 13 }}>No decisions yet.</div>;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", fontSize: 12, width: "100%" }}>
        <thead>
          <tr style={{ background: "#fafbfc", color: "#5e6c84", fontSize: 10, textTransform: "uppercase", letterSpacing: ".05em" }}>
            <th style={{ padding: "6px 8px", textAlign: "left", border: "1px solid #dfe1e6", minWidth: 180 }}>Topic</th>
            <th style={{ padding: "6px 8px", textAlign: "left", border: "1px solid #dfe1e6", minWidth: 480 }}>Decision</th>
            <th style={{ padding: "6px 8px", textAlign: "left", border: "1px solid #dfe1e6", minWidth: 100 }}>Decided in</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td style={{ padding: "8px", border: "1px solid #dfe1e6", fontWeight: 600 }}>{r.topic}</td>
              <td style={{ padding: "8px", border: "1px solid #dfe1e6", whiteSpace: "pre-wrap" }}>{r.text}</td>
              <td style={{ padding: "8px", border: "1px solid #dfe1e6", color: "#5e6c84" }}>{r.decided_in}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
