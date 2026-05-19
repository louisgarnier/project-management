"use client";
import type { TopicWithCallHistory } from "@/types";

type Props = { topics: TopicWithCallHistory[] };

export default function DashboardView({ topics }: Props) {
  let totalTasksOpen = 0;
  let totalTasksInProgress = 0;
  let totalTasksResolved = 0;
  let totalOQsOpen = 0;
  let totalDecisions = 0;

  for (const t of topics) {
    for (const c of t.calls) {
      for (const task of c.tasks) {
        if (task.status === "open") totalTasksOpen++;
        else if (task.status === "in_progress") totalTasksInProgress++;
        else if (task.status === "resolved") totalTasksResolved++;
      }
      for (const q of c.open_questions) {
        if (q.status !== "resolved") totalOQsOpen++;
      }
      totalDecisions += c.decisions.length;
    }
  }

  const rows = [
    { label: "Total topics", value: topics.length },
    { label: "Open tasks", value: totalTasksOpen },
    { label: "In-progress tasks", value: totalTasksInProgress },
    { label: "Resolved tasks", value: totalTasksResolved },
    { label: "Open questions still open", value: totalOQsOpen },
    { label: "Total decisions", value: totalDecisions },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <table style={{ borderCollapse: "collapse", fontSize: 13, width: "fit-content" }}>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <td style={{ padding: "8px 16px", color: "#42526e" }}>{r.label}</td>
              <td style={{ padding: "8px 16px", fontWeight: 700, color: "#172b4d" }}>{r.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
