"use client";

/* EPIC-17 — Stage 11 review banner.
 * Surfaces 3 sections when call.call_topics_v5_state === "awaiting_review":
 *   - Approvals needed (red, blocking)
 *   - Confidence review (amber, low-confidence tasks)
 *   - Warnings (yellow, informational)
 * "Apply & Continue" submits resolve-review and unblocks Stage 12.
 */

import { useState } from "react";

import { callsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call, CallTopicsV5Payload, NewTopicProposal } from "@/types";

type Props = {
  call: Call;
  onResolved: () => void;
};

type NewTopicDecision = {
  proposed_name: string;
  registry_action: "approve" | "merge" | "reject";
  merge_with_id?: string;
};

export default function CallTopicsReviewBanner({ call, onResolved }: Props) {
  const payload: CallTopicsV5Payload | null = call.call_topics_v5_payload ?? null;
  const review = payload?.review_payload;
  const [newTopicDecisions, setNewTopicDecisions] = useState<Record<string, NewTopicDecision>>({});
  const [acknowledgedWarnings, setAcknowledgedWarnings] = useState<Set<number>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  if (!review) return null;

  const newTopicApprovals = review.approvals_needed.filter((a) => a.type === "new_topic");
  const hardFailures = review.approvals_needed.filter((a) => a.type === "hard_failure_escalation");

  const allNewTopicsDecided =
    newTopicApprovals.length === 0 ||
    newTopicApprovals.every((a) => {
      const name = a.proposal?.proposed_name || "";
      return !!newTopicDecisions[name];
    });

  const handleApply = async () => {
    setSubmitting(true);
    try {
      const decisions = {
        approved_new_topics: Object.values(newTopicDecisions),
        confidence_decisions: review.confidence_review.map((r) => ({
          task_index_path: `${r.topic_name}/${r.task_text}`,
          action: "approve",  // simplified: this UI auto-approves; future: per-task control
        })),
        acknowledged_warnings: Array.from(acknowledgedWarnings),
      };
      await callsAPI.v5ResolveReview(call.id, decisions);
      onResolved();
    } catch (e) {
      logger.error("[CallTopicsReviewBanner] resolve failed", { data: e });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        margin: "12px 20px",
        padding: 16,
        border: "1px solid #ffbdad",
        background: "#fff8f7",
        borderRadius: 6,
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 700, color: "#ae2a19", marginBottom: 8 }}>
        ⏸ Pipeline paused — Stage 11 review
      </div>
      <div style={{ fontSize: 11, color: "#5e6c84", marginBottom: 12 }}>
        Pipeline ran through Stage 10 and surfaced items for your review. Resolve below to unblock Stage 12 (final output).
      </div>

      {/* Approvals needed — new topic proposals */}
      {newTopicApprovals.length > 0 && (
        <Section title="Approvals needed — new topic proposals" color="#ae2a19">
          {newTopicApprovals.map((a, i) => {
            const prop = a.proposal as NewTopicProposal;
            const name = prop.proposed_name;
            const decision = newTopicDecisions[name];
            return (
              <div key={i} style={proposalBox}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#172b4d" }}>
                  {name}
                  <span style={{ marginLeft: 8, color: "#5e6c84", fontWeight: 400 }}>
                    ({prop.unit_ids.length} units · importance: {prop.importance})
                  </span>
                </div>
                {prop.suggested_match_name && (
                  <div style={{ fontSize: 10, color: "#974f0c", marginTop: 4 }}>
                    Suggested merge target: <strong>{prop.suggested_match_name}</strong>
                    (Jaccard {prop.lexical_similarity_to_existing})
                  </div>
                )}
                <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                  <button
                    type="button"
                    onClick={() =>
                      setNewTopicDecisions((prev) => ({
                        ...prev,
                        [name]: { proposed_name: name, registry_action: "approve" },
                      }))
                    }
                    style={pillBtn(decision?.registry_action === "approve", "#36b37e")}
                  >
                    ✓ Approve new
                  </button>
                  {prop.suggested_match_id && (
                    <button
                      type="button"
                      onClick={() =>
                        setNewTopicDecisions((prev) => ({
                          ...prev,
                          [name]: {
                            proposed_name: name,
                            registry_action: "merge",
                            merge_with_id: prop.suggested_match_id!,
                          },
                        }))
                      }
                      style={pillBtn(decision?.registry_action === "merge", "#0052cc")}
                    >
                      ↻ Merge with &quot;{prop.suggested_match_name}&quot;
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() =>
                      setNewTopicDecisions((prev) => ({
                        ...prev,
                        [name]: { proposed_name: name, registry_action: "reject" },
                      }))
                    }
                    style={pillBtn(decision?.registry_action === "reject", "#bf2600")}
                  >
                    ✗ Reject
                  </button>
                </div>
              </div>
            );
          })}
        </Section>
      )}

      {/* Hard failure escalations */}
      {hardFailures.length > 0 && (
        <Section title={`Hard validation failures (${hardFailures.length} — escalated)`} color="#ae2a19">
          {hardFailures.map((a, i) => {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const f = a.failure as any;
            const code = f?.code as string;
            const isOrphan = code === "H3_orphan_units";
            const isFewCit = code === "H1_too_few_citations";
            return (
              <div key={i} style={proposalBox}>
                <div style={{ fontSize: 11, color: "#ae2a19", fontWeight: 700 }}>
                  {code}
                </div>
                <div style={{ fontSize: 11, color: "#42526e", marginTop: 4, lineHeight: 1.5 }}>
                  {f?.message}
                </div>

                {/* H3 — show the actual orphan units */}
                {isOrphan && f?.details?.orphan_units && (
                  <ul style={{ marginTop: 6, marginBottom: 0, paddingLeft: 18, fontSize: 11, color: "#5e6c84" }}>
                    {(f.details.orphan_units as Array<{ unit_id: string; type: string; text: string; owner: string; lines: number[]; citation: string }>).map((u) => (
                      <li key={u.unit_id} style={{ marginBottom: 4 }}>
                        <span style={{ fontFamily: "ui-monospace, SFMono-Regular, monospace", color: "#974f0c" }}>
                          {u.type}
                        </span>{" — "}
                        <span style={{ color: "#172b4d" }}>{u.text}</span>
                        <div style={{ fontSize: 10, color: "#97a0af", marginTop: 2 }}>
                          {u.owner} · lines {u.lines?.[0]}-{u.lines?.[1]}: <em>&ldquo;{u.citation}&rdquo;</em>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}

                {/* H1 — task name + topic + preview of the 1 citation */}
                {isFewCit && (
                  <div style={{ marginTop: 6, fontSize: 11, color: "#5e6c84" }}>
                    Topic: <strong>{f?.topic}</strong> · Task: <strong>{f?.task}</strong>
                    {f?.first_citation_preview && (
                      <div style={{ marginTop: 4, fontStyle: "italic", color: "#42526e" }}>
                        Only citation: &ldquo;{f.first_citation_preview}&rdquo;
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
          <div style={{ fontSize: 10, color: "#5e6c84", marginTop: 4, fontStyle: "italic" }}>
            Apply &amp; Continue will accept these failures and let the run complete with the
            data as-is. To fix properly, you&apos;d need to re-run extraction or manually edit
            the topics after they appear in the table.
          </div>
        </Section>
      )}

      {/* Confidence review */}
      {review.confidence_review.length > 0 && (
        <Section title="Confidence review (low-confidence tasks)" color="#974f0c">
          {review.confidence_review.map((r, i) => (
            <div key={i} style={proposalBox}>
              <div style={{ fontSize: 12, color: "#172b4d" }}>
                <strong>{r.topic_name}</strong> · {r.task_text}
                <span style={{ marginLeft: 8, color: "#974f0c", fontWeight: 600 }}>
                  conf {r.score.toFixed(2)}
                </span>
              </div>
            </div>
          ))}
        </Section>
      )}

      {/* Warnings */}
      {review.warnings.length > 0 && (
        <Section title={`Warnings (${review.warnings.length})`} color="#7a4f00">
          {review.warnings.map((w, i) => {
            const acked = acknowledgedWarnings.has(i);
            return (
              <div key={i} style={{ ...proposalBox, opacity: acked ? 0.5 : 1 }}>
                <div style={{ fontSize: 11, color: "#7a4f00", fontWeight: 600 }}>
                  {w.code}
                  {w.topic && <span style={{ color: "#5e6c84", marginLeft: 6 }}>· {w.topic}</span>}
                </div>
                <div style={{ fontSize: 11, color: "#42526e", marginTop: 2 }}>{w.message}</div>
                <button
                  type="button"
                  onClick={() => {
                    setAcknowledgedWarnings((prev) => {
                      const next = new Set(prev);
                      next.has(i) ? next.delete(i) : next.add(i);
                      return next;
                    });
                  }}
                  style={{
                    marginTop: 4,
                    fontSize: 10,
                    padding: "2px 8px",
                    border: "1px solid #c1c7d0",
                    borderRadius: 3,
                    background: acked ? "#deebff" : "white",
                    cursor: "pointer",
                  }}
                >
                  {acked ? "✓ Acknowledged" : "Acknowledge"}
                </button>
              </div>
            );
          })}
        </Section>
      )}

      <div style={{ marginTop: 12, display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <button
          type="button"
          disabled={!allNewTopicsDecided || submitting}
          onClick={handleApply}
          style={{
            fontSize: 12,
            padding: "6px 16px",
            background: allNewTopicsDecided && !submitting ? "#0052cc" : "#c1c7d0",
            color: "white",
            border: "none",
            borderRadius: 4,
            cursor: allNewTopicsDecided && !submitting ? "pointer" : "default",
            fontWeight: 600,
          }}
        >
          {submitting ? "Applying…" : "Apply & Continue"}
        </button>
      </div>
    </div>
  );
}

function Section({ title, color, children }: { title: string; color: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color, marginBottom: 4 }}>
        {title}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>{children}</div>
    </div>
  );
}

const proposalBox: React.CSSProperties = {
  padding: 8,
  background: "white",
  border: "1px solid #ebecf0",
  borderRadius: 4,
};

function pillBtn(selected: boolean, color: string): React.CSSProperties {
  return {
    fontSize: 10,
    padding: "4px 10px",
    border: `1px solid ${selected ? color : "#c1c7d0"}`,
    borderRadius: 12,
    background: selected ? color : "white",
    color: selected ? "white" : color,
    cursor: "pointer",
    fontWeight: 600,
  };
}
