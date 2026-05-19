"use client";
import type { TopicWithCallHistory } from "@/types";

type Props = { topics: TopicWithCallHistory[] };

export default function KeyTermsRegistryView({ topics }: Props) {
  type Row = { topic: string; term: string; first_seen: string };
  const rows: Row[] = [];
  for (const t of topics) {
    const firstCall = [...t.calls].sort((a, b) => (a.call_date < b.call_date ? -1 : 1))[0];
    const firstDate = firstCall?.call_date ?? "";
    for (const kt of t.key_terms) {
      rows.push({ topic: t.name, term: kt, first_seen: firstDate });
    }
  }

  if (rows.length === 0) {
    return <div style={{ color: "#5e6c84", fontSize: 13 }}>No key terms yet.</div>;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", fontSize: 12, width: "100%" }}>
        <thead>
          <tr style={{ background: "#fafbfc", color: "#5e6c84", fontSize: 10, textTransform: "uppercase", letterSpacing: ".05em" }}>
            <th style={{ padding: "6px 8px", textAlign: "left", border: "1px solid #dfe1e6" }}>Topic</th>
            <th style={{ padding: "6px 8px", textAlign: "left", border: "1px solid #dfe1e6" }}>Key term</th>
            <th style={{ padding: "6px 8px", textAlign: "left", border: "1px solid #dfe1e6" }}>First seen</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td style={{ padding: "8px", border: "1px solid #dfe1e6", fontWeight: 600 }}>{r.topic}</td>
              <td style={{ padding: "8px", border: "1px solid #dfe1e6" }}>{r.term}</td>
              <td style={{ padding: "8px", border: "1px solid #dfe1e6", color: "#5e6c84" }}>{r.first_seen}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
