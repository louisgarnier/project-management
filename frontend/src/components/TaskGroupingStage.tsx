"use client";

// EPIC-20 Stage 2: Task grouping (3-column layout).
//
// LEFT  : Previous-call tasks (collapsible per source topic).
// MID   : New-call tasks (collapsible per source topic).
// RIGHT : Groups. Each group is a CARD with:
//           - editable NAME (top, large)
//           - target TOPIC dropdown
//           - "+ Add selected" button (adds current task selection to this group)
//           - task list with × per task
//           - delete-group button
//
// Workflow:
//   1. Click tasks left/right (⌘/Ctrl/Shift for multi-select).
//   2. Click "+ Create group" — a new empty card appears on the right.
//   3. Selection is auto-added to the new group; name + topic editable.
//   4. To add MORE tasks: select them, click "+ Add" on a group card.
//   5. Save & advance once orphan bin is empty.

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  taskGroupingAPI,
  type GroupingGroup,
  type GroupingTask,
  type GroupingTopic,
} from "@/api/client";
import { logger } from "@/utils/logger";

type Props = { callId: string; onAdvance: () => void };

const GROUP_COLORS = [
  { bg: "#e9f0ff", border: "#4c9aff", text: "#0052cc" },
  { bg: "#e3fcef", border: "#57d9a3", text: "#006644" },
  { bg: "#fce4fa", border: "#cc57c5", text: "#6b2066" },
  { bg: "#ffe8d6", border: "#ff8b00", text: "#bf4300" },
  { bg: "#e6fcff", border: "#00b8d9", text: "#00668c" },
  { bg: "#ffd6d6", border: "#ff5630", text: "#ae2a19" },
  { bg: "#fff3cd", border: "#dbab09", text: "#735a00" },
  { bg: "#d4f0d4", border: "#197d23", text: "#0c5c14" },
];
const colorOf = (i: number) => GROUP_COLORS[i % GROUP_COLORS.length];

