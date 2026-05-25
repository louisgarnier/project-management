"use client";

import React, { useState, useEffect, useMemo } from 'react';
import { TaskCard } from './TaskCard';
import { CrossTopicBindingModal } from './CrossTopicBindingModal';
import type { TaskMatchGroup, TaskRef } from '@/types';
import { topicsAPI } from '@/api/client';

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

export function TaskMatchingStage({ callId, existingTopics, candidateTopics, onAdvance }: Props) {
  const [groups, setGroups] = useState<TaskMatchGroup[]>([]);
  const [stagedCandidate, setStagedCandidate] = useState<TaskRef | null>(null);
  const [stagedExisting, setStagedExisting] = useState<TaskRef | null>(null);
  const [saving, setSaving] = useState(false);
  const [showCrossTopicModal, setShowCrossTopicModal] = useState<{
    candidate: string;
    existing: string;
  } | null>(null);
  const [focusPos, setFocusPos] = useState<FocusPos>({
    column: 'candidate',
    topicIndex: 0,
    taskIndex: 0,
  });

  // Exact-text match hints (mechanical, no LLM)
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

  function stageCandidate(ref: TaskRef) { setStagedCandidate(ref); }
  function stageExisting(ref: TaskRef) { setStagedExisting(ref); }

  function commitBinding() {
    if (!stagedCandidate || !stagedExisting) return;
    // Cross-topic check
    const candidateTopic = stagedCandidate.call_topic_name?.toLowerCase();
    const existingTopic = existingTopics.find(t => t.topic_id === stagedExisting.project_topic_id);
    const existingTopicNameLc = existingTopic?.name.toLowerCase();
    if (candidateTopic && existingTopicNameLc && candidateTopic !== existingTopicNameLc) {
      setShowCrossTopicModal({
        candidate: stagedCandidate.call_topic_name || '',
        existing: existingTopic?.name || '',
      });
      return;
    }
    doCommitBinding();
  }

  function doCommitBinding(topicMergeDecision?: 'keep_existing' | 'keep_candidate' | 'merge') {
    if (!stagedCandidate || !stagedExisting) return;
    const newGroups: TaskMatchGroup[] = [
      ...groups,
      {
        kind: 'binding' as const,
        call_task_refs: [stagedCandidate],
        project_task_refs: [stagedExisting],
      },
    ];
    if (topicMergeDecision === 'merge') {
      // Emit an additional topic_merge group capturing the decision
      newGroups.push({
        kind: 'topic_merge',
        call_task_refs: [{ call_topic_name: stagedCandidate.call_topic_name || '', task_id: '' }],
        project_task_refs: [{ project_topic_id: stagedExisting.project_topic_id || '', task_id: '' }],
      });
    }
    // 'keep_existing' and 'keep_candidate' don't emit additional groups —
    // the binding alone implies the task lives under the chosen topic.
    // Per-binding topic ownership is derived later from the binding direction.
    setGroups(newGroups);
    setStagedCandidate(null);
    setStagedExisting(null);
    setShowCrossTopicModal(null);
  }

  function clearStaging() { setStagedCandidate(null); setStagedExisting(null); }

  function markCandidateNew(ref: TaskRef) {
    setGroups(g => [...g, { kind: 'binding' as const, call_task_refs: [ref], project_task_refs: [] }]);
  }

  // ── Focus navigation helpers ──────────────────────────────────────────────

  function getColumnTopics(column: 'existing' | 'candidate'): Array<{ name: string; tasks: Array<{ task_id: string }> }> {
    return column === 'existing'
      ? existingTopics.map(t => ({ name: t.name, tasks: t.tasks }))
      : candidateTopics;
  }

  function moveFocus(pos: FocusPos, delta: 1 | -1): FocusPos {
    const topics = getColumnTopics(pos.column);
    if (!topics.length) return pos;
    let { topicIndex, taskIndex } = pos;
    taskIndex += delta;
    // Wrap within topic; if past beginning, move to previous topic
    while (taskIndex < 0) {
      topicIndex -= 1;
      if (topicIndex < 0) {
        topicIndex = topics.length - 1;
      }
      taskIndex = topics[topicIndex].tasks.length - 1;
    }
    // If past end, advance to next topic
    while (topicIndex < topics.length && taskIndex >= topics[topicIndex].tasks.length) {
      topicIndex += 1;
      if (topicIndex >= topics.length) topicIndex = 0;
      taskIndex = 0;
    }
    return { column: pos.column, topicIndex, taskIndex };
  }

  function getFocusedTaskRef(pos: FocusPos): TaskRef | null {
    if (pos.column === 'existing') {
      const topic = existingTopics[pos.topicIndex];
      if (!topic) return null;
      const task = topic.tasks[pos.taskIndex];
      if (!task) return null;
      return { project_topic_id: topic.topic_id, task_id: task.task_id };
    } else {
      const topic = candidateTopics[pos.topicIndex];
      if (!topic) return null;
      const task = topic.tasks[pos.taskIndex];
      if (!task) return null;
      return { call_topic_name: topic.name, task_id: task.task_id };
    }
  }

  function stageFocused(pos: FocusPos) {
    const ref = getFocusedTaskRef(pos);
    if (!ref) return;
    if (pos.column === 'existing') {
      setStagedExisting(ref);
    } else {
      setStagedCandidate(ref);
    }
  }

  // ── Keyboard: j/k/h/l/Enter/space/n/esc ─────────────────────────────────

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      // Modal open: only allow esc to close it; skip all nav keys
      if (showCrossTopicModal) {
        if (e.key === 'Escape') {
          e.preventDefault();
          setShowCrossTopicModal(null);
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
        stageFocused(focusPos);
      } else if (e.key === ' ' && stagedCandidate && stagedExisting) {
        e.preventDefault();
        commitBinding();
      } else if (e.key === 'n' && stagedCandidate) {
        e.preventDefault();
        markCandidateNew(stagedCandidate);
        setStagedCandidate(null);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        clearStaging();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stagedCandidate, stagedExisting, focusPos, showCrossTopicModal, existingTopics, candidateTopics]);

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

  const isBound = (taskId: string) =>
    groups.some(g =>
      g.call_task_refs.some(r => r.task_id === taskId) ||
      g.project_task_refs.some(r => r.task_id === taskId)
    );

  const isFocused = (column: 'existing' | 'candidate', topicIdx: number, taskIdx: number) =>
    focusPos.column === column &&
    focusPos.topicIndex === topicIdx &&
    focusPos.taskIndex === taskIdx;

  const exactMatchCount = Array.from(matchHints.values()).filter(h => h === 'exact').length;

  return (
    <div className="flex gap-4 p-4">
      {showCrossTopicModal && (
        <CrossTopicBindingModal
          candidateTopicName={showCrossTopicModal.candidate}
          existingTopicName={showCrossTopicModal.existing}
          onChoose={(decision) => {
            if (decision === 'cancel') {
              setShowCrossTopicModal(null);
              return;
            }
            doCommitBinding(
              decision === 'keep_existing_topic'
                ? 'keep_existing'
                : decision === 'keep_candidate_topic'
                ? 'keep_candidate'
                : 'merge',
            );
          }}
        />
      )}
      <div className="flex-1 overflow-auto max-h-[80vh]">
        <h3 className="font-semibold mb-2 sticky top-0 bg-white">Existing project tasks</h3>
        {existingTopics.map((t, tIdx) => (
          <div key={t.topic_id} className="mb-3">
            <div className="text-sm text-gray-600 mb-1 font-semibold">{t.name}</div>
            {t.tasks.map((task, taskIdx) => (
              <TaskCard
                key={task.task_id}
                taskId={task.task_id}
                topicName={t.name}
                taskText={task.task}
                nextStep={task.next_step}
                owner={task.owner}
                keyTerms={task.key_terms}
                isSelected={stagedExisting?.task_id === task.task_id}
                isBound={isBound(task.task_id)}
                isFocused={isFocused('existing', tIdx, taskIdx)}
                onClick={() => stageExisting({ project_topic_id: t.topic_id, task_id: task.task_id })}
              />
            ))}
          </div>
        ))}
      </div>
      <div className="flex-1 overflow-auto max-h-[80vh]">
        <h3 className="font-semibold mb-2 sticky top-0 bg-white">This call&apos;s candidate tasks</h3>
        {candidateTopics.map((t, tIdx) => (
          <div key={t.name} className="mb-3">
            <div className="text-sm text-gray-600 mb-1 font-semibold">{t.name}</div>
            {t.tasks.map((task, taskIdx) => (
              <TaskCard
                key={task.task_id}
                taskId={task.task_id}
                topicName={t.name}
                taskText={task.task}
                nextStep={task.next_step}
                owner={task.owner}
                keyTerms={task.key_terms}
                matchHint={matchHints.get(task.task_id)}
                isSelected={stagedCandidate?.task_id === task.task_id}
                isBound={isBound(task.task_id)}
                isFocused={isFocused('candidate', tIdx, taskIdx)}
                onClick={() => stageCandidate({ call_topic_name: t.name, task_id: task.task_id })}
              />
            ))}
          </div>
        ))}
      </div>
      <div className="w-56 sticky top-4 self-start">
        <h3 className="font-semibold mb-2">Actions</h3>
        <button
          disabled={!stagedCandidate || !stagedExisting}
          onClick={commitBinding}
          className="w-full p-2 bg-blue-500 text-white rounded disabled:bg-gray-300 mb-2 text-sm"
        >
          Bind ({stagedCandidate ? '1' : '0'} ↔ {stagedExisting ? '1' : '0'})
        </button>
        <button
          disabled={!stagedCandidate}
          onClick={() => {
            if (stagedCandidate) {
              markCandidateNew(stagedCandidate);
              setStagedCandidate(null);
            }
          }}
          className="w-full p-2 bg-green-500 text-white rounded disabled:bg-gray-300 mb-2 text-sm"
        >
          Mark candidate NEW
        </button>
        <button onClick={clearStaging} className="w-full p-2 bg-gray-200 rounded mb-2 text-sm">
          Clear staging
        </button>
        {exactMatchCount > 0 && (
          <button
            onClick={() => {
              const autoGroups: TaskMatchGroup[] = [];
              for (const ct of candidateTopics) {
                for (const task of ct.tasks) {
                  if (matchHints.get(task.task_id) !== 'exact') continue;
                  const candidateText = task.task.trim().toLowerCase();
                  outer: for (const et of existingTopics) {
                    for (const etask of et.tasks) {
                      if (etask.task.trim().toLowerCase() === candidateText) {
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
        <div className="text-xs text-gray-600 mb-2">Groups: {groups.length}</div>
        <button
          onClick={save}
          disabled={saving}
          className="w-full p-2 bg-purple-600 text-white rounded text-sm disabled:bg-gray-400"
        >
          {saving ? 'Saving…' : 'Save matches → Project updates'}
        </button>
        <div className="text-xs text-gray-500 mt-2">
          Keyboard: j/k = up/down, h/l = left/right column, Enter = stage, space = bind, n = mark new, esc = clear
        </div>
      </div>
    </div>
  );
}
