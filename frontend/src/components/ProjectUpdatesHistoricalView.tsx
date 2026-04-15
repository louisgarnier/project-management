"use client";

import { useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { TopicData } from "@/types";

type Props = {
  callId: string;
  projectId: string;
};

const STATUS_BADGE: Record<string, React.CSSProperties> = {
  open:        { background: "#e9f0ff", color: "#0052cc" },
  in_progress: { background: "#fff4e6", color: "#974f0c" },
  resolved:    { background: "#e3fcef", color: "#006644" },
};

const SENTIMENT_COLOR: Record<string, string> = {
  positive: "#216e4e", neutral: "#5e6c84", concern: "#ae2a19",
};

function ReadOnlyRow({ topic }: { topic: TopicData }) {
  return (
    <div style={{
      borderBottom: "1px solid #f0f1f3",
      paddingLeft: 20, paddingRight: 20, paddingTop: 10, paddingBottom: 10,
      borderLeft: `3px solid ${!topic.topic_id ? "#79dbb2" : "transparent"}`,
      background: "white",
    }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 2 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: "#172b4d" }}>{topic.name}</span>
        <span style={{
          fontSize: 9, fontWeight: 700, textTransform: "uppercase",
          padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap", flexShrink: 0,
          ...(STATUS_BADGE[topic.status ?? "open"] ?? STATUS_BADGE.open),
        }}>
          {(topic.status ?? "open").replace("_", " ")}
        </span>
        {!topic.topic_id && (
          <span style={{
            fontSize: 9, fontWeight: 700, textTransform: "uppercase",
            padding: "2px 6px", borderRadius: 3, background: "#f0fdf7", color: "#36b37e", flexShrink: 0,
          }}>
            New
          </span>
        )}
        <span style={{
          fontSize: 10, fontWeight: 700, textTransform: "uppercase",
          color: SENTIMENT_COLOR[topic.sentiment ?? "neutral"] ?? "#5e6c84", marginLeft: "auto",
        }}>
          {topic.sentiment}
        </span>
      </div>
      {topic.summary && (
        <p style={{ fontSize: 12, color: "#5e6c84", margin: "3px 0 0", lineHeight: 1.5 }}>{topic.summary}</p>
      )}
      {(topic.follow_up_items ?? []).map((item, i) => (
        <div key={i} style={{ fontSize: 11, color: "#5e6c84", paddingTop: 2 }}>→ {item}</div>
      ))}
    </div>
  );
}

function SectionHeader({ title, count, subtitle }: { title: string; count: number; subtitle?: string }) {
  return (
    <div style={{
      padding: "8px 20px 6px", borderBottom: "1px solid #dfe1e6", background: "#f4f5f7",
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "#5e6c84", letterSpacing: ".05em" }}>
        {title} ({count})
      </div>
      {subtitle && (
        <div style={{ fontSize: 11, color: "#97a0af", marginTop: 2 }}>{subtitle}</div>
      )}
    </div>
  );
}