const KIND_LABEL: Record<GroupingGroup["group_kind"], string> = {
  new_only: "NEW",
  old_only: "OLD",
  mixed: "MIXED",
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
  const [dropped, setDropped] = useState<Set<string>>(new Set());
  // Cache of dropped tasks' text/origin/topic so the "Dropped" section can show
  // them even after the backend stops returning them in `tasks`.
  const [droppedCache, setDroppedCache] = useState<Map<string, GroupingTask>>(new Map());
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"run" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const d = await taskGroupingAPI.state(callId);
      setTopics(d.topics);
      setTasks(d.tasks);
      setGroups(d.groups);
      setOrphans(d.orphans);
      setDropped(new Set(d.dropped || []));
      setSelected(new Set());
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

  // ── View-models ────────────────────────────────────────────────────────────
  const prevColumns = useMemo(() => groupTasksByTopicName(tasks.filter((t) => t.origin === "previous")), [tasks]);
  const newColumns = useMemo(() => groupTasksByTopicName(tasks.filter((t) => t.origin === "new")), [tasks]);
  const tasksById = useMemo(() => {
    const m = new Map<string, GroupingTask>();
    for (const t of tasks) m.set(t.id, t);
    for (const [id, t] of droppedCache.entries()) {
      if (!m.has(id)) m.set(id, t);
    }
    return m;
  }, [tasks, droppedCache]);
  const groupByTaskId = useMemo(() => {
    const m = new Map<string, number>();
    groups.forEach((g, i) => {
      for (const tid of g.task_ids) m.set(tid, i);
    });
    return m;
  }, [groups]);

  // ── Selection helpers ────────────────────────────────────────────────────────
  // Clic simple = toggle (ajoute si non sélectionné, retire sinon).
  // Pas besoin de modifier (Cmd/Ctrl/Shift) — sélection multiple par défaut.
  const toggleSelect = (taskId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  };

  // ── Group mutations ──────────────────────────────────────────────────────────
  const mutateGroups = (updater: (gs: GroupingGroup[]) => GroupingGroup[]) => {
    setGroups((gs) => {
      const next = updater(gs)
        .filter((g) => g.task_ids.length > 0)
        .map((g) => ({ ...g, group_kind: inferKind(g.task_ids) }));
      const placed = new Set<string>();
      for (const g of next) for (const tid of g.task_ids) placed.add(tid);
      setOrphans(tasks.map((t) => t.id).filter((id) => !placed.has(id)));
      return next;
    });
  };

  const createGroupFromSelection = () => {
    if (selected.size === 0) {
      setError("Sélectionne au moins une tâche d'abord.");
      return;
    }
    if (topics.length === 0) {
      setError("Aucun topic finalisé — retourne à Stage 1.");
      return;
    }
    const newId = `local-${crypto.randomUUID()}`;
    const taskIds = Array.from(selected);
    mutateGroups((gs) => [
      ...gs.map((g) => ({ ...g, task_ids: g.task_ids.filter((tid) => !selected.has(tid)) })),
      {
        id: newId,
        name: "",
        finalized_topic_id: topics[0].id,
        group_kind: inferKind(taskIds),
        task_ids: taskIds,
      },
    ]);
    setSelected(new Set());
  };

  const addSelectionToGroup = (groupId: string) => {
    if (selected.size === 0) return;
    mutateGroups((gs) =>
      gs
        .map((g) => ({ ...g, task_ids: g.task_ids.filter((tid) => !selected.has(tid)) }))
        .map((g) =>
          g.id === groupId ? { ...g, task_ids: [...g.task_ids, ...Array.from(selected)] } : g,
        ),
    );
    setSelected(new Set());
  };

  const removeTaskFromGroup = (taskId: string) => {
    mutateGroups((gs) => gs.map((g) => ({ ...g, task_ids: g.task_ids.filter((tid) => tid !== taskId) })));
  };

  const deleteGroup = (groupId: string) => {
    mutateGroups((gs) => gs.filter((g) => g.id !== groupId));
  };

  const setGroupName = (groupId: string, name: string) => {
    setGroups((gs) => gs.map((g) => (g.id === groupId ? { ...g, name } : g)));
  };

  const setGroupTopic = (groupId: string, topicId: string) => {
    setGroups((gs) => gs.map((g) => (g.id === groupId ? { ...g, finalized_topic_id: topicId } : g)));
  };

  // ── Drop / restore ────────────────────────────────────────────────────────
  const dropTask = (taskId: string) => {
    const t = tasksById.get(taskId);
    if (t) {
      setDroppedCache((m) => {
        const next = new Map(m);
        next.set(taskId, t);
        return next;
      });
    }
    // Remove from any group
    mutateGroups((gs) => gs.map((g) => ({ ...g, task_ids: g.task_ids.filter((tid) => tid !== taskId) })));
    setDropped((prev) => new Set(prev).add(taskId));
    setSelected((prev) => {
      const next = new Set(prev);
      next.delete(taskId);
      return next;
    });
  };

  const restoreTask = (taskId: string) => {
    setDropped((prev) => {
      const next = new Set(prev);
      next.delete(taskId);
      return next;
    });
    // Update orphans calc so it shows up in counts
    setOrphans((prev) => (prev.includes(taskId) ? prev : [...prev, taskId]));
  };

  const dropSelected = () => {
    if (selected.size === 0) return;
    if (!window.confirm(`Jeter ${selected.size} tâche${selected.size === 1 ? "" : "s"} ? Elle${selected.size === 1 ? "" : "s"} ne sera${selected.size === 1 ? "" : "ont"} pas envoyée${selected.size === 1 ? "" : "s"} aux passes.`)) return;
    const ids = Array.from(selected);
    for (const id of ids) dropTask(id);
  };

  // ── Actions ──────────────────────────────────────────────────────────────────
  const runLLM = async () => {
    if (groups.length > 0 && !window.confirm("Re-cluster va écraser tes groupes actuels. Continuer ?")) return;
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
      setError(`${orphans.length} tâche(s) sans groupe — place-les ou jette-les d'abord.`);
      return;
    }
    setBusy("save");
    setError(null);
    try {
      const out = await taskGroupingAPI.save(callId, groups, Array.from(dropped));
      if (out.advanced) onAdvance();
      else await reload();
    } catch (e) {
      logger.error("TaskGrouping save failed", { component: "TaskGroupingStage", data: e });
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setBusy(null);
    }
  };

  // Debounced auto-save (draft) on any change to groups OR dropped
  useEffect(() => {
    if (loading || busy) return;
    const t = setTimeout(() => {
      taskGroupingAPI.save(callId, groups, Array.from(dropped)).catch(() => {});
    }, 800);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groups, dropped]);

  if (loading) return <div style={{ padding: 24 }}>Chargement…</div>;

  return (
    <div style={{ padding: 12, display: "flex", flexDirection: "column", height: "100%", width: "100%" }}>
      {/* Top bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 16 }}>Task grouping</h2>
          <div style={{ fontSize: 11, color: "#5e6c84", marginTop: 2 }}>
            Sélectionne des tâches → <strong>Créer un groupe</strong> → nomme-le + choisis son topic.
            Orphelins: <strong style={{ color: orphans.length > 0 ? "#cc5500" : "#197d23" }}>{orphans.length}</strong>
            {" · "}Groupes: <strong>{groups.length}</strong>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={runLLM} disabled={busy !== null} style={btnSecondary}>
            {busy === "run" ? "Clustering…" : "🤖 Re-cluster (LLM)"}
          </button>
          <button
            onClick={save}
            disabled={busy !== null || orphans.length > 0}
            style={{ ...btnPrimary, opacity: busy !== null || orphans.length > 0 ? 0.5 : 1 }}
          >
            {busy === "save"
              ? "Enregistrement…"
              : orphans.length > 0
                ? `${orphans.length} orphelin${orphans.length === 1 ? "" : "s"}`
                : "💾 Save & advance"}
          </button>
        </div>
      </div>

      {error && <div style={errorBox}>{error}</div>}

      {/* Selection action bar */}
      <div style={selectionBar}>
        <div style={{ flex: 1, fontSize: 12 }}>
          <strong>{selected.size}</strong> tâche{selected.size === 1 ? "" : "s"} sélectionnée{selected.size === 1 ? "" : "s"}
          {selected.size > 0 && (
            <button onClick={() => setSelected(new Set())} style={linkBtn}>
              désélectionner
            </button>
          )}
          {dropped.size > 0 && (
            <span style={{ marginLeft: 12, color: "#974f0c" }}>
              · 🗑 {dropped.size} jetée{dropped.size === 1 ? "" : "s"}
            </span>
          )}
        </div>
        <button
          onClick={dropSelected}
          disabled={selected.size === 0}
          style={{
            background: "#fff",
            color: "#cc5500",
            border: "1px solid #cc5500",
            borderRadius: 4,
            padding: "6px 12px",
            fontSize: 12,
            fontWeight: 600,
            cursor: selected.size === 0 ? "not-allowed" : "pointer",
            opacity: selected.size === 0 ? 0.4 : 1,
          }}
        >
          🗑 Jeter
        </button>
        <button
          onClick={createGroupFromSelection}
          disabled={selected.size === 0}
          style={{ ...btnPrimary, opacity: selected.size === 0 ? 0.4 : 1, padding: "6px 12px" }}
        >
          + Créer un groupe
        </button>
      </div>

      {/* 3 columns */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1.2fr",
          gap: 10,
          flex: 1,
          minHeight: 300,
          overflow: "hidden",
        }}
      >
        <Column
          title="Tâches précédentes"
          subtitle={`${tasks.filter((t) => t.origin === "previous").length} tâches · ${prevColumns.length} topic(s)`}
          accent="#5e6c84"
        >
          {prevColumns.map((col) => (
            <TopicSection
              key={"prev-" + col.name}
              col={col}
              groupByTaskId={groupByTaskId}
              selected={selected}
              onToggle={toggleSelect}
              onSelectAllOrphans={(ids) => setSelected((prev) => new Set([...prev, ...ids]))}
              onDrop={dropTask}
            />
          ))}
          {prevColumns.length === 0 && <Empty>Aucune tâche précédente.</Empty>}
        </Column>

        <Column
          title="Tâches du call actuel"
          subtitle={`${tasks.filter((t) => t.origin === "new").length} tâches · ${newColumns.length} topic(s)`}
          accent="#0747a6"
        >
          {newColumns.map((col) => (
            <TopicSection
              key={"new-" + col.name}
              col={col}
              groupByTaskId={groupByTaskId}
              selected={selected}
              onToggle={toggleSelect}
              onSelectAllOrphans={(ids) => setSelected((prev) => new Set([...prev, ...ids]))}
              onDrop={dropTask}
            />
          ))}
          {newColumns.length === 0 && <Empty>Aucune tâche pour ce call.</Empty>}
        </Column>

        {/* Groups column */}
        <Column
          title={`Groupes (${groups.length})`}
          subtitle="Chaque groupe = un nom + un topic + des tâches"
          accent="#197d23"
        >
          {dropped.size > 0 && (
            <div
              style={{
                marginBottom: 10,
                padding: 8,
                background: "#fbeae5",
                border: "1px dashed #cc5500",
                borderRadius: 4,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: "#7a2200", letterSpacing: ".05em" }}>
                  🗑 JETÉES · {dropped.size}
                </span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {Array.from(dropped).map((tid) => {
                  const t = tasksById.get(tid);
                  if (!t) return null;
                  return (
                    <div
                      key={tid}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                        padding: "2px 4px",
                        fontSize: 11,
                        background: "#fff",
                        borderRadius: 2,
                        color: "#7a2200",
                        textDecoration: "line-through",
                      }}
                      title={t.text}
                    >
                      <span style={{ fontWeight: 700, fontSize: 9 }}>
                        {t.origin === "new" ? "N" : "P"}
                      </span>
                      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {t.text || "(empty)"}
                      </span>
                      <button
                        onClick={() => restoreTask(tid)}
                        style={{
                          background: "transparent",
                          border: "1px solid #0052cc",
                          color: "#0052cc",
                          fontSize: 9,
                          padding: "0 5px",
                          borderRadius: 2,
                          cursor: "pointer",
                        }}
                        title="Restaurer"
                      >
                        ↶
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          {groups.length === 0 ? (
            <Empty>
              Aucun groupe. Sélectionne des tâches puis clique &ldquo;+ Créer un groupe&rdquo;.
            </Empty>
          ) : (
            groups.map((g, i) => {
              const col = colorOf(i);
              return (
                <div
                  key={g.id ?? i}
                  style={{
                    marginBottom: 10,
                    padding: 10,
                    background: col.bg,
                    borderLeft: `4px solid ${col.border}`,
                    borderRadius: 4,
                  }}
                >
                  {/* header: kind badge + delete */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: col.text, letterSpacing: ".05em" }}>
                      #{i + 1} · {KIND_LABEL[g.group_kind]} · {g.task_ids.length}
                    </span>
                    <button
                      onClick={() => g.id && deleteGroup(g.id)}
                      style={miniBtn}
                      title="Supprimer le groupe"
                    >
                      🗑
                    </button>
                  </div>

                  {/* Name input */}
                  <input
                    type="text"
                    placeholder="Nom du groupe (optionnel)"
                    value={g.name || ""}
                    onChange={(e) => g.id && setGroupName(g.id, e.target.value)}
                    style={{
                      width: "100%",
                      padding: "5px 8px",
                      fontSize: 12,
                      fontWeight: 600,
                      border: "1px solid #c1c7d0",
                      borderRadius: 3,
                      marginBottom: 6,
                      background: "#fff",
                    }}
                  />

                  {/* Topic dropdown */}
                  <select
                    value={g.finalized_topic_id}
                    onChange={(e) => g.id && setGroupTopic(g.id, e.target.value)}
                    style={{
                      width: "100%",
                      padding: "4px 8px",
                      fontSize: 11,
                      border: "1px solid #c1c7d0",
                      borderRadius: 3,
                      marginBottom: 6,
                      background: "#fff",
                    }}
                  >
                    {topics.map((t) => (
                      <option key={t.id} value={t.id}>
                        🎯 {t.name}
                      </option>
                    ))}
                  </select>

                  {/* Add selection button */}
                  <button
                    onClick={() => g.id && addSelectionToGroup(g.id)}
                    disabled={selected.size === 0 || !g.id}
                    style={{
                      width: "100%",
                      padding: "5px 8px",
                      background: selected.size > 0 ? "#0747a6" : "#fff",
                      color: selected.size > 0 ? "#fff" : "#5e6c84",
                      border: "1px solid #0747a6",
                      borderRadius: 3,
                      fontSize: 11,
                      fontWeight: 600,
                      cursor: selected.size > 0 ? "pointer" : "not-allowed",
                      marginBottom: 6,
                      opacity: selected.size > 0 ? 1 : 0.4,
                    }}
                  >
                    {selected.size > 0
                      ? `+ Ajouter ${selected.size} tâche${selected.size === 1 ? "" : "s"} sélectionnée${selected.size === 1 ? "" : "s"}`
                      : "+ Ajouter (sélectionne d'abord)"}
                  </button>

                  {/* Task list inside the group */}
                  <div style={{ display: "flex", flexDirection: "column", gap: 2, background: "#fff", padding: 4, borderRadius: 3 }}>
                    {g.task_ids.map((tid) => {
                      const t = tasksById.get(tid);
                      if (!t) return null;
                      return (
                        <div
                          key={tid}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 4,
                            padding: "2px 4px",
                            fontSize: 11,
                            borderBottom: "1px solid #f4f5f7",
                          }}
                          title={t.text}
                        >
                          <span style={{ fontWeight: 700, color: t.origin === "new" ? "#0747a6" : "#5e6c84" }}>
                            {t.origin === "new" ? "N" : "P"}
                          </span>
                          <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {t.text || "(empty)"}
                          </span>
                          <button onClick={() => removeTaskFromGroup(tid)} style={miniBtnPlain} title="Retirer">
                            ×
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })
          )}
        </Column>
      </div>
    </div>
  );
}

// ── Helpers / sub-components ────────────────────────────────────────────────

type TopicCol = { name: string; tasks: GroupingTask[] };
function groupTasksByTopicName(arr: GroupingTask[]): TopicCol[] {
  const m = new Map<string, GroupingTask[]>();
  for (const t of arr) {
    const k = (t.topic_name || "(sans topic)").trim() || "(sans topic)";
    const existing = m.get(k) ?? [];
    existing.push(t);
    m.set(k, existing);
  }
  return Array.from(m.entries()).map(([name, tasks]) => ({ name, tasks }));
}

function Column({
  title,
  subtitle,
  accent,
  children,
}: {
  title: string;
  subtitle: string;
  accent: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ background: "#f7f8fa", border: "1px solid #e1e4e8", borderRadius: 6, padding: 10, overflowY: "auto" }}>
      <div style={{ marginBottom: 8, paddingBottom: 6, borderBottom: `2px solid ${accent}` }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: accent }}>{title}</div>
        <div style={{ fontSize: 10, color: "#5e6c84" }}>{subtitle}</div>
      </div>
      {children}
    </div>
  );
}

function TopicSection({
  col,
  groupByTaskId,
  selected,
  onToggle,
  onSelectAllOrphans,
  onDrop,
}: {
  col: TopicCol;
  groupByTaskId: Map<string, number>;
  selected: Set<string>;
  onToggle: (taskId: string) => void;
  onSelectAllOrphans: (taskIds: string[]) => void;
  onDrop: (taskId: string) => void;
}) {
  const [open, setOpen] = useState(true);
  // Orphans in this topic section (not yet in a group)
  const orphansInSection = col.tasks.filter((t) => groupByTaskId.get(t.id) === undefined).map((t) => t.id);
  return (
    <div style={{ marginBottom: 8 }}>
      <div
        onClick={() => setOpen((o) => !o)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 4,
          cursor: "pointer",
          padding: "4px 6px",
          borderRadius: 3,
          background: "#eef0f3",
          marginBottom: 4,
        }}
      >
        <span style={{ fontSize: 10, color: "#5e6c84" }}>{open ? "▼" : "▶"}</span>
        <span style={{ fontSize: 12, fontWeight: 600, flex: 1 }}>{col.name}</span>
        {orphansInSection.length > 0 && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onSelectAllOrphans(orphansInSection);
            }}
            style={{
              background: "transparent",
              border: "1px solid #0052cc",
              color: "#0052cc",
              fontSize: 9,
              padding: "1px 6px",
              borderRadius: 3,
              cursor: "pointer",
            }}
            title="Sélectionner toutes les tâches non groupées de ce topic"
          >
            Tout sél.
          </button>
        )}
        <span style={{ fontSize: 10, color: "#5e6c84" }}>{col.tasks.length}</span>
      </div>
      {open &&
        col.tasks.map((t) => {
          const isSelected = selected.has(t.id);
          const groupIdx = groupByTaskId.get(t.id);
          const inGroup = groupIdx !== undefined;
          const c = inGroup ? colorOf(groupIdx) : null;
          return (
            <div
              key={t.id}
              style={{
                position: "relative",
                padding: "4px 22px 4px 8px",
                marginBottom: 3,
                marginLeft: 14,
                borderRadius: 3,
                cursor: "pointer",
                background: isSelected ? "#deebff" : inGroup ? "#f4f5f7" : "#fff",
                border: isSelected
                  ? "1.5px solid #0052cc"
                  : inGroup
                    ? `1px solid #dfe1e6`
                    : "1px solid #e1e4e8",
                fontSize: 11,
                color: inGroup ? "#7a869a" : "#172b4d",
                userSelect: "none",
                opacity: inGroup && !isSelected ? 0.5 : 1,
                textDecoration: inGroup && !isSelected ? "line-through" : "none",
              }}
              title={t.text + (inGroup ? ` (dans Groupe #${(groupIdx as number) + 1})` : "")}
            >
              <div onClick={() => onToggle(t.id)} style={{ flex: 1 }}>
                {c && (
                  <span
                    style={{
                      display: "inline-block",
                      width: 18,
                      marginRight: 4,
                      fontSize: 9,
                      fontWeight: 700,
                      color: c.border,
                      background: c.bg,
                      padding: "0 3px",
                      borderRadius: 2,
                      textAlign: "center",
                    }}
                  >
                    #{(groupIdx as number) + 1}
                  </span>
                )}
                <span
                  style={{
                    display: "inline-block",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    maxWidth: "calc(100% - 24px)",
                    verticalAlign: "middle",
                  }}
                >
                  {t.text || "(empty)"}
                </span>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDrop(t.id);
                }}
                title="Jeter cette tâche (sera ignorée par les Pass 1/2/3)"
                style={{
                  position: "absolute",
                  top: 2,
                  right: 4,
                  background: "transparent",
                  border: "none",
                  color: "#cc5500",
                  fontSize: 13,
                  cursor: "pointer",
                  padding: "0 4px",
                  lineHeight: 1,
                }}
              >
                ×
              </button>
            </div>
          );
        })}
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div style={{ color: "#5e6c84", fontSize: 11, fontStyle: "italic", padding: 12 }}>{children}</div>;
}

