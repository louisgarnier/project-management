"use client";

import { useState } from "react";
import { topicsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call, TopicData, TopicSavePayload, TopicDisposition, ExtractionResult } from "@/types";
import PreCallBrief from "@/components/PreCallBrief";
import TopicEditor from "@/components/TopicEditor";
import AddTopicForm from "@/components/AddTopicForm";

type Phase = "choice" | "extracting" | "reviewing" | "manual" | "validating";

type Props = {
  call: Call;
  onAdvance: () => void;
};

// Each editable topic in state, tagged with its bucket
type EditableTopic = TopicData & {
  _bucket: "followed_up" | "not_discussed" | "new" | "manual";
  _disposition: TopicDisposition;
  _key: string; // stable local key for list rendering
};

let _keyCounter = 0;
function mkKey() { return String(++_keyCounter); }

function wrapTopics(
  topics: TopicData[],
  bucket: EditableTopic["_bucket"]
): EditableTopic[] {
  return topics.map((t) => ({ ...t, _bucket: bucket, _disposition: null, _key: mkKey() }));
}

export default function TopicsStage({ call, onAdvance }: Props) {
  const [phase, setPhase]     = useState<Phase>("choice");
  const [topics, setTopics]   = useState<EditableTopic[]>([]);
  const [callNumber, setCallNumber] = useState(1);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [validateError, setValidateError] = useState<string | null>(null);

  // ── Extract ──────────────────────────────────────────────────────────────
  async function handleExtract() {
    setPhase("extracting");
    setExtractError(null);
    try {
      logger.info("Extracting topics", { component: "TopicsStage", data: { callId: call.id } });
      const result: ExtractionResult = await topicsAPI.extract(call.id);
      setCallNumber(result.call_number);
      setTopics([
        ...wrapTopics(result.followed_up, "followed_up"),
        ...wrapTopics(result.not_discussed, "not_discussed"),
        ...wrapTopics(result.new_topics, "new"),
      ]);
      setPhase("reviewing");
    } catch (err) {
      logger.error("Extraction failed", { component: "TopicsStage", data: err });
      setExtractError("Extraction failed. Please try again.");
      setPhase("choice");
    }
  }

  // ── Manual mode ──────────────────────────────────────────────────────────
  function handleManual() {
    setTopics([]);
    setPhase("manual");
  }

  // ── Topic mutations ───────────────────────────────────────────────────────
  function updateTopic(key: string, updated: TopicData) {
    setTopics((prev) => prev.map((t) => t._key === key ? { ...t, ...updated } : t));
  }

  function setDisposition(key: string, d: TopicDisposition) {
    setTopics((prev) => prev.map((t) => t._key === key ? { ...t, _disposition: d } : t));
  }

  function removeTopic(key: string) {
    setTopics((prev) => prev.filter((t) => t._key !== key));
  }

  function addTopic(topic: TopicData) {
    setTopics((prev) => [...prev, {
      ...topic, _bucket: "manual", _disposition: null, _key: mkKey(),
    }]);
  }

  // ── Validate gate ─────────────────────────────────────────────────────────
  const unacknowledgedCount = topics.filter(
    (t) => t._bucket === "not_discussed" && t._disposition === null
  ).length;
  const canValidate = topics.length > 0 && unacknowledgedCount === 0;

  // ── Validate & Complete ───────────────────────────────────────────────────
  async function handleValidate() {
    setPhase("validating");
    setValidateError(null);
    try {
      const payload: TopicSavePayload[] = topics.map((t) => ({
        topic_id: t.topic_id ?? null,
        name: t.name,
        summary: t.summary,
        follow_up_items: t.follow_up_items,
        decisions: t.decisions,
        status: t.status,
        owner: t.owner,
        sentiment: t.sentiment,
        calls_open: t.calls_open,
        disposition: t._disposition,
      }));
      await topicsAPI.save(call.id, payload);
      await topicsAPI.validate(call.id);
      logger.info("Call validated → done", { component: "TopicsStage", data: { callId: call.id } });
      onAdvance();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Validation failed.";
      logger.error("Validation failed", { component: "TopicsStage", data: err });
      setValidateError(msg);
      setPhase("reviewing");
    }
  }

  // ── Buckets for rendering ─────────────────────────────────────────────────
  const followedUp   = topics.filter((t) => t._bucket === "followed_up");
  const notDiscussed = topics.filter((t) => t._bucket === "not_discussed");
  const newTopics    = topics.filter((t) => t._bucket === "new");
  const manualTopics = topics.filter((t) => t._bucket === "manual");

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div>
      <PreCallBrief callId={call.id} />

      {/* Choice screen */}
      {phase === "choice" && (
        <>
          {extractError && (
            <div style={{ background: "#fff1f0", border: "1px solid #ffc2c2", borderRadius: 6,
              padding: "10px 14px", marginBottom: 16, fontSize: 12, color: "#ae2a19" }}>
              {extractError}
            </div>
          )}
          <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
            <button onClick={handleExtract}
              style={{ flex: 1, background: "white", border: "1.5px solid #dfe1e6",
                borderRadius: 10, padding: 16, cursor: "pointer", textAlign: "left" }}>
              <div style={{ fontSize: 20, marginBottom: 8 }}>✨</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#172b4d", marginBottom: 4 }}>
                Extract via Claude
              </div>
              <div style={{ fontSize: 11, color: "#5e6c84", lineHeight: 1.5 }}>
                Claude reads the transcript and surfaces topics automatically. Review and edit before saving.
              </div>
            </button>
            <button onClick={handleManual}
              style={{ flex: 1, background: "white", border: "1.5px solid #dfe1e6",
                borderRadius: 10, padding: 16, cursor: "pointer", textAlign: "left" }}>
              <div style={{ fontSize: 20, marginBottom: 8 }}>✏️</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#172b4d", marginBottom: 4 }}>
                Add Manually
              </div>
              <div style={{ fontSize: 11, color: "#5e6c84", lineHeight: 1.5 }}>
                Start with a blank list and enter topics yourself.
              </div>
            </button>
          </div>
        </>
      )}

      {/* Spinner */}
      {phase === "extracting" && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 48 }}>
          <p style={{ fontSize: 13, color: "#5e6c84" }}>Extracting topics…</p>
        </div>
      )}

      {/* Three-bucket review (Call 2+) or flat list (Call 1) */}
      {(phase === "reviewing" || phase === "validating") && (
        <>
          {callNumber > 1 ? (
            <>
              {/* Section label */}
              <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase",
                letterSpacing: "0.06em", color: "#97a0af", marginBottom: 10 }}>
                Topics — {followedUp.length} followed-up · {notDiscussed.length} not discussed · {newTopics.length} new
              </div>

              {/* Bucket: Followed-up */}
              {followedUp.length > 0 && (
                <Bucket title="Followed-up" count={followedUp.length} variant="normal">
                  {followedUp.map((t) => (
                    <TopicEditor key={t._key} topic={t} bucket="followed_up"
                      disposition={t._disposition}
                      onUpdate={(u) => updateTopic(t._key, u)}
                      onDisposition={(d) => setDisposition(t._key, d)}
                      onRemove={() => removeTopic(t._key)} />
                  ))}
                  <AddTopicForm onAdd={addTopic} />
                </Bucket>
              )}

              {/* Bucket: Not discussed */}
              {notDiscussed.length > 0 && (
                <Bucket title="⚠ Not discussed this call" count={notDiscussed.length} variant="amber">
                  <div style={{ fontSize: 10, color: "#974f0c", background: "#fff4e6",
                    padding: "6px 14px", borderBottom: "1px solid #ffe0a0" }}>
                    Set a disposition for each topic before validating.
                  </div>
                  {notDiscussed.map((t) => (
                    <TopicEditor key={t._key} topic={t} bucket="not_discussed"
                      disposition={t._disposition}
                      onUpdate={(u) => updateTopic(t._key, u)}
                      onDisposition={(d) => setDisposition(t._key, d)}
                      onRemove={() => removeTopic(t._key)} />
                  ))}
                </Bucket>
              )}

              {/* Bucket: New */}
              {newTopics.length > 0 && (
                <Bucket title="New this call" count={newTopics.length} variant="blue">
                  {newTopics.map((t) => (
                    <TopicEditor key={t._key} topic={t} bucket="new"
                      disposition={t._disposition}
                      onUpdate={(u) => updateTopic(t._key, u)}
                      onDisposition={(d) => setDisposition(t._key, d)}
                      onRemove={() => removeTopic(t._key)} />
                  ))}
                  <AddTopicForm onAdd={addTopic} />
                </Bucket>
              )}
            </>
          ) : (
            /* Call 1: flat list */
            <div style={{ background: "white", border: "1px solid #dfe1e6", borderRadius: 8, marginBottom: 12 }}>
              <div style={{ padding: "10px 14px", borderBottom: "1px solid #f4f5f7",
                fontSize: 11, fontWeight: 700, color: "#172b4d" }}>
                Topics ({topics.length})
              </div>
              {topics.map((t) => (
                <TopicEditor key={t._key} topic={t} bucket="followed_up"
                  disposition={t._disposition}
                  onUpdate={(u) => updateTopic(t._key, u)}
                  onDisposition={(d) => setDisposition(t._key, d)}
                  onRemove={() => removeTopic(t._key)} />
              ))}
              <AddTopicForm onAdd={addTopic} />
            </div>
          )}

          {/* Action bar */}
          <ActionBar
            unacknowledged={unacknowledgedCount}
            canValidate={canValidate}
            validating={phase === "validating"}
            error={validateError}
            onValidate={handleValidate}
          />
        </>
      )}

      {/* Manual mode */}
      {phase === "manual" && (
        <>
          <div style={{ background: "white", border: "1px solid #dfe1e6", borderRadius: 8, marginBottom: 12 }}>
            <div style={{ padding: "10px 14px", borderBottom: "1px solid #f4f5f7",
              fontSize: 11, fontWeight: 700, color: "#172b4d" }}>
              Topics ({manualTopics.length})
            </div>
            {manualTopics.map((t) => (
              <TopicEditor key={t._key} topic={t} bucket="followed_up"
                disposition={t._disposition}
                onUpdate={(u) => updateTopic(t._key, u)}
                onDisposition={(d) => setDisposition(t._key, d)}
                onRemove={() => removeTopic(t._key)} />
            ))}
            <AddTopicForm onAdd={addTopic} />
          </div>
          <ActionBar
            unacknowledged={0}
            canValidate={manualTopics.length > 0}
            validating={false}
            error={validateError}
            onValidate={handleValidate}
          />
        </>
      )}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

