"use client";
import type { TopicWithCallHistory } from "@/types";

type Props = { topics: TopicWithCallHistory[] };

export default function ChronologyView({ topics }: Props) {
  // Collect unique calls across all topics, sorted by date
  const callMap = new Map<string, string>(); // call_id -> call_date
  for (const t of topics) {
    for (const c of t.calls) callMap.set(c.call_id, c.call_date);
  }
  const calls = Array.from(callMap.entries())
    .map(([id, date]) => ({ id, date }))
    .sort((a, b) => (a.date < b.date ? -1 : 1));

  if (topics.length === 0) {
    return <div style={{ color: "#5e6c84", fontSize: 13 }}>No topics yet.</div>;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", fontSize: 12, width: "100%" }}>
        <thead>
          <tr style={{ background: "#fafbfc", color: "#5e6c84", fontSize: 10, textTransform: "uppercase", letterSpacing: ".05em" }}>
            <th style={{ padding: "6px 8px", textAlign: "left", border: "1px solid #dfe1e6", minWidth: 180 }}>Topic</th>
            {calls.map((c) => (
              <th key={c.id} style={{ padding: "6px 8px", textAlign: "left", border: "1px solid #dfe1e6", minWidth: 240 }}>
                {c.date}
              </th>
            ))}
            <th style={{ padding: "6px 8px", textAlign: "left", border: "1px solid #dfe1e6", minWidth: 160 }}>RAG note</th>
          </tr>
        </thead>
        <tbody>
          {topics.map((t) => {
            const callsById = new Map(t.calls.map((c) => [c.call_id, c]));
            const latestRag = t.calls
              .map((c) => c.rag_verification_note)
              .filter((r): r is string => !!r && r !== "verified")
              .slice(-1)[0] ?? "";
            return (
              <tr key={t.id}>
                <td style={{ padding: "8px", border: "1px solid #dfe1e6", verticalAlign: "top", fontWeight: 600 }}>
                  {t.name}
                </td>
                {calls.map((c) => {
                  const tc = callsById.get(c.id);
                  return (
                    <td key={c.id} style={{ padding: "8px", border: "1px solid #dfe1e6", verticalAlign: "top", whiteSpace: "pre-wrap" }}>
                      {tc?.chronology_narrative ?? ""}
                    </td>
                  );
                })}
                <td style={{ padding: "8px", border: "1px solid #dfe1e6", verticalAlign: "top", fontSize: 11, color: latestRag ? "#bf2600" : "#5e6c84", whiteSpace: "pre-wrap" }}>
                  {latestRag || "verified"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