// ── Styles ───────────────────────────────────────────────────────────────────
const btnPrimary: React.CSSProperties = {
  background: "#0747a6",
  color: "#fff",
  border: "none",
  borderRadius: 4,
  padding: "7px 14px",
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
};
const btnSecondary: React.CSSProperties = {
  background: "#fff",
  color: "#0747a6",
  border: "1px solid #0747a6",
  borderRadius: 4,
  padding: "7px 14px",
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
};
const errorBox: React.CSSProperties = {
  background: "#ffd6cc",
  border: "1px solid #cc5500",
  color: "#7a2200",
  padding: "6px 10px",
  borderRadius: 4,
  marginBottom: 8,
  fontSize: 12,
};
const selectionBar: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  padding: "6px 10px",
  background: "#fafbfc",
  border: "1px solid #e1e4e8",
  borderRadius: 4,
  marginBottom: 8,
};
const linkBtn: React.CSSProperties = {
  marginLeft: 6,
  background: "none",
  border: "none",
  color: "#0052cc",
  fontSize: 11,
  cursor: "pointer",
  textDecoration: "underline",
};
const miniBtn: React.CSSProperties = {
  background: "rgba(255,255,255,0.6)",
  border: "1px solid rgba(0,0,0,0.1)",
  borderRadius: 3,
  padding: "0 6px",
  fontSize: 12,
  cursor: "pointer",
  lineHeight: 1.4,
  minWidth: 22,
};
const miniBtnPlain: React.CSSProperties = {
  background: "transparent",
  border: "none",
  color: "#5e6c84",
  fontSize: 14,
  cursor: "pointer",
  padding: "0 4px",
  lineHeight: 1,
};