type BucketVariant = "normal" | "amber" | "blue";

const BUCKET_HEADER: Record<BucketVariant, React.CSSProperties> = {
  normal: {},
  amber:  { background: "#fffbf0", borderBottom: "1px solid #ffe0a0" },
  blue:   { background: "#f0f7ff" },
};
const BUCKET_TITLE_COLOR: Record<BucketVariant, string> = {
  normal: "#172b4d",
  amber:  "#974f0c",
  blue:   "#0052cc",
};
const BUCKET_COUNT_STYLE: Record<BucketVariant, React.CSSProperties> = {
  normal: { background: "#dfe1e6", color: "#5e6c84" },
  amber:  { background: "#fff4e6", color: "#974f0c" },
  blue:   { background: "#e9f0ff", color: "#0052cc" },
};

function Bucket({ title, count, variant, children }: {
  title: string; count: number; variant: BucketVariant; children: React.ReactNode;
}) {
  return (
    <div style={{ background: "white", border: "1px solid #dfe1e6",
      borderRadius: 8, marginBottom: 12, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8,
        padding: "10px 14px", ...BUCKET_HEADER[variant] }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: BUCKET_TITLE_COLOR[variant] }}>{title}</span>
        <span style={{ fontSize: 9, fontWeight: 700, padding: "1px 6px", borderRadius: 10,
          ...BUCKET_COUNT_STYLE[variant] }}>{count}</span>
      </div>
      {children}
    </div>
  );
}

