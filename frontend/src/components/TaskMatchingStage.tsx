"use client";

import React, { useState, useEffect, useMemo } from 'react';
import { TaskCard } from './TaskCard';
import { CrossTopicBindingModal } from './CrossTopicBindingModal';
import type { TaskMatchGroup, TaskRef } from '@/types';
import { topicsAPI } from '@/api/client';

// ── Color palette ─────────────────────────────────────────────────────────────

const GROUP_COLORS = [
  { bg: "#e9f0ff", border: "#4c9aff", text: "#0052cc" },  // blue
  { bg: "#e3fcef", border: "#57d9a3", text: "#006644" },  // green
  { bg: "#fce4fa", border: "#cc57c5", text: "#6b2066" },  // purple
  { bg: "#ffe8d6", border: "#ff8b00", text: "#bf4300" },  // orange
  { bg: "#e6fcff", border: "#00b8d9", text: "#00668c" },  // cyan
  { bg: "#ffd6d6", border: "#ff5630", text: "#ae2a19" },  // red
];

function groupColor(idx: number) {
  return GROUP_COLORS[idx % GROUP_COLORS.length];
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface ExistingTopic {
  topic_id: string;
  name: string;
  tasks: Array<{ task_id: string; task: string; next_step?: string; owner?: string; key_terms?: string[] }>;
}

interface CandidateTopic {
  name: string;
  tasks: Array<{ task_id: string; task: string; next_step?: string; owner?: string; key_terms?: string[] }>;
}

interface Props {
  callId: string;
  existingTopics: ExistingTopic[];
  candidateTopics: CandidateTopic[];
  onAdvance: () => void;
}

type FocusPos = {
  column: 'existing' | 'candidate';
  topicIndex: number;
  taskIndex: number;
};

type ContextMenuState = {
  x: number;
  y: number;
  taskId: string;
  side: 'existing' | 'candidate';
};

// ── Component ─────────────────────────────────────────────────────────────────

export function TaskMatchingStage({ callId, existingTopics, candidateTopics, onAdvance }: Props) {
  const [groups, setGroups] = useState<TaskMatchGroup[]>([]);
  const [selectedExisting, setSelectedExisting] = useState<Set<string>>(new Set()); // task_id set
  const [selectedCandidates, setSelectedCandidates] = useState<Set<string>>(new Set()); // task_id set
  const [saving, setSaving] = useState(false);
  const [showCrossTopicModal, setShowCrossTopicModal] = useState<{
    candidate: string;
    existing: string;
  } | null>(null);
  const [pendingRefs, setPendingRefs] = useState<{ candidateRefs: TaskRef[]; existingRefs: TaskRef[] } | null>(null);
  const [focusPos, setFocusPos] = useState<FocusPos>({
    column: 'candidate',
    topicIndex: 0,
    taskIndex: 0,
  });
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);

  // ── Match hints ──────────────────────────────────────────────────────────────

  const matchHints = useMemo(() => {
    const existingTexts = new Map<string, string>();
    for (const t of existingTopics) {
      for (const task of t.tasks) {
        existingTexts.set(task.task.trim().toLowerCase(), task.task_id);
      }
    }
    const hints = new Map<string, 'exact' | 'partial'>();
    for (const t of candidateTopics) {
      for (const task of t.tasks) {
        if (existingTexts.has(task.task.trim().toLowerCase())) {
          hints.set(task.task_id, 'exact');
        }
      }
    }
    return hints;
  }, [existingTopics, candidateTopics]);

  // ── Group membership helpers ─────────────────────────────────────────────────

  function isInAnyGroup(taskId: string): boolean {
    return groups.some(g =>
      g.call_task_refs.some(r => r.task_id === taskId) ||
      g.project_task_refs.some(r => r.task_id === taskId)
    );
  }

  function getGroupIndexForTask(taskId: string): number | null {
    // Only count 'binding' kind groups (topic_merge doesn't carry task colors)
    const bindingGroups = groups.filter(g => g.kind === 'binding');
    for (let i = 0; i < bindingGroups.length; i++) {
      const g = bindingGroups[i];
      if (
        g.call_task_refs.some(r => r.task_id === taskId) ||
        g.project_task_refs.some(r => r.task_id === taskId)
      ) {
        return i;
      }
    }
    return null;
  }

  // ── Toggle handlers ──────────────────────────────────────────────────────────

  function toggleExisting(taskId: string) {
    if (isInAnyGroup(taskId)) return;
    setSelectedExisting(prev => {
      const next = new Set(prev);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  }

  function toggleCandidate(taskId: string) {
    if (isInAnyGroup(taskId)) return;
    setSelectedCandidates(prev => {
      const next = new Set(prev);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  }

  // ── Ref lookup helpers ───────────────────────────────────────────────────────

  function findCandidateRef(taskId: string): TaskRef | null {
    for (const ct of candidateTopics) {
      for (const task of ct.tasks) {
        if (task.task_id === taskId) {
          return { call_topic_name: ct.name, task_id: taskId };
        }
      }
    }
    return null;
  }

  function findExistingRef(taskId: string): TaskRef | null {
    for (const et of existingTopics) {
      for (const task of et.tasks) {
        if (task.task_id === taskId) {
          return { project_topic_id: et.topic_id, task_id: taskId };
        }
      }
    }
    return null;
  }

  // ── Commit group ─────────────────────────────────────────────────────────────

  function commitGroup() {
    const candidateRefs = Array.from(selectedCandidates)
      .map(findCandidateRef)
      .filter((r): r is TaskRef => r !== null);
    const existingRefs = Array.from(selectedExisting)
      .map(findExistingRef)
      .filter((r): r is TaskRef => r !== null);
    if (candidateRefs.length === 0 && existingRefs.length === 0) return;

    // Cross-topic check: if BOTH sides have selections AND topics differ → modal
    if (candidateRefs.length > 0 && existingRefs.length > 0) {
      const candidateTopicSet = new Set(
        candidateRefs.map(r => (r.call_topic_name || '').toLowerCase())
      );
      const existingTopicSet = new Set(
        existingRefs.map(r => r.project_topic_id || '')
      );
      const candidateTopicNames = Array.from(candidateTopicSet).join(', ');
      const existingTopicNames = Array.from(existingTopicSet)
        .map(pid => {
          const topic = existingTopics.find(t => t.topic_id === pid);
          return topic?.name || pid;
        })
        .join(', ');

      const isCrossTopic =
        candidateTopicSet.size > 1 ||
        existingTopicSet.size > 1 ||
        Array.from(candidateTopicSet)[0] !==
          existingTopics.find(t => t.topic_id === Array.from(existingTopicSet)[0])?.name.toLowerCase();

      if (isCrossTopic) {
        setShowCrossTopicModal({
          candidate: candidateTopicNames,
          existing: existingTopicNames,
        });
        setPendingRefs({ candidateRefs, existingRefs });
        return;
      }
    }
    doCommitGroup(candidateRefs, existingRefs);
  }

  function doCommitGroup(
    candidateRefs: TaskRef[],
    existingRefs: TaskRef[],
    topicMergeDecision?: 'keep_existing' | 'keep_candidate' | 'merge'
  ) {
    const newGroups: TaskMatchGroup[] = [
      ...groups,
      {
        kind: 'binding' as const,
        call_task_refs: candidateRefs,
        project_task_refs: existingRefs,
      },
    ];
    if (topicMergeDecision === 'merge' && candidateRefs.length > 0 && existingRefs.length > 0) {
      const uniqueCallTopics = Array.from(
        new Set(candidateRefs.map(r => r.call_topic_name || ''))
      ).filter(Boolean);
      const uniqueProjectTopics = Array.from(
        new Set(existingRefs.map(r => r.project_topic_id || ''))
      ).filter(Boolean);
      newGroups.push({
        kind: 'topic_merge',
        call_task_refs: uniqueCallTopics.map(name => ({ call_topic_name: name, task_id: '' })),
        project_task_refs: uniqueProjectTopics.map(pid => ({ project_topic_id: pid, task_id: '' })),
      });
    }
    setGroups(newGroups);
    setSelectedCandidates(new Set());
    setSelectedExisting(new Set());
    setShowCrossTopicModal(null);
    setPendingRefs(null);
  }

  function clearSelection() {
    setSelectedCandidates(new Set());
    setSelectedExisting(new Set());
  }

  // ── Context menu ─────────────────────────────────────────────────────────────

  function handleContextMenu(e: React.MouseEvent, taskId: string, side: 'existing' | 'candidate') {
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, taskId, side });
  }

  function addTaskToGroup(taskId: string, side: 'existing' | 'candidate', targetBindingGroupIdx: number) {
    // Remove the task from any group it is already in
    const newGroups = groups.map(g => {
      if (g.kind !== 'binding') return g;
      return {
        ...g,
        call_task_refs: g.call_task_refs.filter(r => r.task_id !== taskId),
        project_task_refs: g.project_task_refs.filter(r => r.task_id !== taskId),
      };
    });
    // Find the target binding group by binding-only index
    let bindingCounter = -1;
    const targetGlobalIdx = newGroups.findIndex(g => {
      if (g.kind !== 'binding') return false;
      bindingCounter++;
      return bindingCounter === targetBindingGroupIdx;
    });
    if (targetGlobalIdx === -1) return;
    const ref = side === 'existing' ? findExistingRef(taskId) : findCandidateRef(taskId);
    if (!ref) return;
    const target = { ...newGroups[targetGlobalIdx] };
    if (side === 'existing') {
      target.project_task_refs = [...target.project_task_refs, ref];
    } else {
      target.call_task_refs = [...target.call_task_refs, ref];
    }
    newGroups[targetGlobalIdx] = target;
    // Drop any binding groups that became empty after removal
    const cleaned = newGroups.filter(g =>
      g.kind !== 'binding' ||
      g.call_task_refs.length > 0 ||
      g.project_task_refs.length > 0
    );
    setGroups(cleaned);
    setContextMenu(null);
  }

  function removeTaskFromCurrentGroup(taskId: string) {
    const newGroups = groups.map(g => {
      if (g.kind !== 'binding') return g;
      return {
        ...g,
        call_task_refs: g.call_task_refs.filter(r => r.task_id !== taskId),
        project_task_refs: g.project_task_refs.filter(r => r.task_id !== taskId),
      };
    });
    // Drop emptied binding groups
    const cleaned = newGroups.filter(g =>
      g.kind !== 'binding' ||
      g.call_task_refs.length > 0 ||
      g.project_task_refs.length > 0
    );
    setGroups(cleaned);
    setContextMenu(null);
  }

  // ── Focus navigation helpers ─────────────────────────────────────────────────

  function getColumnTopics(
    column: 'existing' | 'candidate'
  ): Array<{ name: string; tasks: Array<{ task_id: string }> }> {
    return column === 'existing'
      ? existingTopics.map(t => ({ name: t.name, tasks: t.tasks }))
      : candidateTopics;
  }

  function moveFocus(pos: FocusPos, delta: 1 | -1): FocusPos {
    const topics = getColumnTopics(pos.column);
    if (!topics.length) return pos;
    let { topicIndex, taskIndex } = pos;
    taskIndex += delta;
    while (taskIndex < 0) {
      topicIndex -= 1;
      if (topicIndex < 0) topicIndex = topics.length - 1;
      taskIndex = topics[topicIndex].tasks.length - 1;
    }
    while (topicIndex < topics.length && taskIndex >= topics[topicIndex].tasks.length) {
      topicIndex += 1;
      if (topicIndex >= topics.length) topicIndex = 0;
      taskIndex = 0;
    }
    return { column: pos.column, topicIndex, taskIndex };
  }

  function getFocusedTaskRef(pos: FocusPos): { ref: TaskRef; id: string } | null {
    if (pos.column === 'existing') {
      const topic = existingTopics[pos.topicIndex];
      if (!topic) return null;
      const task = topic.tasks[pos.taskIndex];
      if (!task) return null;
      return {
        ref: { project_topic_id: topic.topic_id, task_id: task.task_id },
        id: task.task_id,
      };
    } else {
      const topic = candidateTopics[pos.topicIndex];
      if (!topic) return null;
      const task = topic.tasks[pos.taskIndex];
      if (!task) return null;
      return {
        ref: { call_topic_name: topic.name, task_id: task.task_id },
        id: task.task_id,
      };
    }
  }

  // ── Keyboard: j/k/h/l/Enter/space/n/esc ─────────────────────────────────────

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (showCrossTopicModal) {
        if (e.key === 'Escape') {
          e.preventDefault();
          setShowCrossTopicModal(null);
          setPendingRefs(null);
        }
        return;
      }
      if (e.key === 'j') {
        e.preventDefault();
        setFocusPos(f => moveFocus(f, 1));
      } else if (e.key === 'k') {
        e.preventDefault();
        setFocusPos(f => moveFocus(f, -1));
      } else if (e.key === 'h') {
        e.preventDefault();
        setFocusPos(f => ({ ...f, column: 'existing', topicIndex: 0, taskIndex: 0 }));
      } else if (e.key === 'l') {
        e.preventDefault();
        setFocusPos(f => ({ ...f, column: 'candidate', topicIndex: 0, taskIndex: 0 }));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const focused = getFocusedTaskRef(focusPos);
        if (focused) {
          if (focusPos.column === 'existing') toggleExisting(focused.id);
          else toggleCandidate(focused.id);
        }
      } else if (e.key === ' ' && (selectedCandidates.size > 0 || selectedExisting.size > 0)) {
        e.preventDefault();
        commitGroup();
      } else if (e.key === 'n' && selectedCandidates.size > 0) {
        e.preventDefault();
        const candidateRefs = Array.from(selectedCandidates)
          .map(findCandidateRef)
          .filter((r): r is TaskRef => r !== null);
        doCommitGroup(candidateRefs, []);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        clearSelection();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCandidates, selectedExisting, focusPos, showCrossTopicModal, existingTopics, candidateTopics, groups]);

  // ── Context menu close on click-outside / Escape ─────────────────────────────

  useEffect(() => {
    if (!contextMenu) return;
    const handleClick = () => setContextMenu(null);
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setContextMenu(null);
    };
    // Slight delay so the menu's own click doesn't immediately close it
    const t = setTimeout(() => {
      window.addEventListener('click', handleClick);
      window.addEventListener('keydown', handleEsc);
    }, 50);
    return () => {
      clearTimeout(t);
      window.removeEventListener('click', handleClick);
      window.removeEventListener('keydown', handleEsc);
    };
  }, [contextMenu]);

  // ── Save ─────────────────────────────────────────────────────────────────────

  async function save() {
    setSaving(true);
    try {
      await topicsAPI.saveTaskMatches(callId, groups);
      onAdvance();
    } catch (e) {
      console.error('Failed to save matches:', e);
      alert(`Failed to save matches: ${e instanceof Error ? e.message : 'Unknown error'}`);
    } finally {
      setSaving(false);
    }
  }

  // ── Derived helpers ──────────────────────────────────────────────────────────

  const isFocused = (column: 'existing' | 'candidate', topicIdx: number, taskIdx: number) =>
    focusPos.column === column &&
    focusPos.topicIndex === topicIdx &&
    focusPos.taskIndex === taskIdx;

  const exactMatchCount = Array.from(matchHints.values()).filter(h => h === 'exact').length;
  const bindingGroupCount = groups.filter(g => g.kind === 'binding').length;

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="flex gap-4 p-4">
      {contextMenu && (() => {
        const bindingGroups = groups.filter(g => g.kind === 'binding');
        const currentIdx = getGroupIndexForTask(contextMenu.taskId);
        return (
          <div
            style={{
              position: 'fixed',
              top: contextMenu.y,
              left: contextMenu.x,
              background: 'white',
              border: '1px solid #d1d5db',
              borderRadius: 6,
              boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
              zIndex: 100,
              minWidth: 200,
              padding: 4,
              fontSize: 12,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {currentIdx !== null && (
              <div style={{
                fontSize: 10, color: '#6b7280', padding: '6px 8px',
                textTransform: 'uppercase', letterSpacing: '0.05em',
                borderBottom: '1px solid #e5e7eb',
              }}>
                Currently in Group {currentIdx + 1}
              </div>
            )}
            {bindingGroups.length === 0 ? (
              <div style={{ padding: '8px 8px', color: '#9ca3af' }}>
                No groups yet — link some tasks first
              </div>
            ) : (
              bindingGroups.map((g, idx) => {
                if (idx === currentIdx) return null;
                const col = groupColor(idx);
                return (
                  <button
                    key={idx}
                    onClick={() => addTaskToGroup(contextMenu.taskId, contextMenu.side, idx)}
                    style={{
                      display: 'block',
                      width: '100%',
                      textAlign: 'left',
                      padding: '6px 8px',
                      border: 'none',
                      background: 'transparent',
                      cursor: 'pointer',
                      borderRadius: 4,
                      color: col.text,
                      fontSize: 12,
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = col.bg)}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                  >
                    {currentIdx !== null ? 'Move to' : 'Add to'} Group {idx + 1}
                    <span style={{ fontSize: 10, color: '#9ca3af', marginLeft: 8 }}>
                      ({g.call_task_refs.length} ↔ {g.project_task_refs.length})
                    </span>
                  </button>
                );
              })
            )}
            {currentIdx !== null && (
              <button
                onClick={() => removeTaskFromCurrentGroup(contextMenu.taskId)}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '6px 8px',
                  border: 'none',
                  background: 'transparent',
                  cursor: 'pointer',
                  borderRadius: 4,
                  color: '#ae2a19',
                  fontSize: 12,
                  borderTop: '1px solid #e5e7eb',
                  marginTop: 4,
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = '#fee2e2')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
              >
                Remove from current group
              </button>
            )}
          </div>
        );
      })()}

      {showCrossTopicModal && pendingRefs && (
        <CrossTopicBindingModal
          candidateTopicName={showCrossTopicModal.candidate}
          existingTopicName={showCrossTopicModal.existing}
          onChoose={(decision) => {
            if (decision === 'cancel') {
              setShowCrossTopicModal(null);
              setPendingRefs(null);
              return;
            }
            doCommitGroup(
              pendingRefs.candidateRefs,
              pendingRefs.existingRefs,
              decision === 'keep_existing_topic'
                ? 'keep_existing'
                : decision === 'keep_candidate_topic'
                ? 'keep_candidate'
                : 'merge',
            );
          }}
        />
      )}

      {/* Existing tasks column */}
      <div className="flex-1 overflow-auto max-h-[80vh]">
        <h3 className="font-semibold mb-2 sticky top-0 bg-white">Existing project tasks</h3>
        {existingTopics.map((t, tIdx) => (
          <div key={t.topic_id} className="mb-3">
            <div className="text-sm text-gray-600 mb-1 font-semibold">{t.name}</div>
            {t.tasks.map((task, taskIdx) => {
              const groupIdx = getGroupIndexForTask(task.task_id);
              return (
                <TaskCard
                  key={task.task_id}
                  taskId={task.task_id}
                  topicName={t.name}
                  taskText={task.task}
                  nextStep={task.next_step}
                  owner={task.owner}
                  keyTerms={task.key_terms}
                  isFocused={isFocused('existing', tIdx, taskIdx)}
                  isSelected={selectedExisting.has(task.task_id)}
                  groupColor={groupIdx !== null ? groupColor(groupIdx) : null}
                  onClick={() => toggleExisting(task.task_id)}
                  onContextMenu={(e) => handleContextMenu(e, task.task_id, 'existing')}
                />
              );
            })}
          </div>
        ))}
      </div>

      {/* Candidate tasks column */}
      <div className="flex-1 overflow-auto max-h-[80vh]">
        <h3 className="font-semibold mb-2 sticky top-0 bg-white">This call&apos;s candidate tasks</h3>
        {candidateTopics.map((t, tIdx) => (
          <div key={t.name} className="mb-3">
            <div className="text-sm text-gray-600 mb-1 font-semibold">{t.name}</div>
            {t.tasks.map((task, taskIdx) => {
              const groupIdx = getGroupIndexForTask(task.task_id);
              return (
                <TaskCard
                  key={task.task_id}
                  taskId={task.task_id}
                  topicName={t.name}
                  taskText={task.task}
                  nextStep={task.next_step}
                  owner={task.owner}
                  keyTerms={task.key_terms}
                  isFocused={isFocused('candidate', tIdx, taskIdx)}
                  isSelected={selectedCandidates.has(task.task_id)}
                  groupColor={groupIdx !== null ? groupColor(groupIdx) : null}
                  matchHint={matchHints.get(task.task_id)}
                  onClick={() => toggleCandidate(task.task_id)}
                  onContextMenu={(e) => handleContextMenu(e, task.task_id, 'candidate')}
                />
              );
            })}
          </div>
        ))}
      </div>

      {/* Action panel */}
      <div className="w-56 sticky top-4 self-start">
        <h3 className="font-semibold mb-2">Actions</h3>

        <button
          disabled={selectedCandidates.size === 0 && selectedExisting.size === 0}
          onClick={commitGroup}
          className="w-full p-2 bg-blue-500 text-white rounded disabled:bg-gray-300 mb-2 text-sm"
        >
          Link ({selectedCandidates.size} ↔ {selectedExisting.size})
        </button>

        <button
          disabled={selectedCandidates.size === 0}
          onClick={() => {
            const candidateRefs = Array.from(selectedCandidates)
              .map(findCandidateRef)
              .filter((r): r is TaskRef => r !== null);
            doCommitGroup(candidateRefs, []);
          }}
          className="w-full p-2 bg-green-500 text-white rounded disabled:bg-gray-300 mb-2 text-sm"
        >
          Mark {selectedCandidates.size} candidate{selectedCandidates.size === 1 ? '' : 's'} NEW
        </button>

        <button
          onClick={clearSelection}
          className="w-full p-2 bg-gray-200 rounded mb-4 text-sm"
        >
          Clear selection
        </button>

        {exactMatchCount > 0 && (
          <button
            onClick={() => {
              const autoGroups: TaskMatchGroup[] = [];
              for (const ct of candidateTopics) {
                for (const task of ct.tasks) {
                  if (matchHints.get(task.task_id) !== 'exact') continue;
                  if (isInAnyGroup(task.task_id)) continue;
                  const candidateText = task.task.trim().toLowerCase();
                  outer: for (const et of existingTopics) {
                    for (const etask of et.tasks) {
                      if (etask.task.trim().toLowerCase() === candidateText && !isInAnyGroup(etask.task_id)) {
                        autoGroups.push({
                          kind: 'binding',
                          call_task_refs: [{ call_topic_name: ct.name, task_id: task.task_id }],
                          project_task_refs: [{ project_topic_id: et.topic_id, task_id: etask.task_id }],
                        });
                        break outer;
                      }
                    }
                  }
                }
              }
              setGroups(g => [...g, ...autoGroups]);
            }}
            className="w-full p-2 bg-yellow-500 text-white rounded text-sm mb-2"
          >
            Auto-bind {exactMatchCount} exact matches
          </button>
        )}

        <hr className="my-2" />
        <div className="text-xs text-gray-600 mb-2">
          Groups: {bindingGroupCount}
        </div>

        {groups.flatMap((g, fullIdx) => {
          if (g.kind !== 'binding') return [];
          // idx among binding-only groups (for color cycling)
          const bindingIdx = groups.slice(0, fullIdx).filter(x => x.kind === 'binding').length;
          const col = groupColor(bindingIdx);
          return [(
            <div
              key={fullIdx}
              style={{
                border: `1.5px solid ${col.border}`,
                background: col.bg,
                color: col.text,
                borderRadius: 4,
                padding: 4,
                marginBottom: 2,
                fontSize: 11,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span>
                Group {bindingIdx + 1}: {g.call_task_refs.length} ↔ {g.project_task_refs.length}
              </span>
              <button
                onClick={() => setGroups(prev => prev.filter((_, i) => i !== fullIdx))}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'inherit' }}
              >
                ×
              </button>
            </div>
          )];
        })}

        <hr className="my-2" />
        <button
          onClick={save}
          disabled={saving}
          className="w-full p-2 bg-purple-600 text-white rounded text-sm disabled:bg-gray-400"
        >
          {saving ? 'Saving…' : 'Save matches → Project updates'}
        </button>
        <div className="text-xs text-gray-500 mt-2">
          Keyboard: j/k = up/down, h/l = column, Enter = toggle, space = link, n = mark new, esc = clear<br/>
          Right-click any task to add/move/remove to an existing group
        </div>
      </div>
    </div>
  );
}
