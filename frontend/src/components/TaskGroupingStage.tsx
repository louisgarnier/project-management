"use client";

// EPIC-20 Stage 2: Task grouping.
// Drag tasks between groups, drag groups between topics, orphans must be placed
// before advancing. LLM "Re-cluster" runs a fresh cluster+route pass.

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  taskGroupingAPI,
  type GroupingGroup,
  type GroupingTask,
  type GroupingTopic,
} from "@/api/client";
import { logger } from "@/utils/logger";

type Props = { callId: string; onAdvance: () => void };

// Color palette per group (cycled by index)
const GROUP_COLORS = [
  { bg: "#d4f0d4", border: "#197d23", text: "#0c5c14" },
  { bg: "#cce5ff", border: "#0747a6", text: "#063572" },
  { bg: "#ffe5b3", border: "#974f0c", text: "#5e3204" },
  { bg: "#ffd6cc", border: "#cc5500", text: "#7a2200" },
  { bg: "#e0d4f7", border: "#5e3da8", text: "#3c1f7e" },
  { bg: "#fff3cd", border: "#856404", text: "#5e4503" },
];
const colorOf = (i: number) => GROUP_COLORS[i % GROUP_COLORS.length];

const KIND_LABEL: Record<GroupingGroup["group_kind"], string> = {
  new_only: "NEW → Pass 1",
  old_only: "OLD → Pass 2",
  mixed: "MIXED → Pass 3",
};

function inferKind(taskIds: string[]): GroupingGroup["group_kind"] {
  const hasNew = taskIds.some((id) => id.startsWith("new:"));
  const hasPrev = taskIds.some((id) => id.startsWith("prev:"));
  if (hasNew && hasPrev) return "mixed";
  if (hasPrev) return "old_only";
  return "new_only";
}

