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
  isFocused?: boolean;
  isSelected?: boolean;     // user clicked but not yet linked → amber
  groupColor?: { bg: string; border: string; text: string } | null;  // committed group color
  matchHint?: 'exact' | 'partial' | null;
  onClick?: () => void;
  onContextMenu?: (e: React.MouseEvent) => void;
}

export function TaskCard({
  taskId, topicName, taskText, nextStep, owner, status, keyTerms,
  isFocused, isSelected, groupColor, matchHint, onClick, onContextMenu,
}: TaskCardProps) {
  // Priority: focused > group > selected > matchHint > default
  let style: React.CSSProperties;
  if (isFocused) {
    style = { border: '2px dashed #8b5cf6', background: 'white' };
  } else if (groupColor) {
    style = { border: `2px solid ${groupColor.border}`, background: groupColor.bg, color: groupColor.text };
  } else if (isSelected) {
    style = { border: '2px solid #f6c000', background: '#fff0b3', color: '#7a4e00' };
  } else if (matchHint === 'exact') {
    style = { border: '2px solid #e2e8f0', background: '#fefce8' };
  } else if (matchHint === 'partial') {
    style = { border: '2px solid #e2e8f0', background: '#fff7ed' };
  } else {
    style = { border: '2px solid #e2e8f0', background: 'white' };
  }
  return (
    <div
      onClick={onClick}
      onContextMenu={onContextMenu}
      style={{
        padding: 8, borderRadius: 6, cursor: 'pointer', marginBottom: 4,
        fontSize: 12, transition: 'border-color .12s, background .12s',
        ...style,
      }}
      data-task-id={taskId}
    >
      <div style={{ fontSize: 10, color: '#6b7280' }}>{topicName}</div>
      <div style={{ fontWeight: 500 }}>{taskText}</div>
      {nextStep && <div style={{ color: '#6b7280', marginTop: 4 }}>→ {nextStep}</div>}
      {owner && <div style={{ color: '#6b7280', fontSize: 10 }}>Owner: {owner}</div>}
      {status && <div style={{ color: '#9ca3af', fontSize: 10 }}>{status}</div>}
      {keyTerms && keyTerms.length > 0 && (
        <div style={{ color: '#9ca3af', marginTop: 4, fontSize: 10 }}>{keyTerms.join(', ')}</div>
      )}
    </div>
  );
}
