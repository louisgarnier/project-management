"use client";

import { useCallback, useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type {
  Call, TopicData, AggregateResult, TopicSavePayload, TopicDisposition,
  TopicStatus, TopicOwner, TopicSentiment,
} from "@/types";

type Props = {
  call: Call;
  initialResult: AggregateResult | null;  // from CallTopicsStage state; null = user navigated back
  onValidated: () => void;
};

const BADGE: React.CSSProperties = {
  fontSize: 9, fontWeight: 700, textTransform: "uppercase",
  padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap",
};

// ── Topic card for 3-bucket view ──────────────────────────────────────────────

type BucketType = "followed_up" | "not_discussed" | "new_topics";

type EditableTopic = TopicData & {
  disposition?: TopicDisposition;
  _linkedTopicId?: string | null;
};

function BucketCard({
  topic,
  bucket,
  existingTopics,
  onChange,
  onLink,
  callIsLocked,
}: {
  topic: EditableTopic;
  bucket: BucketType;
  existingTopics: TopicData[];
  onChange: (t: EditableTopic) => void;
  onLink: (topicId: string, topicName: string) => void;
  callIsLocked: boolean;
}) {
  const [showPicker, setShowPicker] = useState(false);
  const [search, setSearch] = useState("");

  const filteredExisting = existingTopics.filter((t) =>
    t.name.toLowerCase().includes(search.toLowerCase())
  );

  const FIELD: React.CSSProperties = {
    width: "100%", fontSize: 11, padding: "4px 6px", borderRadius: 4,
    border: "1px solid #dfe1e6", fontFamily: "inherit",
  };

  return (
    <div style={{
      background: "white", border: "1px solid #dfe1e6", borderRadius: 8, padding: 12,
      display: "flex", flexDirection: "column", gap: 8,
      opacity: callIsLocked ? 0.75 : 1,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <input
          value={topic.name}
          disabled={callIsLocked}
          onChange={(e) => onChange({ ...topic, name: e.target.value })}
          style={{ ...FIELD, fontWeight: 600, fontSize: 13, flex: 1 }}
        />
        {bucket === "new_topics" && !callIsLocked && (
          <button
            onClick={() => setShowPicker((v) => !v)}
            style={{ marginLeft: 8, fontSize: 10, padding: "3px 8px", borderRadius: 4,
              border: "1px solid #b3c6e8", background: "#e9f0ff", color: "#0052cc",
              cursor: "pointer", whiteSpace: "nowrap" }}
          >
            Link to existing →
          </button>
        )}
      </div>

      {showPicker && (
        <div style={{ border: "1px solid #dfe1e6", borderRadius: 6, padding: 8,
          background: "#fafbfc", display: "flex", flexDirection: "column", gap: 6 }}>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search existing topics…"
            autoFocus
            style={{ ...FIELD }}
          />
          <div style={{ maxHeight: 140, overflowY: "auto" }}>
            {filteredExisting.length === 0 && (
              <p style={{ fontSize: 11, color: "#97a0af", padding: 4 }}>No matches</p>
            )}
            {filteredExisting.map((t) => (
              <button
                key={t.topic_id}
                onClick={() => {
                  if (t.topic_id) {
                    onLink(t.topic_id, t.name);
                    setShowPicker(false);
                    setSearch("");
                  }
                }}
                style={{ display: "block", width: "100%", textAlign: "left",
                  padding: "5px 8px", fontSize: 11, border: "none", background: "none",
                  cursor: "pointer", borderRadius: 4, color: "#172b4d" }}
              >
                {t.name}
              </button>
            ))}
          </div>
          <button onClick={() => setShowPicker(false)}
            style={{ fontSize: 10, color: "#97a0af", border: "none", background: "none",
              cursor: "pointer", alignSelf: "flex-start" }}>
            Cancel
          </button>
        </div>
      )}

      <textarea
        value={topic.summary}
        disabled={callIsLocked}
        onChange={(e) => onChange({ ...topic, summary: e.target.value })}
        rows={2}
        style={{ ...FIELD, resize: "vertical" }}
      />

      <div style={{ display: "flex", gap: 8 }}>
        <select value={topic.status} disabled={callIsLocked}
          onChange={(e) => onChange({ ...topic, status: e.target.value as TopicStatus })}
          style={{ ...FIELD, flex: 1 }}>
          <option value="open">Open</option>
          <option value="in_progress">In Progress</option>
          <option value="resolved">Resolved</option>
        </select>
        <select value={topic.owner} disabled={callIsLocked}
          onChange={(e) => onChange({ ...topic, owner: e.target.value as TopicOwner })}
          style={{ ...FIELD, flex: 1 }}>
          <option value="Us">Us</option>
          <option value="Client">Client</option>
          <option value="Both">Both</option>
        </select>
        <select value={topic.sentiment} disabled={callIsLocked}
          onChange={(e) => onChange({ ...topic, sentiment: e.target.value as TopicSentiment })}
          style={{ ...FIELD, flex: 1 }}>
          <option value="positive">Positive</option>
          <option value="neutral">Neutral</option>
          <option value="concern">Concern</option>
        </select>
      </div>

      {bucket === "not_discussed" && !callIsLocked && (
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => onChange({ ...topic, disposition: "keep_as_is" })}
            style={{ flex: 1, padding: "5px", fontSize: 10, borderRadius: 4, cursor: "pointer",
              border: "1px solid", fontWeight: 600,
              background: topic.disposition === "keep_as_is" ? "#e9f0ff" : "white",
              borderColor: topic.disposition === "keep_as_is" ? "#0052cc" : "#dfe1e6",
              color: topic.disposition === "keep_as_is" ? "#0052cc" : "#5e6c84" }}>
            Keep as-is
          </button>
          <button
            onClick={() => onChange({ ...topic, disposition: "archive" })}
            style={{ flex: 1, padding: "5px", fontSize: 10, borderRadius: 4, cursor: "pointer",
              border: "1px solid", fontWeight: 600,
              background: topic.disposition === "archive" ? "#fff4e6" : "white",
              borderColor: topic.disposition === "archive" ? "#ff8b00" : "#dfe1e6",
              color: topic.disposition === "archive" ? "#974f0c" : "#5e6c84" }}>
            Archive
          </button>
        </div>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ProjectTopicsStage({ call, initialResult, onValidated }: Props) {
  const [result, setResult] = useState<AggregateResult | null>(initialResult);
  const [followed, setFollowed] = useState<EditableTopic[]>([]);
  const [notDiscussed, setNotDiscussed] = useState<EditableTopic[]>([]);
  const [newTopics, setNewTopics] = useState<EditableTopic[]>([]);
  const [existingTopics, setExistingTopics] = useState<TopicData[]>([]);
  const [loading, setLoading] = useState(!initialResult);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Populate buckets from result
  useEffect(() => {
    if (!result) return;
    setFollowed((result.followed_up ?? []).map((t) => ({ ...t })));
    setNotDiscussed((result.not_discussed ?? []).map((t) => ({ ...t, disposition: undefined })));
    setNewTopics((result.new_topics ?? []).map((t) => ({ ...t })));
  }, [result]);

  // Load existing project topics for "Link to existing" picker
  useEffect(() => {
    topicsAPI.listForProject(call.project_id)
      .then(setExistingTopics)
      .catch(() => {});
  }, [call.project_id]);

  // If no initialResult (user navigated back), re-run Step 1 + Step 2 automatically
  const reAggregate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      logger.info("Re-running Step 1+2 (state lost)", { component: "ProjectTopicsStage" });
      const step1 = await topicsAPI.extractCall(call.id);
      const step2 = await topicsAPI.aggregate(call.id, step1);
      setResult(step2);
    } catch (err) {
      logger.error("Re-aggregation failed", { component: "ProjectTopicsStage", data: err });
      setError(err instanceof Error ? err.message : "Failed to load topics");
    } finally {
      setLoading(false);
    }
  }, [call.id]);

  useEffect(() => {
    if (!initialResult) {
      reAggregate();
    }
  }, [initialResult, reAggregate]);

  // "Link to existing" — move from new_topics to followed_up with matched topic_id
  function handleLink(newTopicIdx: number, topicId: string, topicName: string) {
    const linked = { ...newTopics[newTopicIdx], topic_id: topicId, name: topicName };
    setFollowed((prev) => [...prev, linked]);
    setNewTopics((prev) => prev.filter((_, i) => i !== newTopicIdx));
  }

  const unacknowledgedCount = notDiscussed.filter((t) => !t.disposition).length;
  const canValidate = !validating && unacknowledgedCount === 0 &&
    (followed.length + notDiscussed.length + newTopics.length) > 0;

  async function handleValidate() {
    setValidating(true);
    setError(null);
    try {
      const allTopics: TopicSavePayload[] = [
        ...followed.map((t) => ({ ...t, topic_id: t.topic_id ?? null, disposition: null })),
        ...notDiscussed.map((t) => ({
          ...t, topic_id: t.topic_id ?? null,
          disposition: (t.disposition ?? null) as TopicDisposition,
        })),
        ...newTopics.map((t) => ({ ...t, topic_id: null, disposition: null })),
      ];
      await topicsAPI.save(call.id, allTopics);
      await topicsAPI.validate(call.id);
      onValidated();
    } catch (err) {
      logger.error("Validate failed", { component: "ProjectTopicsStage", data: err });
      setError(err instanceof Error ? err.message : "Validation failed");
    } finally {
      setValidating(false);
    }
  }

  if (loading) return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <p style={{ fontSize: 13, color: "#5e6c84" }}>Matching topics with project history…</p>
    </div>
  );

  if (error && !result) return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 12 }}>
      <p style={{ fontSize: 13, color: "#ae2a19" }}>{error}</p>
      <button onClick={reAggregate} style={{ fontSize: 12, color: "#0052cc", textDecoration: "underline", border: "none", background: "none", cursor: "pointer" }}>
        Retry
      </button>
    </div>
  );

  const SECTION_HEADER = (label: string, count: number, color: string): React.ReactNode => (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
      <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase",
        letterSpacing: "0.06em", color: "#5e6c84" }}>{label}</span>
      <span style={{ ...BADGE, background: color, color: "white" }}>{count}</span>
    </div>
  );

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", marginBottom: 4 }}>
          Project Topics
        </h2>
        <p style={{ fontSize: 12, color: "#5e6c84", lineHeight: 1.5 }}>
          Step 2 of 2 — Review how this call relates to the project&apos;s topic history.
          Link any missed matches using the &quot;Link to existing&quot; button.
        </p>
      </div>

      {error && (
        <div style={{ background: "#fff1f0", border: "1px solid #ffbdad",
          borderRadius: 6, padding: "10px 14px", fontSize: 12, color: "#ae2a19" }}>
          {error}
        </div>
      )}

      {/* Followed up */}
      {followed.length > 0 && (
        <div>
          {SECTION_HEADER("Followed Up", followed.length, "#36b37e")}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {followed.map((t, i) => (
              <BucketCard key={i} topic={t} bucket="followed_up"
                existingTopics={existingTopics}
                onChange={(u) => { const n = [...followed]; n[i] = u; setFollowed(n); }}
                onLink={() => {}}
                callIsLocked={call.is_locked} />
            ))}
          </div>
        </div>
      )}

      {/* Not discussed */}
      {notDiscussed.length > 0 && (
        <div>
          {SECTION_HEADER("Not Discussed", notDiscussed.length, "#97a0af")}
          <p style={{ fontSize: 11, color: "#97a0af", marginBottom: 8 }}>
            Set a disposition for each topic before validating.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {notDiscussed.map((t, i) => (
              <BucketCard key={i} topic={t} bucket="not_discussed"
                existingTopics={existingTopics}
                onChange={(u) => { const n = [...notDiscussed]; n[i] = u; setNotDiscussed(n); }}
                onLink={() => {}}
                callIsLocked={call.is_locked} />
            ))}
          </div>
        </div>
      )}

      {/* New topics */}
      {newTopics.length > 0 && (
        <div>
          {SECTION_HEADER("New Topics", newTopics.length, "#0052cc")}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {newTopics.map((t, i) => (
              <BucketCard key={i} topic={t} bucket="new_topics"
                existingTopics={existingTopics}
                onChange={(u) => { const n = [...newTopics]; n[i] = u; setNewTopics(n); }}
                onLink={(topicId, topicName) => handleLink(i, topicId, topicName)}
                callIsLocked={call.is_locked} />
            ))}
          </div>
        </div>
      )}

      {/* Validate */}
      {!call.is_locked && (
        <div style={{ paddingTop: 8 }}>
          {unacknowledgedCount > 0 && (
            <p style={{ fontSize: 11, color: "#97a0af", marginBottom: 8 }}>
              {unacknowledgedCount} not-discussed topic{unacknowledgedCount > 1 ? "s" : ""} need a disposition.
            </p>
          )}
          <button
            onClick={handleValidate}
            disabled={!canValidate}
            style={{
              padding: "10px 24px", borderRadius: 6, border: "none", fontSize: 13, fontWeight: 600,
              background: canValidate ? "#36b37e" : "#f4f5f7",
              color: canValidate ? "white" : "#97a0af",
              cursor: canValidate ? "pointer" : "default",
            }}
          >
            {validating ? "Validating…" : "Validate & Continue →"}
          </button>
        </div>
      )}
    </div>
  );
}