function ActionBar({ unacknowledged, canValidate, validating, error, onValidate }: {
  unacknowledged: number;
  canValidate: boolean;
  validating: boolean;
  error: string | null;
  onValidate: () => void;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
      background: "white", border: "1px solid #dfe1e6", borderRadius: 8,
      padding: "12px 16px", marginTop: 16 }}>
      <div>
        {error && (
          <span style={{ fontSize: 11, color: "#ae2a19", background: "#fff1f0",
            padding: "5px 10px", borderRadius: 4 }}>{error}</span>
        )}
        {!error && unacknowledged > 0 && (
          <span style={{ fontSize: 11, color: "#ae2a19", background: "#fff1f0",
            padding: "5px 10px", borderRadius: 4 }}>
            {unacknowledged} topic{unacknowledged > 1 ? "s need" : " needs"} a disposition before validating
          </span>
        )}
      </div>
      <button onClick={onValidate} disabled={!canValidate || validating}
        style={{ fontSize: 13, fontWeight: 700,
          background: canValidate && !validating ? "#36b37e" : "#dfe1e6",
          color: canValidate && !validating ? "white" : "#97a0af",
          border: "none", padding: "9px 20px", borderRadius: 6,
          cursor: canValidate && !validating ? "pointer" : "not-allowed" }}>
        {validating ? "Saving…" : "Validate & Complete Call →"}
      </button>
    </div>
  );
}
