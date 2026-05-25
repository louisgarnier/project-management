"use client";

import React from 'react';

interface Props {
  candidateTopicName: string;
  existingTopicName: string;
  onChoose: (decision: 'keep_existing_topic' | 'keep_candidate_topic' | 'merge_topics' | 'cancel') => void;
}

export function CrossTopicBindingModal({ candidateTopicName, existingTopicName, onChoose }: Props) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white p-4 rounded shadow-lg max-w-md">
        <h3 className="font-semibold mb-2">Cross-topic binding</h3>
        <p className="text-sm mb-4">
          You&apos;re binding a task from <strong>{candidateTopicName}</strong> to a task under{' '}
          <strong>{existingTopicName}</strong>. Which topic should the merged task live under?
        </p>
        <div className="flex flex-col gap-2">
          <button
            onClick={() => onChoose('keep_existing_topic')}
            className="p-2 bg-blue-500 text-white rounded text-sm"
          >
            Keep under &quot;{existingTopicName}&quot; (existing wins)
          </button>
          <button
            onClick={() => onChoose('keep_candidate_topic')}
            className="p-2 bg-blue-400 text-white rounded text-sm"
          >
            Move into &quot;{candidateTopicName}&quot; (candidate wins)
          </button>
          <button
            onClick={() => onChoose('merge_topics')}
            className="p-2 bg-purple-500 text-white rounded text-sm"
          >
            These two topics are the same — merge them
          </button>
          <button onClick={() => onChoose('cancel')} className="p-2 bg-gray-200 rounded text-sm">
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
