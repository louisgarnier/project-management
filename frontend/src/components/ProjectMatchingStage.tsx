"use client";

import { useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { TopicData, MatchGroup } from "@/types";

type Props = {
  callId: string;
  projectId: string;
  onMatchingComplete: () => void;
};

const PILL: React.CSSProperties = {
  margin: "4px 12px",
  padding: "9px 12px",
  borderRadius: 6,
  border: "1.5px solid #dfe1e6",
  background: "white",
  cursor: "pointer",
  userSelect: "none",
  transition: "border-color .12s, background .12s",
};

const STATUS_BADGE: Record<string, React.CSSProperties> = {
  open:        { background: "#e9f0ff", color: "#0052cc" },
  in_progress: { background: "#fff4e6", color: "#974f0c" },
  resolved:    { background: "#e3fcef", color: "#006644" },
};

const GROUP_COLORS = [
  { bg: "#e9f0ff", border: "#4c9aff", text: "#0052cc" },  // blue
  { bg: "#e3fcef", border: "#57d9a3", text: "#006644" },  // green
  { bg: "#fffae6", border: "#ffc400", text: "#974f0c" },  // yellow
  { bg: "#fce4fa", border: "#cc57c5", text: "#6b2066" },  // purple
  { bg: "#ffe8d6", border: "#ff8b00", text: "#bf4300" },  // orange
  { bg: "#e6fcff", border: "#00b8d9", text: "#00668c" },  // cyan
];

function groupColor(idx: number) {
  return GROUP_COLORS[idx % GROUP_COLORS.length];
}

export default function ProjectMatchingStage({ callId, projectId, onMatchingComplete }: Props) {
  const [projectTopics, setProjectTopics] = useState<TopicData[]>([]);
  const [callTopics, setCallTopics] = useState<TopicData[]>([]);
  const [selectedLeft, setSelectedLeft] = useState<Set<string>>(new Set()); // topic_id
  const [selectedRight, setSelectedRight] = useState<Set<string>>(new Set()); // name
  const [groups, setGroups] = useState<MatchGroup[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      topicsAPI.listForProject(projectId),
      topicsAPI.getPending(callId),
    ]).then(([proj, pending]) => {
      setProjectTopics(proj);
      setCallTopics(pending);
    }).catch(() => setError("Failed to load topics"));
  }, [callId, projectId]);

  // Which project topic IDs have been matched
  const matchedProjectIds = new Set(groups.map((g) => g.project_topic_id).filter(Boolean) as string[]);
  // Which call topic names have been matched or marked new
  const accountedCallNames = new Set(groups.flatMap((g) => g.call_topic_names));

  function toggleLeft(id: string) {
    if (matchedProjectIds.has(id)) return;
    setSelectedLeft((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleRight(name: string) {
    if (accountedCallNames.has(name)) return;
    setSelectedRight((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  function handleLink() {
    if (selectedRight.size === 0 || selectedLeft.size === 0) return;
    const projectTopicId = [...selectedLeft][0]; // 1:N — one project topic
    setGroups((prev) => [
      ...prev,
      { project_topic_id: projectTopicId, call_topic_names: [...selectedRight] },
    ]);
    setSelectedLeft(new Set());
    setSelectedRight(new Set());
  }

  function handleMarkNew() {
    if (selectedRight.size === 0) return;
    setGroups((prev) => [
      ...prev,
      { project_topic_id: null, call_topic_names: [...selectedRight] },
    ]);
    setSelectedRight(new Set());
  }

  function removeGroup(idx: number) {
    setGroups((prev) => prev.filter((_, i) => i !== idx));
  }

  const allCallTopicsAccounted = callTopics.length > 0 &&
    callTopics.every((t) => accountedCallNames.has(t.name));

  const pendingCount = callTopics.filter((t) => !accountedCallNames.has(t.name)).length;

  async function handleDone() {
    setSaving(true);
    setError(null);
    try {
      await topicsAPI.saveMatches(callId, groups);
      logger.info(`✅ [ProjectMatching] Saved ${groups.length} groups`, { component: "ProjectMatchingStage" });
      onMatchingComplete();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save matches");
    } finally {
      setSaving(false);
    }
  }

  function getProjectTopicGroup(id: string): MatchGroup | undefined {
    return groups.find((g) => g.project_topic_id === id);
  }

  function getCallTopicGroup(name: string): MatchGroup | undefined {
    return groups.find((g) => g.call_topic_names.includes(name));
  }

  function groupIndex(group: MatchGroup): number {
    return groups.indexOf(group);
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

      {/* Header */}
      <div style={{ padding: "16px 20px 12px", borderBottom: "1px solid #dfe1e6", flexShrink: 0 }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", margin: "0 0 4px" }}>
          Project Topic Matching
        </h2>
        <div style={{ fontSize: 12, color: "#5e6c84" }}>
          Step 1 of 2 — Match this call&apos;s topics to existing project topics, or mark as new.
        </div>
      </div>

      {error && (
        <div style={{ margin: "0 20px", marginTop: 12, background: "#fff1f0", border: "1px solid #ffbdad",
          borderRadius: 6, padding: "10px 14px", fontSize: 12, color: "#ae2a19", flexShrink: 0 }}>
          {error}
        </div>
      )}

      {/* Two-column body */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* LEFT — existing project topics */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", borderRight: "1px solid #dfe1e6" }}>
          <div style={{ padding: "10px 16px 8px", borderBottom: "1px solid #f0f1f3", flexShrink: 0,
            display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".05em", color: "#5e6c84" }}>
              Existing Project Topics
            </span>
            <span style={{ fontSize: 10, color: "#97a0af" }}>{projectTopics.length} topics</span>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
            {projectTopics.map((t) => {
              const group = getProjectTopicGroup(t.topic_id ?? "");
              const isSelected = selectedLeft.has(t.topic_id ?? "");
              const isMatched = !!group;
              return (
                <div
                  key={t.topic_id}
                  onClick={() => toggleLeft(t.topic_id ?? "")}
                  style={{
                    ...PILL,
                    borderColor: isMatched ? groupColor(groupIndex(group!)).border : isSelected ? "#0052cc" : "#dfe1e6",
                    background: isMatched ? groupColor(groupIndex(group!)).bg : isSelected ? "#e9f0ff" : "white",
                    cursor: isMatched ? "default" : "pointer",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "#172b4d" }}>{t.name}</span>
                    {t.status && (
                      <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                        padding: "2px 6px", borderRadius: 3, ...(STATUS_BADGE[t.status] ?? STATUS_BADGE.open) }}>
                        {t.status.replace("_", " ")}
                      </span>
                    )}
                    {isMatched && (
                      <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                        padding: "2px 6px", borderRadius: 3,
                        background: groupColor(groupIndex(group!)).bg,
                        color: groupColor(groupIndex(group!)).text,
                        border: `1px solid ${groupColor(groupIndex(group!)).border}` }}>
                        Matched
                      </span>
                    )}
                    {isMatched && (
                      <button
                        onClick={(e) => { e.stopPropagation(); removeGroup(groupIndex(group!)); }}
                        title="Remove match"
                        style={{ marginLeft: "auto", fontSize: 10, color: "#bfc5ce",
                          background: "none", border: "none", cursor: "pointer" }}
                      >
                        ✕
                      </button>
                    )}
                  </div>
                  {t.summary && (
                    <div style={{ fontSize: 11, color: "#5e6c84", lineHeight: 1.4 }}>{t.summary}</div>
                  )}
                  {isMatched && (
                    <div style={{ fontSize: 10, color: groupColor(groupIndex(group!)).text, fontWeight: 600, marginTop: 4 }}>
                      ↔ {group!.call_topic_names.join(", ")}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* CENTER — action buttons */}
        <div style={{ width: 72, flexShrink: 0, display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center", background: "#fafbfc",
          borderRight: "1px solid #dfe1e6", gap: 8, padding: "12px 0" }}>
          <button
            onClick={handleLink}
            disabled={selectedLeft.size === 0 || selectedRight.size === 0}
            title="Link selected topics"
            style={{
              writingMode: "vertical-rl", textOrientation: "mixed",
              fontSize: 11, fontWeight: 700,
              background: (selectedLeft.size > 0 && selectedRight.size > 0) ? "#0052cc" : "#f4f5f7",
              color: (selectedLeft.size > 0 && selectedRight.size > 0) ? "white" : "#97a0af",
              border: "none", padding: "12px 8px", borderRadius: 6,
              cursor: (selectedLeft.size > 0 && selectedRight.size > 0) ? "pointer" : "default",
              letterSpacing: ".04em", fontFamily: "inherit",
            }}
          >
            Link ↔
          </button>
          <button
            onClick={handleMarkNew}
            disabled={selectedRight.size === 0}
            title="Mark as new project topic"
            style={{
              writingMode: "vertical-rl", textOrientation: "mixed",
              fontSize: 11, fontWeight: 600,
              background: "white",
              color: selectedRight.size > 0 ? "#172b4d" : "#97a0af",
              border: `1px solid ${selectedRight.size > 0 ? "#97a0af" : "#dfe1e6"}`,
              padding: "12px 8px", borderRadius: 6,
              cursor: selectedRight.size > 0 ? "pointer" : "default",
              fontFamily: "inherit",
            }}
          >
            New →
          </button>
        </div>

        {/* RIGHT — this call's topics */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{ padding: "10px 16px 8px", borderBottom: "1px solid #f0f1f3", flexShrink: 0,
            display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".05em", color: "#5e6c84" }}>
              This Call&apos;s Topics
            </span>
            <span style={{ fontSize: 10, color: "#97a0af" }}>
              {callTopics.length - pendingCount} matched · {pendingCount} pending
            </span>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
            {callTopics.map((t) => {
              const group = getCallTopicGroup(t.name);
              const isSelected = selectedRight.has(t.name);
              const isAccounted = accountedCallNames.has(t.name);
              return (
                <div
                  key={t.name}
                  onClick={() => toggleRight(t.name)}
                  style={{
                    ...PILL,
                    borderColor: isAccounted && group ? groupColor(groupIndex(group)).border : isSelected ? "#0052cc" : "#dfe1e6",
                    background: isAccounted && group ? groupColor(groupIndex(group)).bg : isSelected ? "#e9f0ff" : "white",
                    cursor: isAccounted ? "default" : "pointer",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "#172b4d" }}>{t.name}</span>
                    {isAccounted && group && (
                      <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                        padding: "2px 6px", borderRadius: 3,
                        background: groupColor(groupIndex(group)).bg,
                        color: groupColor(groupIndex(group)).text,
                        border: `1px solid ${groupColor(groupIndex(group)).border}` }}>
                        {group.project_topic_id ? "Matched" : "New Topic"}
                      </span>
                    )}
                    {isAccounted && group && (
                      <button
                        onClick={(e) => { e.stopPropagation(); removeGroup(groupIndex(group)); }}
                        title="Remove match"
                        style={{ marginLeft: "auto", fontSize: 10, color: "#bfc5ce",
                          background: "none", border: "none", cursor: "pointer" }}
                      >
                        ✕
                      </button>
                    )}
                  </div>
                  {t.summary && (
                    <div style={{ fontSize: 11, color: "#5e6c84", lineHeight: 1.4 }}>{t.summary}</div>
                  )}
                  {isAccounted && group?.project_topic_id && (
                    <div style={{ fontSize: 10, color: groupColor(groupIndex(group!)).text, fontWeight: 600, marginTop: 4 }}>
                      ↔ {projectTopics.find((p) => p.topic_id === group!.project_topic_id)?.name}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

      </div>

      {/* Action bar */}
      <div style={{ padding: "12px 20px", borderTop: "1px solid #dfe1e6", background: "white",
        display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
        <span style={{ fontSize: 12, color: "#5e6c84" }}>
          {allCallTopicsAccounted ? (
            <span style={{ color: "#36b37e", fontWeight: 600 }}>✓ All call topics accounted for</span>
          ) : (
            <><strong style={{ color: "#172b4d" }}>{pendingCount}</strong> call topic{pendingCount !== 1 ? "s" : ""} still need matching</>
          )}
        </span>
        <button
          onClick={handleDone}
          disabled={!allCallTopicsAccounted || saving}
          style={{
            padding: "8px 22px", borderRadius: 6, border: "none",
            background: allCallTopicsAccounted && !saving ? "#0052cc" : "#f4f5f7",
            color: allCallTopicsAccounted && !saving ? "white" : "#97a0af",
            fontSize: 13, fontWeight: 600,
            cursor: allCallTopicsAccounted && !saving ? "pointer" : "default",
            fontFamily: "inherit",
          }}
        >
          {saving ? "Saving…" : "Done Matching →"}
        </button>
      </div>

    </div>
  );
}
