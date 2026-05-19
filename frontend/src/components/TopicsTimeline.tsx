"use client";

import { useCallback, useEffect, useState } from "react";
import { topicsAPI } from "@/api/client";
import type { TopicsTimelineData, TimelineCell, TopicStatus, TopicSentiment, TimelineTopic } from "@/types";
import { resolveProvenance, type CellHistory } from "@/utils/provenance";
import ProvenancePill from "./ProvenancePill";
import KeyTermChips from "./KeyTermChips";
import EvidenceRefPopover from "./EvidenceRefPopover";

type Props = { projectId: string; refreshKey?: number };

// ── Style constants ───────────────────────────────────────────────────────

const STATUS_BADGE: Record<TopicStatus, React.CSSProperties> = {
  open:        { background: "#e9f0ff", color: "#0052cc" },
  in_progress: { background: "#fff4e6", color: "#974f0c" },
  resolved:    { background: "#e3fcef", color: "#006644" },
};

const SENTIMENT_BADGE: Record<TopicSentiment, React.CSSProperties> = {
  positive: { background: "#e3fcef", color: "#006644" },
  neutral:  { background: "#f4f5f7", color: "#5e6c84" },
  concern:  { background: "#fff1f0", color: "#ae2a19" },
};

const BADGE_BASE: React.CSSProperties = {
  fontSize: 9, fontWeight: 700, textTransform: "uppercase",
  padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap",
};

// ── Cell component ────────────────────────────────────────────────────────