export default function TaskGroupingStage({ callId, onAdvance }: Props) {
  const [topics, setTopics] = useState<GroupingTopic[]>([]);
  const [tasks, setTasks] = useState<GroupingTask[]>([]);
  const [groups, setGroups] = useState<GroupingGroup[]>([]);
  const [orphans, setOrphans] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"run" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragTaskId, setDragTaskId] = useState<string | null>(null);
  const [dragGroupId, setDragGroupId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await taskGroupingAPI.state(callId);
      setTopics(d.topics);
      setTasks(d.tasks);
      setGroups(d.groups);
      setOrphans(d.orphans);
    } catch (e) {
      logger.error("TaskGrouping state load failed", { component: "TaskGroupingStage", data: e });
      setError(e instanceof Error ? e.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }, [callId]);

  useEffect(() => {
    reload();
  }, [reload]);

  const tasksById = useMemo(() => {
    const m = new Map<string, GroupingTask>();
    for (const t of tasks) m.set(t.id, t);
    return m;
  }, [tasks]);

  const groupsByTopic = useMemo(() => {
    const m = new Map<string, GroupingGroup[]>();
    for (const t of topics) m.set(t.id, []);
    for (const g of groups) {
      const arr = m.get(g.finalized_topic_id);
      if (arr) arr.push(g);
    }
    return m;
  }, [topics, groups]);

  // ── Mutations ──────────────────────────────────────────────────────────────

  const mutateGroups = (updater: (gs: GroupingGroup[]) => GroupingGroup[]) => {
    setGroups((gs) => {
      const next = updater(gs)
        // Drop empties
        .filter((g) => g.task_ids.length > 0)
        // Refresh kind from current task_ids
        .map((g) => ({ ...g, group_kind: inferKind(g.task_ids) }));
      // Recompute orphans
      const placed = new Set<string>();
      for (const g of next) for (const tid of g.task_ids) placed.add(tid);
      setOrphans(tasks.map((t) => t.id).filter((id) => !placed.has(id)));
      return next;
    });
  };

  const moveTaskToGroup = (taskId: string, targetGroupId: string) => {
    mutateGroups((gs) =>
      gs
        .map((g) => ({ ...g, task_ids: g.task_ids.filter((tid) => tid !== taskId) }))
        .map((g) => (g.id === targetGroupId ? { ...g, task_ids: [...g.task_ids, taskId] } : g)),
    );
  };

  const moveTaskToNewGroupUnderTopic = (taskId: string, topicId: string) => {
    const newId = `local-${crypto.randomUUID()}`;
    mutateGroups((gs) => [
      ...gs.map((g) => ({ ...g, task_ids: g.task_ids.filter((tid) => tid !== taskId) })),
      { id: newId, finalized_topic_id: topicId, group_kind: "new_only", task_ids: [taskId] },
    ]);
  };

  const moveGroupToTopic = (groupId: string, topicId: string) => {
    mutateGroups((gs) => gs.map((g) => (g.id === groupId ? { ...g, finalized_topic_id: topicId } : g)));
  };

  // ── Drag handlers ──────────────────────────────────────────────────────────

  const onTaskDragStart = (e: React.DragEvent, taskId: string) => {
    setDragTaskId(taskId);
    setDragGroupId(null);
    e.dataTransfer.setData("text/plain", `task:${taskId}`);
    e.dataTransfer.effectAllowed = "move";
  };

  const onGroupDragStart = (e: React.DragEvent, groupId: string) => {
    setDragGroupId(groupId);
    setDragTaskId(null);
    e.dataTransfer.setData("text/plain", `group:${groupId}`);
    e.dataTransfer.effectAllowed = "move";
  };

  const onDragEnd = () => {
    setDragTaskId(null);
    setDragGroupId(null);
  };

  const handleDropOnGroup = (e: React.DragEvent, groupId: string) => {
    e.preventDefault();
    e.stopPropagation();
    const payload = e.dataTransfer.getData("text/plain");
    if (payload.startsWith("task:")) {
      moveTaskToGroup(payload.slice(5), groupId);
    }
    onDragEnd();
  };

  const handleDropOnTopic = (e: React.DragEvent, topicId: string) => {
    e.preventDefault();
    const payload = e.dataTransfer.getData("text/plain");
    if (payload.startsWith("group:")) {
      moveGroupToTopic(payload.slice(6), topicId);
    } else if (payload.startsWith("task:")) {
      moveTaskToNewGroupUnderTopic(payload.slice(5), topicId);
    }
    onDragEnd();
  };

  // ── Actions ────────────────────────────────────────────────────────────────

  const runLLM = async () => {
    if (!window.confirm("Re-cluster will overwrite the current groups with an LLM proposal. Continue?")) return;
    setBusy("run");
    setError(null);
    try {
      await taskGroupingAPI.run(callId);
      await reload();
    } catch (e) {
      logger.error("TaskGrouping LLM run failed", { component: "TaskGroupingStage", data: e });
      setError(e instanceof Error ? e.message : "Re-cluster failed");
    } finally {
      setBusy(null);
    }
  };

  const save = async () => {
    if (orphans.length > 0) {
      setError(`${orphans.length} task(s) still ungrouped — place all before advancing.`);
      return;
    }
    setBusy("save");
    setError(null);
    try {
      const out = await taskGroupingAPI.save(callId, groups);
      if (out.advanced) onAdvance();
      else await reload();
    } catch (e) {
      logger.error("TaskGrouping save failed", { component: "TaskGroupingStage", data: e });
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(null);
    }
  };

  // Debounced auto-save on group changes (draft, no advancement)
  useEffect(() => {
    if (loading || busy) return;
    const t = setTimeout(() => {
      taskGroupingAPI.save(callId, groups).catch(() => {});
    }, 800);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groups]);

  // ── Render ────────────────────────────────────────────────────────────────

  if (loading) return <div style={{ padding: 24 }}>Loading groups…</div>;

  return (
    <div style={{ padding: 16, maxWidth: 1600, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Task grouping</h2>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={runLLM} disabled={busy !== null} style={btnSecondary}>
            {busy === "run" ? "Clustering…" : "🤖 Re-cluster (LLM)"}
          </button>
          <button
            onClick={save}
            disabled={busy !== null || orphans.length > 0}
            style={{
              ...btnPrimary,
              opacity: busy !== null || orphans.length > 0 ? 0.5 : 1,
              cursor: busy !== null || orphans.length > 0 ? "not-allowed" : "pointer",
            }}
          >
            {busy === "save"
              ? "Saving…"
              : orphans.length > 0
                ? `${orphans.length} orphan${orphans.length === 1 ? "" : "s"} — place to advance`
                : `Save & advance to Project Updates`}
          </button>
        </div>
      </div>

      {error && (
        <div style={errorBox}>{error}</div>
      )}

      {/* Orphan bin */}
      {orphans.length > 0 && (
        <div style={orphanBox}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6, color: "#856404" }}>
            UNGROUPED ({orphans.length}) — drag onto a group or topic column
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {orphans.map((tid) => {
              const t = tasksById.get(tid);
              if (!t) return null;
              return (
                <TaskPill
                  key={tid}
                  task={t}
                  onDragStart={(e) => onTaskDragStart(e, tid)}
                  onDragEnd={onDragEnd}
                />
              );
            })}
          </div>
        </div>
      )}

      {/* Topic columns */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${Math.max(topics.length, 1)}, minmax(220px, 1fr))`,
          gap: 12,
          marginTop: 12,
        }}
      >
        {topics.map((t) => {
          const tgs = groupsByTopic.get(t.id) ?? [];
          const isDropHere = !!(dragTaskId || dragGroupId);
          return (
            <div
              key={t.id}
              onDragOver={(e) => {
                if (!isDropHere) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
              }}
              onDrop={(e) => handleDropOnTopic(e, t.id)}
              style={{
                background: "#f7f8fa",
                border: "1px solid #e1e4e8",
                borderRadius: 6,
                padding: 10,
                minHeight: 220,
              }}
            >
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#172b4d" }}>{t.name}</div>
                <div style={{ fontSize: 11, color: "#5e6c84" }}>
                  {tgs.length} group{tgs.length === 1 ? "" : "s"}
                </div>
              </div>
              {tgs.map((g, idx) => {
                // Color group by global index for stable colors across topic moves
                const globalIdx = groups.findIndex((x) => x === g);
                const col = colorOf(globalIdx >= 0 ? globalIdx : idx);
                return (
                  <GroupCard
                    key={g.id ?? `${t.id}-${idx}`}
                    group={g}
                    color={col}
                    tasksById={tasksById}
                    onTaskDragStart={onTaskDragStart}
                    onGroupDragStart={onGroupDragStart}
                    onDrop={handleDropOnGroup}
                    onDragEnd={onDragEnd}
                  />
                );
              })}
              {tgs.length === 0 && (
                <div style={{ color: "#5e6c84", fontSize: 12, fontStyle: "italic", padding: 8 }}>
                  Drop a group or task here.
                </div>
              )}
            </div>
          );
        })}
      </div>

      {topics.length === 0 && (
        <div style={{ padding: 24, color: "#5e6c84" }}>
          No finalized topics — complete Stage 1 (Topic Confirmation) first.
        </div>
      )}
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────────────────────

function GroupCard({
  group,
  color,
  tasksById,
  onTaskDragStart,
  onGroupDragStart,
  onDrop,
  onDragEnd,
}: {
  group: GroupingGroup;
  color: { bg: string; border: string; text: string };
  tasksById: Map<string, GroupingTask>;
  onTaskDragStart: (e: React.DragEvent, taskId: string) => void;
  onGroupDragStart: (e: React.DragEvent, groupId: string) => void;
  onDrop: (e: React.DragEvent, groupId: string) => void;
  onDragEnd: () => void;
}) {
  const gid = group.id ?? "";
  return (
    <div
      draggable={!!gid}
      onDragStart={(e) => gid && onGroupDragStart(e, gid)}
      onDragEnd={onDragEnd}
      onDragOver={(e) => {
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = "move";
      }}
      onDrop={(e) => gid && onDrop(e, gid)}
      style={{
        background: color.bg,
        borderLeft: `3px solid ${color.border}`,
        padding: 6,
        marginBottom: 6,
        borderRadius: 3,
        cursor: gid ? "grab" : "default",
      }}
      title="Drag this group to another topic column"
    >
      <div style={{ fontSize: 10, fontWeight: 700, color: color.text, marginBottom: 4 }}>
        {KIND_LABEL[group.group_kind]} · {group.task_ids.length} task
        {group.task_ids.length === 1 ? "" : "s"}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
        {group.task_ids.map((tid) => {
          const t = tasksById.get(tid);
          if (!t) return null;
          return (
            <TaskPill
              key={tid}
              task={t}
              onDragStart={(e) => onTaskDragStart(e, tid)}
              onDragEnd={onDragEnd}
            />
          );
        })}
      </div>
    </div>
  );
}

function TaskPill({
  task,
  onDragStart,
  onDragEnd,
}: {
  task: GroupingTask;
  onDragStart: (e: React.DragEvent) => void;
  onDragEnd: () => void;
}) {
  const bg = task.origin === "new" ? "#cce5ff" : "#e0e0e0";
  const fg = task.origin === "new" ? "#063572" : "#444";
  const txt = task.text || "(empty)";
  const short = txt.length > 70 ? txt.slice(0, 67) + "…" : txt;
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      title={task.text}
      style={{
        background: bg,
        color: fg,
        padding: "2px 8px",
        borderRadius: 10,
        fontSize: 11,
        cursor: "grab",
        userSelect: "none",
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
        maxWidth: 220,
      }}
    >
      <span style={{ fontWeight: 700, marginRight: 4, opacity: 0.7 }}>
        {task.origin === "new" ? "N" : "P"}
      </span>
      {short}
    </div>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────────

const btnPrimary: React.CSSProperties = {
  background: "#0747a6",
  color: "#fff",
  border: "none",
  borderRadius: 4,
  padding: "8px 14px",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
};

const btnSecondary: React.CSSProperties = {
  background: "#fff",
  color: "#0747a6",
  border: "1px solid #0747a6",
  borderRadius: 4,
  padding: "8px 14px",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
};

const errorBox: React.CSSProperties = {
  background: "#ffd6cc",
  border: "1px solid #cc5500",
  color: "#7a2200",
  padding: "8px 12px",
  borderRadius: 4,
  marginBottom: 12,
};

const orphanBox: React.CSSProperties = {
  background: "#fff3cd",
  border: "2px dashed #ffa500",
  borderRadius: 6,
  padding: 10,
};
