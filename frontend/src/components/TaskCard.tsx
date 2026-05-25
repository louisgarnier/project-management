"use client";

import React from 'react';

interface TaskCardProps {
  taskId: string;
  topicName: string;
  taskText: string;
  nextStep?: string;
  owner?: string;
  status?: string;
  keyTerms?: string[];
  isSelected?: boolean;
  isBound?: boolean;
  isFocused?: boolean;
  matchHint?: 'exact' | 'partial' | null;
  onClick?: () => void;
}

export function TaskCard({
  taskId, topicName, taskText, nextStep, owner, status, keyTerms,
  isSelected, isBound, isFocused, matchHint, onClick,
}: TaskCardProps) {
  const border = isFocused
    ? 'border-purple-500 ring-2 ring-purple-300'
    : isSelected ? 'border-blue-500'
    : isBound ? 'border-green-500'
    : 'border-gray-200';
  const bg = matchHint === 'exact' ? 'bg-yellow-50' : matchHint === 'partial' ? 'bg-orange-50' : 'bg-white';
  return (
    <div
      onClick={onClick}
      className={`p-2 border-2 rounded cursor-pointer ${border} ${bg} hover:shadow-md text-xs mb-1`}
      data-task-id={taskId}
    >
      <div className="text-gray-500 text-xs">{topicName}</div>
      <div className="font-medium">{taskText}</div>
      {nextStep && <div className="text-gray-600 mt-1">→ {nextStep}</div>}
      {owner && <div className="text-gray-500">Owner: {owner}</div>}
      {status && <div className="text-gray-400 text-xs">{status}</div>}
      {keyTerms && keyTerms.length > 0 && (
        <div className="text-gray-400 mt-1">{keyTerms.join(', ')}</div>
      )}
    </div>
  );
}
