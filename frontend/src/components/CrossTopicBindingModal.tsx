"use client";

import React, { useState } from 'react';

interface Props {
  candidateTopicName: string;
  existingTopicName: string;
  onChoose: (
    decision:
      | 'keep_existing_topic'
      | 'keep_candidate_topic'
      | 'merge_topics'
      | 'create_new'
      | 'cancel',
    newTopicName?: string,
  ) => void;
}

export function CrossTopicBindingModal({ candidateTopicName, existingTopicName, onChoose }: Props) {
  const [newTopicName, setNewTopicName] = useState('');

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
          <div style={{ borderTop: '1px solid #e5e7eb', marginTop: 8, paddingTop: 8 }}>
            <input
              type="text"
              placeholder="…or type a new topic name"
              value={newTopicName}
              onChange={(e) => setNewTopicName(e.target.value)}
              className="w-full p-2 border border-gray-300 rounded text-sm mb-2"
              style={{ width: '100%' }}
            />
            <button
              disabled={!newTopicName.trim()}
              onClick={() => onChoose('create_new', newTopicName.trim())}
              className="p-2 bg-orange-500 text-white rounded text-sm disabled:bg-gray-300"
              style={{ width: '100%' }}
            >
              Create new topic &quot;{newTopicName.trim() || '...'}&quot;
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