export default function ProjectUpdatesHistoricalView({ callId, projectId }: Props) {
  const [newTopics, setNewTopics] = useState<TopicData[]>([]);
  const [updatedTopics, setUpdatedTopics] = useState<TopicData[]>([]);
  const [notDiscussed, setNotDiscussed] = useState<TopicData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      topicsAPI.getMatchGroups(callId),
      topicsAPI.listForCall(callId),
      topicsAPI.listForProject(projectId),
    ]).then(([groups, callTopics, projectTopics]) => {
      // Index call-specific topic data (from topic_updates) by project topic ID and by name
      const callTopicsByProjectId = new Map(
        callTopics.filter((t: TopicData) => t.topic_id).map((t: TopicData) => [t.topic_id!, t])
      );
      const callTopicsByName = new Map(
        callTopics.map((t: TopicData) => [t.name.toLowerCase().trim(), t])
      );

      const newCallTopicNames = new Set<string>();
      const matchedProjectIds = new Set<string>();

      const newBucket: TopicData[] = [];
      const updatedBucket: TopicData[] = [];

      for (const g of groups) {
        if (g.project_topic_id === null) {
          for (const name of g.call_topic_names) {
            const lower = name.toLowerCase().trim();
            newCallTopicNames.add(lower);
            const ct = callTopicsByName.get(lower);
            if (ct) newBucket.push({ ...ct, topic_id: undefined });
          }
        } else {
          matchedProjectIds.add(g.project_topic_id);
          // Use call-specific data (from topic_updates for this call) not current project state
          const ct = callTopicsByProjectId.get(g.project_topic_id);
          if (ct) updatedBucket.push(ct);
        }
      }

      // Not discussed: project topics not in any group AND not a new topic from this call
      const notDiscussedBucket = (projectTopics as TopicData[]).filter((t) => {
        if (matchedProjectIds.has(t.topic_id ?? "")) return false;
        if (newCallTopicNames.has(t.name.toLowerCase().trim())) return false;
        return true;
      });

      setNewTopics(newBucket);
      setUpdatedTopics(updatedBucket);
      setNotDiscussed(notDiscussedBucket);

      logger.info("[ProjectUpdatesHistoricalView] Loaded", {
        component: "ProjectUpdatesHistoricalView",
        data: { new: newBucket.length, updated: updatedBucket.length, notDiscussed: notDiscussedBucket.length },
      });
    }).catch((err) => {
      logger.error("[ProjectUpdatesHistoricalView] Failed to load", { component: "ProjectUpdatesHistoricalView", data: err });
      setError("Failed to load project updates data");
    }).finally(() => setLoading(false));
  }, [callId, projectId]);

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
          Project Topic Updates
        </h2>
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
          <span>Read-only — topic updates were saved</span>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: "auto" }}>

        {/* New Topics */}
        {newTopics.length > 0 && (
          <>
            <SectionHeader title="New Topics" count={newTopics.length} />
            {newTopics.map((t, i) => <ReadOnlyRow key={t.name ?? i} topic={t} />)}
          </>
        )}

        {/* Updated Topics */}
        {updatedTopics.length > 0 && (
          <div style={{ marginTop: newTopics.length > 0 ? 8 : 0 }}>
            <SectionHeader
              title="Updated Topics"
              count={updatedTopics.length}
              subtitle="Existing topics merged with call content"
            />
            {updatedTopics.map((t, i) => <ReadOnlyRow key={t.topic_id ?? t.name ?? i} topic={t} />)}
          </div>
        )}

        {/* Not Discussed */}
        {notDiscussed.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={{
              padding: "8px 20px 6px", borderTop: "1px solid #dfe1e6", borderBottom: "1px solid #dfe1e6",
              background: "#f4f5f7",
            }}>
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "#97a0af", letterSpacing: ".05em" }}>
                Not discussed in this call&nbsp;&nbsp;({notDiscussed.length} topic{notDiscussed.length !== 1 ? "s" : ""})
              </div>
              <div style={{ fontSize: 11, color: "#97a0af", marginTop: 2 }}>
                These topics existed in the project but were not mentioned in this call.
              </div>
            </div>
            {notDiscussed.map((t, idx) => (
              <div key={t.topic_id ?? t.name ?? idx}
                style={{
                  opacity: 0.7, borderBottom: "1px solid #f0f1f3",
                  paddingLeft: 20, paddingRight: 20, paddingTop: 10, paddingBottom: 10,
                  borderLeft: "3px solid transparent", background: "white",
                }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                  <span style={{ color: "#97a0af", fontSize: 12 }}>•</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "#172b4d" }}>{t.name}</span>
                  <span style={{
                    fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                    padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap", flexShrink: 0,
                    ...(STATUS_BADGE[t.status ?? "open"] ?? STATUS_BADGE.open),
                  }}>
                    {(t.status ?? "open").replace("_", " ")}
                  </span>
                  <span style={{
                    fontSize: 10, fontWeight: 700, textTransform: "uppercase",
                    color: SENTIMENT_COLOR[t.sentiment ?? "neutral"] ?? "#5e6c84", marginLeft: "auto",
                  }}>
                    {t.sentiment}
                  </span>
                </div>
                {t.summary && (
                  <p style={{ fontSize: 12, color: "#5e6c84", margin: "3px 0 0 18px", lineHeight: 1.5 }}>{t.summary}</p>
                )}
              </div>
            ))}
          </div>
        )}

      </div>
    </div>
  );
}
