"use client";

import { useCallback, useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { TopicData } from "@/types";
import AddTopicForm from "@/components/AddTopicForm";

type Props = {
  callId: string;
  projectId: string;
  defaultOpen?: boolean;
};

export default function TopicsPanel({ callId, projectId, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const [topics, setTopics] = useState<TopicData[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedCount, setSavedCount] = useState(0);

  const load = useCallback(async () => {
    if (!open) return;
    setLoading(true);
    try {
      const data = await topicsAPI.listForProject(projectId);
      setTopics(data);
    } finally {
      setLoading(false);
    }
  }, [open, projectId]);

  useEffect(() => { load(); }, [load]);

  async function handleAdd(topic: TopicData) {
    setSaving(true);
    setSaveError(null);
    try {
      await topicsAPI.save(callId, [{
        ...topic,
        topic_id: null,
        disposition: null,
      }]);
      logger.info("Topic added to done call", { component: "TopicsPanel", data: { callId } });
      setSavedCount((n) => n + 1);
      setShowAdd(false);
      await load();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to save topic";
      setSaveError(msg);
      logger.error("Failed to add topic", { component: "TopicsPanel", data: err });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ background: "white", border: "1px solid #dfe1e6", borderRadius: 8, marginBottom: 12 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "10px 14px", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}
      >
        <span style={{ fontSize: 12, fontWeight: 700, color: "#172b4d" }}>
          Topics {topics.length > 0 && !loading ? `(${topics.length})` : ""}
        </span>
        <span style={{ fontSize: 10, color: "#97a0af" }}>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div style={{ borderTop: "1px solid #f4f5f7" }}>
          {loading ? (
            <p style={{ fontSize: 12, color: "#5e6c84", padding: "10px 14px" }}>Loading…</p>
          ) : (
            <>
              {topics.length === 0 ? (
                <p style={{ fontSize: 12, color: "#5e6c84", padding: "10px 14px" }}>No topics yet.</p>
              ) : (
                <div style={{ padding: "8px 14px" }}>
                  {topics.map((t) => (
                    <TopicRow key={t.topic_id ?? t.name} topic={t} />
                  ))}
                </div>
              )}

              {savedCount > 0 && (
                <div style={{ fontSize: 11, color: "#36b37e", padding: "4px 14px" }}>
                  ✓ {savedCount} topic{savedCount > 1 ? "s" : ""} added to this call
                </div>
              )}

              {saveError && (
                <div style={{ fontSize: 11, color: "#ae2a19", padding: "4px 14px" }}>{saveError}</div>
              )}

              <div style={{ padding: "8px 14px", borderTop: "1px solid #f4f5f7" }}>
                {showAdd ? (
                  <div style={{ opacity: saving ? 0.6 : 1, pointerEvents: saving ? "none" : "auto" }}>
                    <AddTopicForm onAdd={handleAdd} />
                    <button
                      onClick={() => setShowAdd(false)}
                      style={{ fontSize: 11, color: "#5e6c84", background: "none", border: "none",
                        cursor: "pointer", marginTop: 4 }}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setShowAdd(true)}
                    style={{ fontSize: 12, color: "#0052cc", background: "none", border: "none",
                      cursor: "pointer", fontWeight: 600 }}
                  >
                    + Add topic
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function TopicRow({ topic }: { topic: TopicData }) {
  const SENTIMENT_COLOR: Record<string, string> = {
    concern: "#ae2a19", positive: "#216e4e", neutral: "#5e6c84",
  };
  const STATUS_COLOR: Record<string, string> = {
    open: "#0052cc", in_progress: "#974f0c", resolved: "#36b37e",
  };
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 8,
      paddingBottom: 8, marginBottom: 8, borderBottom: "1px solid #f4f5f7" }}>
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#172b4d" }}>{topic.name}</span>
          <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
            color: STATUS_COLOR[topic.status] ?? "#5e6c84" }}>
            {topic.status?.replace("_", " ")}
          </span>
          {topic.calls_open && topic.calls_open >= 2 && (
            <span style={{ fontSize: 9, fontWeight: 700, background: "#fff4e6",
              color: "#974f0c", padding: "1px 5px", borderRadius: 3 }}>
              Open · {topic.calls_open} calls
            </span>
          )}
        </div>
        {topic.summary && (
          <p style={{ fontSize: 11, color: "#5e6c84", margin: 0, lineHeight: 1.5 }}>{topic.summary}</p>
        )}
      </div>
      <span style={{ fontSize: 10, color: SENTIMENT_COLOR[topic.sentiment] ?? "#5e6c84",
        fontWeight: 700, textTransform: "uppercase", flexShrink: 0 }}>
        {topic.sentiment}
      </span>
    </div>
  );
}
