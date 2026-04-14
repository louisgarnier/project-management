"use client";

import { useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { TopicData } from "@/types";

type Props = {
  callId: string;
  projectId: string;
};

type SavedMatchGroup = {
  project_topic_id: string | null;
  project_topic_name: string | null;
  call_topic_names: string[];
};

const PILL: React.CSSProperties = {
  margin: "4px 12px",
  padding: "9px 12px",
  borderRadius: 6,
  border: "1.5px solid #dfe1e6",
  background: "white",
  userSelect: "none",
};

const STATUS_BADGE: Record<string, React.CSSProperties> = {
  open:        { background: "#e9f0ff", color: "#0052cc" },
  in_progress: { background: "#fff4e6", color: "#974f0c" },
  resolved:    { background: "#e3fcef", color: "#006644" },
};

const GROUP_COLORS = [
  { bg: "#e9f0ff", border: "#4c9aff", text: "#0052cc" },
  { bg: "#e3fcef", border: "#57d9a3", text: "#006644" },
  { bg: "#fffae6", border: "#ffc400", text: "#974f0c" },
  { bg: "#fce4fa", border: "#cc57c5", text: "#6b2066" },
  { bg: "#ffe8d6", border: "#ff8b00", text: "#bf4300" },
  { bg: "#e6fcff", border: "#00b8d9", text: "#00668c" },
];

function groupColor(idx: number) {
  return GROUP_COLORS[idx % GROUP_COLORS.length];
}

export default function ProjectMatchingHistoricalView({ callId, projectId }: Props) {
  const [projectTopics, setProjectTopics] = useState<TopicData[]>([]);
  const [callTopics, setCallTopics] = useState<TopicData[]>([]);
  const [matchGroups, setMatchGroups] = useState<SavedMatchGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      topicsAPI.listForProject(projectId),
      topicsAPI.getPending(callId),
      topicsAPI.getMatchGroups(callId),
    ]).then(([proj, pending, groups]) => {
      setProjectTopics(proj);
      setCallTopics(pending);
      setMatchGroups(groups);
      logger.info("[ProjectMatchingHistoricalView] Loaded match data", {
        component: "ProjectMatchingHistoricalView",
        data: { projectTopics: proj.length, callTopics: pending.length, groups: groups.length },
      });
    }).catch((err) => {
      logger.error("[ProjectMatchingHistoricalView] Failed to load", { component: "ProjectMatchingHistoricalView", data: err });
      setError("Failed to load matching data");
    }).finally(() => setLoading(false));
  }, [callId, projectId]);

  function getGroupForProjectTopic(topicId: string): { group: SavedMatchGroup; idx: number } | undefined {
    const idx = matchGroups.findIndex((g) => g.project_topic_id === topicId);
    if (idx === -1) return undefined;
    return { group: matchGroups[idx], idx };
  }

  function getGroupForCallTopic(name: string): { group: SavedMatchGroup; idx: number } | undefined {
    const idx = matchGroups.findIndex((g) => g.call_topic_names.includes(name));
    if (idx === -1) return undefined;
    return { group: matchGroups[idx], idx };
  }

  if (loading) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <p style={{ fontSize: 13, color: "#5e6c84" }}>Loading…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <p style={{ fontSize: 13, color: "#ae2a19" }}>{error}</p>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

      {/* Header */}
      <div style={{ padding: "16px 20px 12px", borderBottom: "1px solid #dfe1e6", flexShrink: 0 }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", margin: "0 0 4px" }}>
          Project Topic Matching
        </h2>
        {/* Read-only banner */}
        <div style={{
          marginTop: 8,
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
          <span>Read-only — matching decisions were saved</span>
        </div>
      </div>

      {/* Two-column body */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* LEFT — existing project topics */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", borderRight: "1px solid #dfe1e6" }}>
          <div style={{
            padding: "10px 16px 8px", borderBottom: "1px solid #f0f1f3", flexShrink: 0,
            display: "flex", alignItems: "center", justifyContent: "space-between",
          }}>
            <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".05em", color: "#5e6c84" }}>
              Existing Project Topics
            </span>
            <span style={{ fontSize: 10, color: "#97a0af" }}>{projectTopics.length} topics</span>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
            {projectTopics.map((t) => {
              const matched = getGroupForProjectTopic(t.topic_id ?? "");
              const color = matched ? groupColor(matched.idx) : null;
              return (
                <div
                  key={t.topic_id}
                  style={{
                    ...PILL,
                    borderColor: color ? color.border : "#dfe1e6",
                    background: color ? color.bg : "white",
                    cursor: "default",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "#172b4d" }}>{t.name}</span>
                    {t.status && (
                      <span style={{
                        fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                        padding: "2px 6px", borderRadius: 3,
                        ...(STATUS_BADGE[t.status] ?? STATUS_BADGE.open),
                      }}>
                        {t.status.replace("_", " ")}
                      </span>
                    )}
                    {color && (
                      <span style={{
                        fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                        padding: "2px 6px", borderRadius: 3,
                        background: color.bg, color: color.text,
                        border: `1px solid ${color.border}`,
                      }}>
                        Matched
                      </span>
                    )}
                  </div>
                  {t.summary && (
                    <div style={{ fontSize: 11, color: "#5e6c84", lineHeight: 1.4 }}>{t.summary}</div>
                  )}
                  {matched && (
                    <div style={{ fontSize: 10, color: color!.text, fontWeight: 600, marginTop: 4 }}>
                      ↔ {matched.group.call_topic_names.join(", ")}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* CENTER — vertical divider only (no buttons) */}
        <div style={{
          width: 72, flexShrink: 0,
          borderRight: "1px solid #dfe1e6",
          background: "#fafbfc",
        }} />

        {/* RIGHT — this call's topics */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{
            padding: "10px 16px 8px", borderBottom: "1px solid #f0f1f3", flexShrink: 0,
            display: "flex", alignItems: "center", justifyContent: "space-between",
          }}>
            <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".05em", color: "#5e6c84" }}>
              This Call&apos;s Topics
            </span>
            <span style={{ fontSize: 10, color: "#97a0af" }}>{callTopics.length} topics</span>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
            {callTopics.map((t) => {
              const matched = getGroupForCallTopic(t.name);
              const color = matched ? groupColor(matched.idx) : null;
              const isNew = matched && matched.group.project_topic_id === null;
              return (
                <div
                  key={t.name}
                  style={{
                    ...PILL,
                    borderColor: color ? color.border : "#dfe1e6",
                    background: color ? color.bg : "white",
                    cursor: "default",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "#172b4d" }}>{t.name}</span>
                    {color && (
                      <span style={{
                        fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                        padding: "2px 6px", borderRadius: 3,
                        background: color.bg, color: color.text,
                        border: `1px solid ${color.border}`,
                      }}>
                        {isNew ? "New" : "Matched"}
                      </span>
                    )}
                  </div>
                  {t.summary && (
                    <div style={{ fontSize: 11, color: "#5e6c84", lineHeight: 1.4 }}>{t.summary}</div>
                  )}
                  {matched && !isNew && matched.group.project_topic_name && (
                    <div style={{ fontSize: 10, color: color!.text, fontWeight: 600, marginTop: 4 }}>
                      ↔ {matched.group.project_topic_name}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

      </div>
    </div>
  );
}