function Cell({ cell, hasSources, sourceNames, isFirstRaisedCell, history, calls }: {
  cell: TimelineCell | undefined;
  hasSources?: boolean;
  sourceNames?: string[];
  isFirstRaisedCell?: boolean;
  history?: CellHistory[];
  calls?: Array<{ id: string; call_number: number; title: string }>;
}) {
  const [expanded, setExpanded] = useState(false);

  if (!cell) {
    return <td style={{ width: 180, minWidth: 180, borderRight: "1px solid #f0f1f3", verticalAlign: "top" }} />;
  }

  if (cell.type === "not_discussed") {
    return (
      <td style={{ width: 180, minWidth: 180, borderRight: "1px solid #f0f1f3",
        verticalAlign: "top", textAlign: "center", color: "#bfc5ce",
        fontSize: 13, paddingTop: 14 }}>
        —
      </td>
    );
  }

  if (cell.type === "merged") {
    return (
      <td style={{ width: 180, minWidth: 180, borderRight: "1px solid #f0f1f3",
        verticalAlign: "top", padding: "10px 12px" }}>
        <div style={{
          background: "#f4f5f7", border: "1.5px dashed #97a0af", borderRadius: 5,
          padding: "7px 9px",
        }}>
          <span style={{ ...BADGE_BASE, background: "#97a0af", color: "white" }}>Merged</span>
          {cell.merged_into_name && (
            <div style={{ fontSize: 11, color: "#5e6c84", lineHeight: 1.4, marginTop: 4 }}>
              → {cell.merged_into_name}
            </div>
          )}
        </div>
      </td>
    );
  }

  if (cell.type === "pending") {
    return (
      <td style={{ width: 180, minWidth: 180, borderRight: "1px solid #f0f1f3",
        verticalAlign: "top", padding: "6px 8px" }}>
        <div style={{
          border: "1.5px dashed #c0c8d8",
          borderRadius: 5,
          padding: "7px 9px",
          background: "#fafbfc",
        }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: "#97a0af",
            textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 4 }}>
            Extracted
          </div>
          {cell.summary && (
            <div style={{ fontSize: 11, color: "#5e6c84", lineHeight: 1.4 }}>
              {cell.summary}
            </div>
          )}
        </div>
      </td>
    );
  }

  const isNew = cell.type === "new";
  const isResolved = cell.status === "resolved";
  // Story 10.5: a "new" cell on a topic that is itself a merge result is a "+ new (merged)" cell.
  // Distinct purple palette + tooltip listing source topic names.
  const isMergedNew = isNew && isFirstRaisedCell && !!hasSources;

  const cellStyle: React.CSSProperties = isResolved
    ? { background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 5, padding: "7px 9px" }
    : isMergedNew
      ? { background: "#f5ecff", border: "1px solid #d9c2ff", borderRadius: 5, padding: "7px 9px", cursor: "pointer" }
      : isNew
        ? { background: "#fff7ec", border: "1px solid #ffe0b2", borderRadius: 5, padding: "7px 9px", cursor: "pointer" }
        : { background: "#f0f4ff", border: "1px solid #c0d0f0", borderRadius: 5, padding: "7px 9px", cursor: "pointer" };

  const badgeStyle: React.CSSProperties = isResolved
    ? { ...BADGE_BASE, background: "#006644", color: "white" }
    : isMergedNew
      ? { ...BADGE_BASE, background: "#6f42c1", color: "white" }
      : isNew
        ? { ...BADGE_BASE, background: "#ff8b00", color: "white" }
        : { ...BADGE_BASE, background: "#0052cc", color: "white" };

  const badgeLabel = isResolved
    ? "✓ Resolved"
    : isMergedNew
      ? "✦ New (merged)"
      : isNew
        ? "✦ New"
        : "Updated";
  const tooltip = isMergedNew && sourceNames && sourceNames.length > 0
    ? `Merged from: ${sourceNames.join(", ")}`
    : undefined;
  const canExpand = true;

  return (
    <td style={{ width: 180, minWidth: 180, borderRight: "1px solid #f0f1f3",
      verticalAlign: "top", padding: "10px 12px" }}>
      <div style={cellStyle} onClick={() => canExpand && setExpanded((v) => !v)} title={tooltip}>
        <span style={badgeStyle}>{badgeLabel}</span>

        {cell.summary && (
          <div style={{
            fontSize: 11, color: "#172b4d", lineHeight: 1.45, marginTop: 5,
            display: "-webkit-box", WebkitLineClamp: expanded ? undefined : 2,
            WebkitBoxOrient: "vertical", overflow: expanded ? "visible" : "hidden",
          }}>
            {cell.summary}
          </div>
        )}

        {!expanded && (cell.follow_up_items ?? []).length > 0 && (() => {
          const items = cell.follow_up_items ?? [];
          const origins = history && calls
            ? resolveProvenance(items, history, "follow_up_items")
            : [];
          // Unique call-index set across all items, oldest first
          const callIdxSet = new Set<number>();
          for (const cid of origins) {
            if (!cid || !calls) continue;
            const idx = calls.findIndex((c) => c.id === cid);
            if (idx >= 0) callIdxSet.add(idx);
          }
          const sortedIdxs = Array.from(callIdxSet).sort((a, b) => a - b);
          const originSummary = sortedIdxs.length > 0
            ? ` (${sortedIdxs.map((i) => `C${i + 1}`).join(", ")})`
            : "";
          return (
            <div style={{ fontSize: 10, color: "#5e6c84", marginTop: 4 }}>
              {items.length} follow-up{items.length !== 1 ? "s" : ""}{originSummary}
            </div>
          );
        })()}

        {canExpand && expanded && (
          <div style={{ marginTop: 6, borderTop: "1px solid #dfe1e6", paddingTop: 6 }}>
            {/* EPIC-15: Key terms chips */}
            {(cell.key_terms ?? []).length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <KeyTermChips terms={cell.key_terms ?? []} />
              </div>
            )}

            {/* EPIC-15: Evidence popover */}
            {(cell.evidence ?? []).length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <EvidenceRefPopover evidence={cell.evidence ?? []} />
              </div>
            )}

            {/* EPIC-15: Tasks list */}
            {(cell.tasks ?? []).length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: "#5e6c84", textTransform: "uppercase", letterSpacing: ".05em", marginBottom: 4 }}>
                  Tasks ({(cell.tasks ?? []).length})
                </div>
                {(cell.tasks ?? []).map((task) => (
                  <div key={task.task_id} style={{ fontSize: 11, marginBottom: 4, lineHeight: 1.4 }}>
                    <span style={{ fontWeight: 600 }}>{task.task}</span>
                    <span style={{ color: "#5e6c84" }}> — {task.next_step}</span>
                    {task.owner && <span style={{ color: "#5e6c84" }}> · {task.owner}</span>}
                    <span style={{ ...BADGE_BASE, marginLeft: 6, ...(STATUS_BADGE[task.status as keyof typeof STATUS_BADGE]) }}>{task.status}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Legacy: follow-ups (shown only when present) */}
            {(cell.follow_up_items ?? []).length > 0 && (
              <>
                <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                  color: "#97a0af", marginBottom: 3 }}>Follow-ups</div>
                {(() => {
                  const items = cell.follow_up_items ?? [];
                  const origins = history && calls
                    ? resolveProvenance(items, history, "follow_up_items")
                    : items.map(() => null);
                  return items.map((item, i) => {
                    const originCallId = origins[i];
                    const idx = originCallId && calls
                      ? calls.findIndex((c) => c.id === originCallId)
                      : -1;
                    const title = idx >= 0 && calls
                      ? `Call ${calls[idx].call_number} · ${calls[idx].title}`
                      : null;
                    return (
                      <div key={i} style={{ fontSize: 10, color: "#5e6c84", padding: "1px 0",
                        display: "flex", alignItems: "flex-start", gap: 4 }}>
                        <ProvenancePill callIndex={idx >= 0 ? idx : null} callTitle={title} />
                        <span>{item}</span>
                      </div>
                    );
                  });
                })()}
              </>
            )}
            {/* Legacy: decisions (shown only when present) */}
            {(cell.decisions ?? []).length > 0 && (
              <>
                <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                  color: "#97a0af", marginTop: 6, marginBottom: 3 }}>Decisions</div>
                {(() => {
                  // Adapter: normalise v3 {id,text,...} objects down to plain strings
                  // so resolveProvenance (exact-string match) and <span> render correctly.
                  const decisionTexts = (cell.decisions ?? []).map((d) =>
                    typeof d === "string" ? d : (d.text ?? "")
                  );
                  const origins = history && calls
                    ? resolveProvenance(decisionTexts, history, "decisions")
                    : decisionTexts.map(() => null);
                  return decisionTexts.map((d, i) => {
                    const originCallId = origins[i];
                    const idx = originCallId && calls
                      ? calls.findIndex((c) => c.id === originCallId)
                      : -1;
                    const title = idx >= 0 && calls
                      ? `Call ${calls[idx].call_number} · ${calls[idx].title}`
                      : null;
                    return (
                      <div key={i} style={{ fontSize: 10, color: "#172b4d", padding: "1px 0",
                        display: "flex", alignItems: "flex-start", gap: 4 }}>
                        <ProvenancePill callIndex={idx >= 0 ? idx : null} callTitle={title} />
                        <span>{d}</span>
                      </div>
                    );
                  });
                })()}
              </>
            )}
          </div>
        )}

        {canExpand && (
          <div style={{ fontSize: 9, color: "#97a0af", marginTop: 4 }}>
            {expanded ? "▴ collapse" : "▾ expand"}
          </div>
        )}
      </div>
    </td>
  );
}

