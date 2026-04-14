"use client";

import { useCallback, useEffect, useState } from "react";
import { callsAPI, topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { TopicData, Call, ExtractionResult } from "@/types";
import AddTopicForm from "@/components/AddTopicForm";

type Props = {
  callId: string;
  projectId: string;
  defaultOpen?: boolean;
  call?: Call; // when provided, enables stale banner and lock enforcement
  callScoped?: boolean; // when true, shows only topics from this specific call
};

export default function TopicsPanel({ callId, projectId, defaultOpen = false, call, callScoped = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const [topics, setTopics] = useState<TopicData[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedCount, setSavedCount] = useState(0);
  const [reExtracting, setReExtracting] = useState(false);
  const [reExtractError, setReExtractError] = useState<string | null>(null);
  const [localTopicsStale, setLocalTopicsStale] = useState(call?.topics_stale ?? false);

  useEffect(() => {
    setLocalTopicsStale(call?.topics_stale ?? false);
  }, [call?.topics_stale]);

  const load = useCallback(async () => {
    if (!open) return;
    setLoading(true);
    try {
      const data = callScoped
        ? await topicsAPI.listForCall(callId)
        : await topicsAPI.listForProject(projectId);
      setTopics(data);
    } finally {
      setLoading(false);
    }
  }, [open, callScoped, callId, projectId]);

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

  async function handleReExtract() {
    setReExtracting(true);
    setReExtractError(null);
    try {
      const result: ExtractionResult = await topicsAPI.extract(callId);
      const allTopics = [
        ...result.followed_up,
        ...result.not_discussed,
        ...result.new_topics,
      ];
      await topicsAPI.save(callId, allTopics.map((t) => ({
        ...t,
        topic_id: t.topic_id ?? null,
        disposition: null,
      })));
      await callsAPI.clearTopicsStale(callId);
      setLocalTopicsStale(false);
      await load();
    } catch (err) {
      setReExtractError(err instanceof Error ? err.message : "Re-extraction failed");
    } finally {
      setReExtracting(false);
    }
  }

  async function handleDismissStale() {
    try {
      await callsAPI.clearTopicsStale(callId);
      setLocalTopicsStale(false);
    } catch { /* ignore */ }
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
          {localTopicsStale && !call?.is_locked && (
            <div style={{ margin: "0 14px 10px", background: "#fff4e6", border: "1px solid #ffe0a0",
              borderRadius: 6, padding: "8px 12px", fontSize: 11, color: "#974f0c" }}>
              <div style={{ fontWeight: 700, marginBottom: 4 }}>⚠ Transcript was updated — topics may be out of date</div>
              {reExtractError && <div style={{ color: "#ae2a19", marginBottom: 4 }}>{reExtractError}</div>}
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={handleReExtract}
                  disabled={reExtracting}
                  style={{ fontSize: 10, fontWeight: 600, background: "#974f0c", color: "white",
                    border: "none", padding: "3px 10px", borderRadius: 4,
                    cursor: reExtracting ? "not-allowed" : "pointer", opacity: reExtracting ? 0.6 : 1 }}
                >
                  {reExtracting ? "Re-extracting…" : "Re-extract topics"}
                </button>
                <button
                  onClick={handleDismissStale}
                  style={{ fontSize: 10, color: "#974f0c", background: "none", border: "none",
                    cursor: "pointer", textDecoration: "underline" }}
                >
                  Dismiss
                </button>
              </div>
            </div>
          )}
          {loading ? (
            <p style={{ fontSize: 12, color: "#5e6c84", padding: "10px 14px" }}>Loading…</p>
          ) : (
            <>
              {topics.length === 0 ? (
                <p style={{ fontSize: 12, color: "#5e6c84", padding: "10px 14px" }}>No topics yet.</p>
              ) : (
                <div style={{ padding: "8px 14px" }}>
                  {topics.map((t) => (
                    <TopicRow key={t.topic_id ?? t.name} topic={t} callId={callId} onSaved={load} callIsLocked={!!(call?.is_locked)} hideCallsOpen={callScoped} callScoped={callScoped} />
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
                  !call?.is_locked && (
                    <button
                      onClick={() => setShowAdd(true)}
                      style={{ fontSize: 12, color: "#0052cc", background: "none", border: "none",
                        cursor: "pointer", fontWeight: 600 }}
                    >
                      + Add topic
                    </button>
                  )
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function TopicRow({ topic, callId, onSaved, callIsLocked, hideCallsOpen, callScoped }: {
  topic: TopicData; callId: string; onSaved: () => void; callIsLocked: boolean; hideCallsOpen?: boolean; callScoped?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<TopicData>(topic);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [newFollowUp, setNewFollowUp] = useState("");

  function set<K extends keyof TopicData>(key: K, val: TopicData[K]) {
    setDraft((prev) => ({ ...prev, [key]: val }));
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      await topicsAPI.save(callId, [{
        ...draft,
        topic_id: topic.topic_id ?? null,
        disposition: null,
      }]);
      setEditing(false);
      onSaved();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  function handleCancel() {
    setDraft(topic);
    setSaveError(null);
    setEditing(false);
  }

  async function handleDelete() {
    if (!topic.topic_id) return;
    setDeleting(true);
    try {
      await topicsAPI.deleteFromCall(callId, topic.topic_id);
      onSaved(); // refresh list
    } catch (err) {
      logger.error("Failed to delete topic from call", { component: "TopicsPanel", data: err });
    } finally {
      setDeleting(false);
    }
  }

  const SENTIMENT_COLOR: Record<string, string> = {
    concern: "#ae2a19", positive: "#216e4e", neutral: "#5e6c84",
  };
  const STATUS_COLOR: Record<string, string> = {
    open: "#0052cc", in_progress: "#974f0c", resolved: "#36b37e",
  };

  if (editing) {
    return (
      <div style={{ paddingBottom: 10, marginBottom: 8, borderBottom: "1px solid #f4f5f7" }}>
        {/* Name */}
        <input
          value={draft.name}
          onChange={(e) => set("name", e.target.value)}
          placeholder="Topic name"
          style={{ width: "100%", fontSize: 12, fontWeight: 600, color: "#172b4d",
            border: "1px solid #dfe1e6", borderRadius: 4, padding: "3px 6px",
            marginBottom: 6, boxSizing: "border-box" }}
        />
        {/* Summary */}
        <textarea
          value={draft.summary ?? ""}
          onChange={(e) => set("summary", e.target.value)}
          placeholder="Summary…"
          rows={2}
          style={{ width: "100%", fontSize: 11, color: "#5e6c84",
            border: "1px solid #dfe1e6", borderRadius: 4, padding: "4px 6px",
            resize: "vertical", marginBottom: 6, boxSizing: "border-box" }}
        />
        {/* Status / Owner / Sentiment */}
        <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
          <select value={draft.status} onChange={(e) => set("status", e.target.value as TopicData["status"])}
            style={{ fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "2px 4px" }}>
            <option value="open">Open</option>
            <option value="in_progress">In Progress</option>
            <option value="resolved">Resolved</option>
          </select>
          <select value={draft.owner} onChange={(e) => set("owner", e.target.value as TopicData["owner"])}
            style={{ fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "2px 4px" }}>
            <option value="Us">Us</option>
            <option value="Client">Client</option>
            <option value="Both">Both</option>
          </select>
          <select value={draft.sentiment} onChange={(e) => set("sentiment", e.target.value as TopicData["sentiment"])}
            style={{ fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "2px 4px" }}>
            <option value="positive">Positive</option>
            <option value="neutral">Neutral</option>
            <option value="concern">Concern</option>
          </select>
        </div>
        {/* Follow-ups */}
        <div style={{ marginBottom: 6 }}>
          <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", color: "#97a0af", marginBottom: 4 }}>
            Follow-ups
          </div>
          {(draft.follow_up_items ?? []).map((item, i) => (
            <div key={i} style={{ display: "flex", gap: 4, alignItems: "center", marginBottom: 2 }}>
              <input value={item}
                onChange={(e) => {
                  const items = [...(draft.follow_up_items ?? [])];
                  items[i] = e.target.value;
                  set("follow_up_items", items);
                }}
                style={{ flex: 1, fontSize: 10, border: "1px solid #dfe1e6", borderRadius: 4, padding: "1px 6px" }}
              />
              <button onClick={() => set("follow_up_items", (draft.follow_up_items ?? []).filter((_, idx) => idx !== i))}
                style={{ fontSize: 10, color: "#97a0af", background: "none", border: "none", cursor: "pointer" }}>✕</button>
            </div>
          ))}
          <div style={{ display: "flex", gap: 4, marginTop: 2 }}>
            <input value={newFollowUp} onChange={(e) => setNewFollowUp(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && newFollowUp.trim()) {
                  set("follow_up_items", [...(draft.follow_up_items ?? []), newFollowUp.trim()]);
                  setNewFollowUp("");
                }
              }}
              placeholder="Add follow-up…"
              style={{ flex: 1, fontSize: 10, border: "1px solid #dfe1e6", borderRadius: 4, padding: "2px 6px" }}
            />
            <button
              onClick={() => { if (newFollowUp.trim()) { set("follow_up_items", [...(draft.follow_up_items ?? []), newFollowUp.trim()]); setNewFollowUp(""); } }}
              style={{ fontSize: 10, color: "#0052cc", background: "none", border: "1px solid #b3c6e8", borderRadius: 4, padding: "2px 8px", cursor: "pointer" }}>
              Add
            </button>
          </div>
        </div>
        {/* Actions */}
        {saveError && <p style={{ fontSize: 10, color: "#ae2a19", margin: "4px 0" }}>{saveError}</p>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
          <button onClick={handleCancel} disabled={saving}
            style={{ fontSize: 11, color: "#5e6c84", background: "none", border: "none", cursor: "pointer" }}>
            Cancel
          </button>
          <button onClick={handleSave} disabled={saving}
            style={{ fontSize: 11, fontWeight: 600, background: saving ? "#dfe1e6" : "#0052cc",
              color: "white", border: "none", padding: "4px 12px", borderRadius: 4, cursor: saving ? "not-allowed" : "pointer" }}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    );
  }

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
          {!hideCallsOpen && topic.calls_open && topic.calls_open >= 2 && (
            <span style={{ fontSize: 9, fontWeight: 700, background: "#fff4e6",
              color: "#974f0c", padding: "1px 5px", borderRadius: 3 }}>
              Open · {topic.calls_open} calls
            </span>
          )}
        </div>
        {topic.summary && (
          <p style={{ fontSize: 11, color: "#5e6c84", margin: 0, lineHeight: 1.5 }}>{topic.summary}</p>
        )}
        {(topic.follow_up_items ?? []).length > 0 && (
          <div style={{ marginTop: 4 }}>
            {(topic.follow_up_items ?? []).map((item, i) => (
              <div key={i} style={{ fontSize: 10, color: "#5e6c84" }}>→ {item}</div>
            ))}
          </div>
        )}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
        <span style={{ fontSize: 10, color: SENTIMENT_COLOR[topic.sentiment] ?? "#5e6c84",
          fontWeight: 700, textTransform: "uppercase" }}>
          {topic.sentiment}
        </span>
        {!callIsLocked && (
          <button onClick={() => setEditing(true)}
            style={{ fontSize: 11, color: "#97a0af", background: "none", border: "none",
              cursor: "pointer", padding: 0 }} title="Edit">
            ✎
          </button>
        )}
        {callScoped && !callIsLocked && (
          <button
            onClick={handleDelete}
            disabled={deleting}
            title="Remove from this call"
            style={{ fontSize: 11, color: "#bfc5ce", background: "none", border: "none",
              cursor: deleting ? "default" : "pointer", padding: 0, opacity: deleting ? 0.5 : 1 }}
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
}
