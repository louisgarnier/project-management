"use client";

// Shared read-only rendering of the EPIC-20 task_grouping output for a call.
// Used by both ProjectMatchingHistoricalView + ProjectUpdatesHistoricalView so
// past-stage cards show the actual committed shape (group → topic → tasks),
// not the pre-EPIC-20 New/Updated/Not-Discussed buckets.

import { useEffect, useState } from "react";
import { taskGroupingAPI, type GroupingGroup, type GroupingTask, type GroupingTopic } from "@/api/client";
import { logger } from "@/utils/logger";

type Props = {
  callId: string;
  /** Title shown in the read-only banner */
  bannerText?: string;
};

const KIND_LABEL: Record<GroupingGroup["group_kind"], string> = {
  new_only: "NEW",
  old_only: "OLD",
  mixed: "MIXED",
};

const KIND_COLORS: Record<GroupingGroup["group_kind"], { bg: string; border: string; text: string }> = {
  new_only: { bg: "#e9f0ff", border: "#4c9aff", text: "#0747a6" },
  old_only: { bg: "#f4f5f7", border: "#97a0af", text: "#42526e" },
  mixed:    { bg: "#fce4fa", border: "#cc57c5", text: "#6b2066" },
};

export default function TaskGroupsReadOnly({ callId, bannerText }: Props) {
  const [topics, setTopics] = useState<GroupingTopic[]>([]);
  const [tasks, setTasks] = useState<GroupingTask[]>([]);
  const [groups, setGroups] = useState<GroupingGroup[]>([]);
  const [orphans, setOrphans] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    taskGroupingAPI
      .state(callId)
      .then((d) => {
        if (!alive) return;
        setTopics(d.topics);
        setTasks(d.tasks);
        setGroups(d.groups);
        setOrphans(d.orphans);
      })
      .catch((e) => {
        if (!alive) return;
        logger.error("[TaskGroupsReadOnly] load failed", { component: "TaskGroupsReadOnly", data: e });
        setError(e instanceof Error ? e.message : "Failed to load");
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [callId]);

  const topicById = new Map(topics.map((t) => [t.id, t.name]));
  const taskById = new Map(tasks.map((t) => [t.id, t]));

  if (loading) {
    return <div style={{ padding: 24, fontSize: 13, color: "#5e6c84" }}>Loading task groups…</div>;
  }
  if (error) {
    return <div style={{ padding: 24, fontSize: 13, color: "#ae2a19" }}>{error}</div>;
  }
  if (groups.length === 0 && tasks.length === 0) {
    return <div style={{ padding: 24, fontSize: 13, color: "#5e6c84" }}>No task grouping data yet.</div>;
  }

  // Group by group_kind for display grouping
  const orderedGroups = [...groups].sort((a, b) => {
    const order = { new_only: 0, mixed: 1, old_only: 2 };
    return (order[a.group_kind] ?? 99) - (order[b.group_kind] ?? 99);
  });

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {bannerText && (
        <div style={{ padding: "12px 20px", flexShrink: 0 }}>
          <div style={{
            background: "#f4f5f7",
            border: "1px solid #dfe1e6",
            borderRadius: 6,
            padding: "8px 12px",
            fontSize: 12,
            color: "#5e6c84",
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}>
            <span style={{ fontSize: 14 }}>🔒</span>
            <span>{bannerText}</span>
          </div>
        </div>
      )}
      <div style={{ flex: 1, overflowY: "auto", padding: "0 20px 20px" }}>
        {orderedGroups.map((g, gi) => {
          const c = KIND_COLORS[g.group_kind];
          const topicName = topicById.get(g.finalized_topic_id) || "(unknown topic)";
          const groupName = (g.name || "").trim() || topicName;
          return (
            <div
              key={g.id || `g-${gi}`}
              style={{
                marginBottom: 14,
                border: `1.5px solid ${c.border}`,
                borderRadius: 8,
                overflow: "hidden",
                background: "white",
              }}
            >
              <div style={{
                padding: "8px 14px",
                background: c.bg,
                borderBottom: `1px solid ${c.border}`,
                display: "flex",
                alignItems: "center",
                gap: 8,
                flexWrap: "wrap",
              }}>
                <span style={{
                  fontSize: 9,
                  fontWeight: 800,
                  padding: "2px 6px",
                  borderRadius: 3,
                  background: c.border,
                  color: "#fff",
                  letterSpacing: ".06em",
                }}>
                  {KIND_LABEL[g.group_kind]}
                </span>
                <span style={{ fontSize: 13, fontWeight: 700, color: "#172b4d" }}>
                  {groupName}
                </span>
                {groupName !== topicName && (
                  <span style={{ fontSize: 11, color: c.text }}>
                    → topic: <b>{topicName}</b>
                  </span>
                )}
                <span style={{ marginLeft: "auto", fontSize: 10, color: c.text, fontWeight: 600 }}>
                  {g.task_ids.length} task{g.task_ids.length === 1 ? "" : "s"}
                </span>
              </div>
              <div style={{ padding: "8px 14px" }}>
                {g.task_ids.length === 0 ? (
                  <div style={{ fontSize: 11, color: "#97a0af", fontStyle: "italic" }}>No tasks in this group.</div>
                ) : (
                  g.task_ids.map((tid) => {
                    const t = taskById.get(tid);
                    if (!t) {
                      return (
                        <div key={tid} style={{ fontSize: 11, color: "#97a0af", padding: "3px 0" }}>
                          <span style={{ fontFamily: "monospace" }}>{tid}</span> (task data missing)
                        </div>
                      );
                    }
                    return (
                      <div
                        key={tid}
                        style={{
                          fontSize: 12,
                          color: "#172b4d",
                          padding: "4px 0",
                          borderBottom: "1px solid #f0f1f3",
                          display: "flex",
                          gap: 8,
                          alignItems: "baseline",
                        }}
                      >
                        <span style={{
                          fontSize: 9,
                          fontWeight: 700,
                          padding: "1px 5px",
                          borderRadius: 2,
                          background: t.origin === "new" ? "#deebff" : "#f4f5f7",
                          color: t.origin === "new" ? "#0747a6" : "#5e6c84",
                          flexShrink: 0,
                        }}>
                          {t.origin === "new" ? "N" : "P"}
                        </span>
                        <span style={{ flex: 1 }}>{t.text}</span>
                        {t.topic_name && t.topic_name !== topicName && (
                          <span style={{ fontSize: 10, color: "#5e6c84", fontStyle: "italic", flexShrink: 0 }}>
                            from: {t.topic_name}
                          </span>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          );
        })}

        {orphans.length > 0 && (
          <div style={{
            marginTop: 8,
            border: "1.5px dashed #c1c7d0",
            borderRadius: 8,
            padding: "10px 14px",
            background: "#fafbfc",
          }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#97a0af", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 6 }}>
              Ungrouped ({orphans.length})
            </div>
            {orphans.map((tid) => {
              const t = taskById.get(tid);
              return (
                <div key={tid} style={{ fontSize: 11, color: "#5e6c84", padding: "2px 0" }}>
                  • {t ? t.text : tid}
                  {t && <span style={{ fontStyle: "italic", marginLeft: 6 }}>from: {t.topic_name}</span>}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
