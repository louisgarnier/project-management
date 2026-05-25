"use client";

import React, { useState, useEffect, useMemo } from 'react';
import { TaskCard } from './TaskCard';
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

export function TaskMatchingStage({ callId, existingTopics, candidateTopics, onAdvance }: Props) {
  const [groups, setGroups] = useState<TaskMatchGroup[]>([]);
  const [stagedCandidate, setStagedCandidate] = useState<TaskRef | null>(null);
  const [stagedExisting, setStagedExisting] = useState<TaskRef | null>(null);
  const [saving, setSaving] = useState(false);

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
    setGroups(g => [...g, {
      kind: 'binding' as const,
      call_task_refs: [stagedCandidate],
      project_task_refs: [stagedExisting],
    }]);
    setStagedCandidate(null);
    setStagedExisting(null);
  }

  function clearStaging() { setStagedCandidate(null); setStagedExisting(null); }

  function markCandidateNew(ref: TaskRef) {
    setGroups(g => [...g, { kind: 'binding' as const, call_task_refs: [ref], project_task_refs: [] }]);
  }

  // Keyboard: space = bind (when both staged), esc = clear
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === ' ' && stagedCandidate && stagedExisting) {
        e.preventDefault();
        commitBinding();
      }
      if (e.key === 'Escape') clearStaging();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stagedCandidate, stagedExisting]);

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

  return (
    <div className="flex gap-4 p-4">
      <div className="flex-1 overflow-auto max-h-[80vh]">
        <h3 className="font-semibold mb-2 sticky top-0 bg-white">Existing project tasks</h3>
        {existingTopics.map(t => (
          <div key={t.topic_id} className="mb-3">
            <div className="text-sm text-gray-600 mb-1 font-semibold">{t.name}</div>
            {t.tasks.map(task => (
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
                onClick={() => stageExisting({ project_topic_id: t.topic_id, task_id: task.task_id })}
              />
            ))}
          </div>
        ))}
      </div>
      <div className="flex-1 overflow-auto max-h-[80vh]">
        <h3 className="font-semibold mb-2 sticky top-0 bg-white">This call&apos;s candidate tasks</h3>
        {candidateTopics.map(t => (
          <div key={t.name} className="mb-3">
            <div className="text-sm text-gray-600 mb-1 font-semibold">{t.name}</div>
            {t.tasks.map(task => (
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
        <button onClick={clearStaging} className="w-full p-2 bg-gray-200 rounded mb-4 text-sm">
          Clear staging
        </button>
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
          Shortcuts: space = bind, esc = clear
        </div>
      </div>
    </div>
  );
}