// ── Main component ────────────────────────────────────────────────────────

export default function TopicsTimeline({ projectId, refreshKey }: Props) {
  const [data, setData] = useState<TopicsTimelineData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedLineageIds, setExpandedLineageIds] = useState<Set<string>>(new Set());

  function toggleLineage(topicId: string) {
    setExpandedLineageIds((prev) => {
      const next = new Set(prev);
      if (next.has(topicId)) next.delete(topicId);
      else next.add(topicId);
      return next;
    });
  }

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await topicsAPI.timeline(projectId);
      setData(result);
    } catch {
      setError("Failed to load topics timeline.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load, refreshKey]);

  if (loading) return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <p style={{ fontSize: 13, color: "#5e6c84" }}>Loading…</p>
    </div>
  );

  if (error) return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <p style={{ fontSize: 13, color: "#ae2a19" }}>{error}</p>
    </div>
  );

  if (!data || data.calls.length === 0 || data.topics.length === 0) return (
    <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <p style={{ fontSize: 13, color: "#5e6c84" }}>
        {!data || data.calls.length === 0
          ? "No completed calls yet."
          : "No topics defined yet."}
      </p>
    </div>
  );

  const mergeResultCount = data.topics.filter(t => t.has_sources && !t.archived).length;

  // Build an ordered render list: each non-archived topic appears in its
  // original timeline order, followed immediately by its expanded ancestors
  // (in ancestor_topic_ids order). Non-expanded merge-results show only
  // themselves. Orphan archived topics (merged_into null or parent missing)
  // are NOT shown — only ancestors attached to a visible merge-result.
  const topicById: Record<string, TimelineTopic> = Object.fromEntries(
    data.topics.map((t) => [t.topic_id, t])
  );
  const renderTopics: Array<{
    topic: TimelineTopic;
    isAncestorOf: string | null;
    ancestorPosition: "middle" | "last" | null;
  }> = [];
  for (const t of data.topics) {
    if (t.archived) continue;
    renderTopics.push({ topic: t, isAncestorOf: null, ancestorPosition: null });
    if (t.has_sources && expandedLineageIds.has(t.topic_id)) {
      const ancestorIds = t.ancestor_topic_ids ?? [];
      ancestorIds.forEach((aid, idx) => {
        const a = topicById[aid];
        if (!a) return;
        const isLast = idx === ancestorIds.length - 1;
        renderTopics.push({
          topic: a,
          isAncestorOf: t.topic_id,
          ancestorPosition: isLast ? "last" : "middle",
        });
      });
    }
  }

  return (
    <>
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", background: "#f4f5f7" }}>
      {mergeResultCount > 0 && (
        <div style={{ padding: "6px 12px", borderBottom: "1px solid #dfe1e6", background: "#f4f5f7", flexShrink: 0,
          display: "flex", alignItems: "center", gap: 8 }}>
          <button
            onClick={() => {
              // Toggle "expand all lineage": if ANY merge-result row is not yet
              // expanded, expand them all; otherwise collapse all.
              const mergeIds = (data?.topics ?? [])
                .filter((t) => t.has_sources && !t.archived)
                .map((t) => t.topic_id);
              const allExpanded = mergeIds.length > 0 && mergeIds.every((id) => expandedLineageIds.has(id));
              if (allExpanded) {
                setExpandedLineageIds(new Set());
              } else {
                setExpandedLineageIds(new Set(mergeIds));
              }
            }}
            style={{
              fontSize: 11, color: "#5e6c84", background: expandedLineageIds.size > 0 ? "#e9f0ff" : "white",
              border: "1px solid #dfe1e6", borderRadius: 4, padding: "3px 10px",
              cursor: "pointer", fontFamily: "inherit",
            }}
          >
            {expandedLineageIds.size > 0 && expandedLineageIds.size === (data?.topics ?? []).filter((t) => t.has_sources && !t.archived).length
              ? "Collapse all lineage"
              : "Expand all lineage"}
          </button>
        </div>
      )}
    <div style={{ flex: 1, overflow: "auto" }}>
      <table style={{ borderCollapse: "collapse", minWidth: "100%", background: "white" }}>
        <thead>
          <tr>
            <th style={{
              position: "sticky", left: 0, zIndex: 2, background: "#f4f5f7",
              width: 220, minWidth: 220, maxWidth: 220,
              borderRight: "2px solid #dfe1e6", borderBottom: "2px solid #dfe1e6",
              padding: "10px 12px", textAlign: "left",
              fontSize: 10, fontWeight: 700, textTransform: "uppercase",
              letterSpacing: ".05em", color: "#5e6c84",
            }}>
              Topic
            </th>
            {data.calls.map((c) => (
              <th key={c.id} style={{
                width: 180, minWidth: 180, maxWidth: 180,
                background: "#f4f5f7", padding: "10px 12px",
                borderRight: "1px solid #f0f1f3", borderBottom: "2px solid #dfe1e6",
                textAlign: "left", whiteSpace: "nowrap",
              }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "#172b4d", display: "block" }}>
                  Call {c.call_number}
                </span>
                <span style={{
                  fontSize: 10, color: "#97a0af", display: "block",
                  overflow: "hidden", textOverflow: "ellipsis", maxWidth: 156,
                }}>
                  {c.title}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {renderTopics.map(({ topic, isAncestorOf, ancestorPosition }) => {
            const isResolved = topic.status === "resolved";
            const isArchived = topic.archived;
            const isAncestorRow = isAncestorOf !== null;
            const parentName = isAncestorRow ? topicById[isAncestorOf]?.name ?? "" : "";
            // Build per-cell history for provenance resolution. Order by call
            // chronology (matches data.calls order).
            // Normalise v3 DecisionData objects to plain strings so resolveProvenance
            // exact-string match works correctly.
            const topicHistory: CellHistory[] = data.calls.map((c) => ({
              call_id: c.id,
              follow_up_items: topic.call_updates[c.id]?.follow_up_items ?? [],
              decisions: (topic.call_updates[c.id]?.decisions ?? []).map((d) =>
                typeof d === "string" ? d : (d.text ?? "")
              ),
            }));
            return (
              <tr key={topic.topic_id} style={{
                borderBottom: "1px solid #f0f1f3",
                opacity: isArchived ? 0.5 : isResolved ? 0.65 : 1,
              }}>
                <td style={{
                  position: "sticky", left: 0,
                  background: isAncestorRow ? "#fafbfc" : "white",
                  zIndex: 1,
                  width: 220, minWidth: 220, maxWidth: 220,
                  borderRight: "2px solid #dfe1e6",
                  padding: isAncestorRow ? "8px 12px 8px 32px" : "10px 12px",
                  verticalAlign: "top",
                }}>
                  {isAncestorRow && (
                    <span style={{
                      position: "absolute", left: 14, marginTop: 2,
                      color: "#bfc5ce", fontSize: 12, fontFamily: "monospace",
                    }}>
                      {ancestorPosition === "last" ? "└─" : "├─"}
                    </span>
                  )}
                  <div style={{ fontSize: 12, fontWeight: 600, color: "#172b4d", marginBottom: 4,
                    textDecoration: isArchived ? "line-through" : undefined,
                    display: "flex", alignItems: "center", gap: 6 }}>
                    {topic.has_sources && !isArchived ? (
                      <button
                        onClick={(e) => { e.stopPropagation(); toggleLineage(topic.topic_id); }}
                        title={expandedLineageIds.has(topic.topic_id) ? "Collapse ancestor lineage" : "Expand ancestor lineage"}
                        style={{
                          background: "none", border: "none", cursor: "pointer",
                          color: "#5e6c84", padding: 0, fontSize: 11, width: 14,
                          fontFamily: "inherit",
                        }}
                      >
                        {expandedLineageIds.has(topic.topic_id) ? "▾" : "▸"}
                      </button>
                    ) : (
                      <span style={{ width: 14, display: "inline-block" }} />
                    )}
                    <span
                      style={{ textDecoration: isArchived ? "line-through" : undefined }}
                    >
                      {topic.name}
                    </span>
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {isArchived ? (
                      <span style={{ ...BADGE_BASE, background: "#f4f5f7", color: "#97a0af" }}>
                        Archived
                      </span>
                    ) : (
                      <>
                        <span style={{ ...BADGE_BASE, ...(STATUS_BADGE[topic.status] ?? STATUS_BADGE.open) }}>
                          {topic.status.replace("_", " ")}
                        </span>
                        <span style={{ ...BADGE_BASE, ...(SENTIMENT_BADGE[topic.sentiment] ?? SENTIMENT_BADGE.neutral) }}>
                          {topic.sentiment}
                        </span>
                        <span style={{ ...BADGE_BASE, background: "#f4f5f7", color: "#5e6c84" }}>
                          {topic.owner}
                        </span>
                      </>
                    )}
                  </div>
                  {isArchived && topic.merged_into_name && (
                    <div style={{ fontSize: 10, color: "#97a0af", marginTop: 3 }}>
                      → Merged into: {topic.merged_into_name}
                    </div>
                  )}
                </td>
                {data.calls.map((c) => {
                  // Ancestor rows render a special "merged ↗" cell at the merge
                  // call column and "(archived)" text after it.
                  if (isAncestorRow) {
                    if (c.id === topic.merge_call_id) {
                      return (
                        <td key={c.id} style={{
                          width: 180, minWidth: 180, borderRight: "1px solid #f0f1f3",
                          verticalAlign: "top", padding: "8px 12px", background: "#f5ecff",
                        }}>
                          <span style={{
                            ...BADGE_BASE, background: "#6f42c1", color: "white",
                          }}>
                            merged ↗
                          </span>
                          <div style={{ fontSize: 10, color: "#5e6c84", marginTop: 4,
                            fontStyle: "italic", lineHeight: 1.3 }}>
                            → folded into &quot;{parentName}&quot;
                          </div>
                        </td>
                      );
                    }
                    const mergeIdx = data.calls.findIndex((x) => x.id === topic.merge_call_id);
                    const thisIdx = data.calls.findIndex((x) => x.id === c.id);
                    if (mergeIdx >= 0 && thisIdx > mergeIdx) {
                      return (
                        <td key={c.id} style={{
                          width: 180, minWidth: 180, borderRight: "1px solid #f0f1f3",
                          verticalAlign: "top", padding: "8px 12px",
                          color: "#bfc5ce", fontSize: 10, fontStyle: "italic",
                        }}>
                          (archived)
                        </td>
                      );
                    }
                    // Before merge call → fall through to regular Cell rendering
                  }
                  return (
                    <Cell
                      key={c.id}
                      cell={topic.call_updates[c.id]}
                      hasSources={topic.has_sources}
                      sourceNames={topic.source_names}
                      isFirstRaisedCell={c.id === topic.first_raised_call_id}
                      history={topicHistory}
                      calls={data.calls}
                    />
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
    </div>
    </>
  );
}
