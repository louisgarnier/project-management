"use client";

// EPIC-20 Stage 1: Topic confirmation.
// User decides which topics are alive for this call BEFORE task matching.
// Output = call_finalized_topics rows that drive the rest of the pipeline.

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  topicConfirmationAPI,
  type ExistingTopicEntry,
  type NewTopicCandidate,
  type FinalizedTopic,
} from "@/api/client";
import { logger } from "@/utils/logger";

type Props = {
  callId: string;
  onAdvance: () => void;
};

export default function TopicConfirmationStage({ callId, onAdvance }: Props) {
  const [existing, setExisting] = useState<ExistingTopicEntry[]>([]);
  const [candidates, setCandidates] = useState<NewTopicCandidate[]>([]);
  const [finalized, setFinalized] = useState<FinalizedTopic[]>([]);
  const [callStage, setCallStage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const STAGE_ORDER = ["transcript", "call_topics", "topic_confirmation", "project_matching", "project_updates", "artifacts", "done"];
  const isPastStage = callStage !== null && STAGE_ORDER.indexOf(callStage) > STAGE_ORDER.indexOf("topic_confirmation");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    topicConfirmationAPI
      .load(callId)
      .then((d) => {
        if (!alive) return;
        setExisting(d.existing);
        setCandidates(d.new_candidates);
        setCallStage(d.kanban_stage);
        if (d.finalized.length > 0) {
          setFinalized(d.finalized);
        } else {
          // Default: pre-select all existing topics + all new candidates so user can de-select
          const seedExisting: FinalizedTopic[] = d.existing.map((t) => ({
            name: t.name,
            source: "existing",
            topic_id: t.topic_id,
            _original_name: t.name,
          }));
          const seedNew: FinalizedTopic[] = d.new_candidates.map((c) => ({
            name: c.name,
            source: "new",
            topic_id: null,
            v5_cluster_id: c.v5_cluster_id,
          }));
          setFinalized([...seedExisting, ...seedNew]);
        }
      })
      .catch((e) => {
        if (!alive) return;
        logger.error("Topic confirmation load failed", { component: "TopicConfirmationStage", data: e });
        setError(e instanceof Error ? e.message : "Load failed");
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [callId]);

  const finalizedNamesLower = useMemo(
    () => new Set(finalized.map((f) => f.name.toLowerCase())),
    [finalized],
  );
  const isKept = (topicId: string) => finalized.some((f) => f.topic_id === topicId);
  const isAccepted = (name: string) =>
    finalized.some((f) => f.source === "new" && f.name.toLowerCase() === name.toLowerCase());

  const toggleExisting = (t: ExistingTopicEntry) => {
    if (isKept(t.topic_id)) {
      setFinalized((arr) => arr.filter((f) => f.topic_id !== t.topic_id));
    } else {
      setFinalized((arr) => [
        ...arr,
        { name: t.name, source: "existing", topic_id: t.topic_id, _original_name: t.name },
      ]);
    }
  };

  const toggleCandidate = (c: NewTopicCandidate) => {
    if (isAccepted(c.name)) {
      setFinalized((arr) =>
        arr.filter((f) => !(f.source === "new" && f.name.toLowerCase() === c.name.toLowerCase())),
      );
    } else {
      setFinalized((arr) => [
        ...arr,
        { name: c.name, source: "new", topic_id: null, v5_cluster_id: c.v5_cluster_id },
      ]);
    }
  };

  const renameAt = (idx: number, newName: string) => {
    setFinalized((arr) => arr.map((f, i) => (i === idx ? { ...f, name: newName } : f)));
  };

  const removeAt = (idx: number) => {
    setFinalized((arr) => arr.filter((_, i) => i !== idx));
  };

  const introduceTopic = () => {
    const name = window.prompt("New topic name?");
    if (!name || !name.trim()) return;
    const clean = name.trim();
    if (finalizedNamesLower.has(clean.toLowerCase())) {
      window.alert("A topic with this name is already in the list.");
      return;
    }
    setFinalized((arr) => [...arr, { name: clean, source: "new", topic_id: null }]);
  };

  const save = useCallback(async () => {
    if (finalized.length === 0) {
      setError("At least one topic is required before advancing.");
      return;
    }
    // Reject empty names + duplicates
    const seen = new Set<string>();
    for (const f of finalized) {
      const n = f.name.trim().toLowerCase();
      if (!n) {
        setError("Empty topic name — fix or remove.");
        return;
      }
      if (seen.has(n)) {
        setError(`Duplicate topic name: "${f.name}"`);
        return;
      }
      seen.add(n);
    }
    setSaving(true);
    setError(null);
    try {
      await topicConfirmationAPI.save(callId, finalized);
      onAdvance();
    } catch (e) {
      logger.error("Topic confirmation save failed", { component: "TopicConfirmationStage", data: e });
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [callId, finalized, onAdvance]);

  if (loading) return <div style={{ padding: 24 }}>Loading topics…</div>;

  return (
    <div style={{ padding: 16, maxWidth: 1400, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>Confirm topics for this call</h2>
        <div style={{ fontSize: 13, color: "#5e6c84" }}>
          Decide which topics are alive going forward. Existing topics not kept will be archived.
        </div>
      </div>

      {error && (
        <div
          style={{
            background: "#ffd6cc",
            border: "1px solid #cc5500",
            color: "#7a2200",
            padding: "8px 12px",
            borderRadius: 4,
            marginBottom: 12,
          }}
        >
          {error}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
        <Column title={`Existing project topics (${existing.length})`} subtitle="From prior calls">
          {existing.length === 0 ? (
            <Empty msg="No prior topics — this is the first call." />
          ) : (
            existing.map((t) => (
              <Row
                key={t.topic_id}
                label={`${t.name}`}
                hint={`${t.tasks_count} task${t.tasks_count === 1 ? "" : "s"}`}
                checked={isKept(t.topic_id)}
                onToggle={() => toggleExisting(t)}
              />
            ))
          )}
        </Column>

        <Column title={`New from this call (${candidates.length})`} subtitle="v5 clustering proposals">
          {candidates.length === 0 ? (
            <Empty msg="v5 produced no new topic candidates." />
          ) : (
            candidates.map((c) => (
              <Row
                key={c.name}
                label={c.name}
                hint={`${c.task_count} task${c.task_count === 1 ? "" : "s"}`}
                checked={isAccepted(c.name)}
                onToggle={() => toggleCandidate(c)}
              />
            ))
          )}
          <button onClick={introduceTopic} style={addBtn}>
            + Introduce a topic manually
          </button>
        </Column>

        <Column
          title={`Finalized list (${finalized.length})`}
          subtitle="Edit names inline; renames propagate to topic_registry"
        >
          {finalized.length === 0 ? (
            <Empty msg="Toggle topics on the left to add them." />
          ) : (
            finalized.map((f, i) => (
              <div key={`${f.source}-${f.topic_id ?? f.name}-${i}`} style={finalRow}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span
                    style={{
                      ...badge,
                      background: f.source === "existing" ? "#cce5ff" : "#d4f0d4",
                      color: f.source === "existing" ? "#0747a6" : "#197d23",
                    }}
                  >
                    {f.source === "existing" ? "kept" : "new"}
                  </span>
                  <input
                    value={f.name}
                    onChange={(e) => renameAt(i, e.target.value)}
                    style={nameInput}
                    placeholder="Topic name"
                  />
                  <button
                    onClick={() => removeAt(i)}
                    title="Remove from finalized list"
                    style={removeBtn}
                  >
                    ×
                  </button>
                </div>
                {f._original_name && f._original_name !== f.name && (
                  <div style={{ fontSize: 11, color: "#974f0c", marginLeft: 46 }}>
                    will rename: &quot;{f._original_name}&quot; → &quot;{f.name}&quot;
                  </div>
                )}
              </div>
            ))
          )}
          <button
            disabled={saving || finalized.length === 0 || isPastStage}
            onClick={save}
            title={isPastStage ? "This call is already past topic confirmation. Use rollback to edit." : undefined}
            style={{
              ...saveBtn,
              opacity: saving || finalized.length === 0 || isPastStage ? 0.5 : 1,
              cursor: saving || finalized.length === 0 || isPastStage ? "not-allowed" : "pointer",
            }}
          >
            {saving
              ? "Saving…"
              : isPastStage
                ? `🔒 Already past — rollback to edit (${finalized.length})`
                : `Save & advance to project matching (${finalized.length})`}
          </button>
        </Column>
      </div>
    </div>
  );
}

// ── sub-components ───────────────────────────────────────────────────────────

function Column({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ background: "#f7f8fa", padding: 12, borderRadius: 6, border: "1px solid #e1e4e8" }}>
      <div style={{ marginBottom: 10 }}>
        <h3 style={{ margin: 0, fontSize: 15 }}>{title}</h3>
        {subtitle && (
          <div style={{ fontSize: 11, color: "#5e6c84", marginTop: 2 }}>{subtitle}</div>
        )}
      </div>
      {children}
    </div>
  );
}

function Row({
  label,
  hint,
  checked,
  onToggle,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        marginBottom: 6,
        padding: "6px 8px",
        background: checked ? "#fff" : "transparent",
        borderRadius: 4,
        cursor: "pointer",
        border: checked ? "1px solid #cce5ff" : "1px solid transparent",
      }}
    >
      <input type="checkbox" checked={checked} onChange={onToggle} />
      <span style={{ flex: 1, fontSize: 13 }}>{label}</span>
      {hint && <span style={{ fontSize: 11, color: "#5e6c84" }}>{hint}</span>}
    </label>
  );
}

function Empty({ msg }: { msg: string }) {
  return <div style={{ color: "#5e6c84", fontSize: 12, padding: 8, fontStyle: "italic" }}>{msg}</div>;
}

// ── styles ───────────────────────────────────────────────────────────────────

const addBtn: React.CSSProperties = {
  marginTop: 8,
  padding: "6px 10px",
  background: "transparent",
  border: "1px dashed #5e6c84",
  borderRadius: 4,
  cursor: "pointer",
  fontSize: 12,
  width: "100%",
};

const finalRow: React.CSSProperties = {
  marginBottom: 6,
  padding: "4px 0",
};

const badge: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  padding: "2px 6px",
  borderRadius: 10,
  textTransform: "uppercase",
  letterSpacing: ".04em",
};

const nameInput: React.CSSProperties = {
  flex: 1,
  padding: "4px 8px",
  border: "1px solid #c1c7d0",
  borderRadius: 3,
  fontSize: 13,
  minWidth: 0,
};

const removeBtn: React.CSSProperties = {
  background: "transparent",
  border: "none",
  color: "#5e6c84",
  fontSize: 18,
  lineHeight: 1,
  cursor: "pointer",
  padding: "0 6px",
};

const saveBtn: React.CSSProperties = {
  marginTop: 12,
  padding: "8px 12px",
  width: "100%",
  background: "#0747a6",
  color: "#fff",
  border: "none",
  borderRadius: 4,
  fontWeight: 600,
  fontSize: 13,
};
