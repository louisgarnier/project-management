"use client";
import type { TopicWithCallHistory } from "@/types";

type Props = { topics: TopicWithCallHistory[] };

const STATUS_BG: Record<string, string> = { open: "#e9f0ff", in_progress: "#fff4e6", resolved: "#e3fcef" };
const STATUS_FG: Record<string, string> = { open: "#0052cc", in_progress: "#974f0c", resolved: "#006644" };

export default function AnchorsLifecycleView({ topics }: Props) {
  // De-dupe items across calls: each task_id / oq.id only appears once with its most recent state
  type Row = { topic: string; kind: string; item: string; owner: string; status: string; added_in: string; closed_in: string };
  const rows: Row[] = [];
  const seen = new Set<string>();

  // call_id -> call_date lookup
  const callDate = new Map<string, string>();
  for (const t of topics) for (const c of t.calls) callDate.set(c.call_id, c.call_date);

  for (const t of topics) {
    // Walk calls in chronological order; later updates overwrite earlier rows for the same item id
    const sortedCalls = [...t.calls].sort((a, b) => (a.call_date < b.call_date ? -1 : 1));
    for (const c of sortedCalls) {
      for (const task of c.tasks) {
        const key = `task::${task.task_id || task.task}`;
        if (seen.has(key)) {
          // Update the existing row in place
          const r = rows.find((x) => x.topic === t.name && x.kind === "task" && x.item === task.task);
          if (r) {
            r.status = task.status;
            r.closed_in = task.closed_in_call_id ? callDate.get(task.closed_in_call_id) ?? "" : "";
          }
          continue;
        }
        seen.add(key);
        rows.push({
          topic: t.name,
          kind: "task",
          item: task.task,
          owner: task.owner || "",
          status: task.status,
          added_in: task.added_in_call_id ? callDate.get(task.added_in_call_id) ?? "" : "",
          closed_in: task.closed_in_call_id ? callDate.get(task.closed_in_call_id) ?? "" : "",
        });
      }
      for (const q of c.open_questions) {
        const key = `oq::${q.id || q.text}`;
        if (seen.has(key)) {
          const r = rows.find((x) => x.topic === t.name && x.kind === "open_question" && x.item === q.text);
          if (r) {
            r.status = q.status;
            r.closed_in = q.closed_in_call_id ? callDate.get(q.closed_in_call_id) ?? "" : "";
          }
          continue;
        }
        seen.add(key);
        rows.push({
          topic: t.name,
          kind: "open_question",
          item: q.text,
          owner: q.owner || "",
          status: q.status,
          added_in: q.added_in_call_id ? callDate.get(q.added_in_call_id) ?? "" : "",
          closed_in: q.closed_in_call_id ? callDate.get(q.closed_in_call_id) ?? "" : "",
        });
      }
    }
  }

  if (rows.length === 0) {
    return <div style={{ color: "#5e6c84", fontSize: 13 }}>No items yet.</div>;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", fontSize: 12, width: "100%" }}>
        <thead>
          <tr style={{ background: "#fafbfc", color: "#5e6c84", fontSize: 10, textTransform: "uppercase", letterSpacing: ".05em" }}>
            <th style={{ padding: "6px 8px", textAlign: "left", border: "1px solid #dfe1e6" }}>Topic</th>
            <th style={{ padding: "6px 8px", textAlign: "left", border: "1px solid #dfe1e6" }}>Kind</th>
            <th style={{ padding: "6px 8px", textAlign: "left", border: "1px solid #dfe1e6" }}>Item</th>
            <th style={{ padding: "6px 8px", textAlign: "left", border: "1px solid #dfe1e6" }}>Owner</th>
            <th style={{ padding: "6px 8px", textAlign: "left", border: "1px solid #dfe1e6" }}>Status</th>
            <th style={{ padding: "6px 8px", textAlign: "left", border: "1px solid #dfe1e6" }}>Added in</th>
            <th style={{ padding: "6px 8px", textAlign: "left", border: "1px solid #dfe1e6" }}>Closed in</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td style={{ padding: "8px", border: "1px solid #dfe1e6", fontWeight: 600 }}>{r.topic}</td>
              <td style={{ padding: "8px", border: "1px solid #dfe1e6", color: "#5e6c84" }}>{r.kind}</td>
              <td style={{ padding: "8px", border: "1px solid #dfe1e6" }}>{r.item}</td>
              <td style={{ padding: "8px", border: "1px solid #dfe1e6" }}>{r.owner}</td>
              <td style={{ padding: "8px", border: "1px solid #dfe1e6" }}>
                <span style={{
                  fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                  padding: "3px 7px", borderRadius: 3,
                  background: STATUS_BG[r.status] ?? "#f4f5f7",
                  color: STATUS_FG[r.status] ?? "#5e6c84",
                }}>
                  {r.status}
                </span>
              </td>
              <td style={{ padding: "8px", border: "1px solid #dfe1e6", color: "#5e6c84" }}>{r.added_in}</td>
              <td style={{ padding: "8px", border: "1px solid #dfe1e6", color: r.closed_in ? "#006644" : "#5e6c84" }}>{r.closed_in || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
