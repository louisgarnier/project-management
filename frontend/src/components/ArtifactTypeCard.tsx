"use client";

import { useState } from "react";
import type { ArtifactType } from "@/types";

type Props = {
  type: ArtifactType;
  onDelete: (id: string) => void;
  onUpdate: (id: string, data: { name?: string; prompt?: string }) => Promise<void>;
};

export default function ArtifactTypeCard({ type, onDelete, onUpdate }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(type.name);
  const [prompt, setPrompt] = useState(type.prompt);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  function handleCancelEdit() {
    setEditing(false);
    setName(type.name);
    setPrompt(type.prompt);
    setSaveError(null);
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      await onUpdate(type.id, { name, prompt });
      setEditing(false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="border rounded-lg p-4 bg-white transition-colors"
      style={{ borderColor: editing ? "#ff8b00" : "#dfe1e6" }}
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span
            className="text-[9px] font-bold px-[5px] py-[1px] rounded uppercase tracking-[.04em] flex-shrink-0"
            style={
              type.is_default
                ? { background: "#e9f0ff", color: "#0052cc" }
                : { background: "#f3f0ff", color: "#5243aa" }
            }
          >
            {type.is_default ? "Default" : "Custom"}
          </span>
          {editing ? (
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="text-[14px] font-semibold text-[#172b4d] border-b-2 border-[#0052cc] outline-none flex-1 min-w-0 bg-transparent"
            />
          ) : (
            <h3 className="text-[14px] font-semibold text-[#172b4d] truncate">{type.name}</h3>
          )}
        </div>

        <div className="flex items-center gap-3 flex-shrink-0">
          {editing ? (
            <>
              <button
                onClick={handleCancelEdit}
                className="text-[11px] text-[#97a0af] hover:text-[#172b4d]"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !name.trim() || !prompt.trim()}
                className="text-[11px] text-[#0052cc] hover:underline disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => {
                  setEditing(true);
                  setExpanded(true);
                }}
                className="text-[11px] text-[#5e6c84] hover:text-[#0052cc] hover:underline"
              >
                Edit
              </button>
              {!type.is_default && (
                <button
                  onClick={() => {
                    if (confirm(`Delete "${type.name}"? This cannot be undone.`)) {
                      onDelete(type.id);
                    }
                  }}
                  className="text-[11px] text-[#97a0af] hover:text-red-500"
                >
                  ✕
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Expand toggle */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="mt-2 text-[11px] text-[#5e6c84] hover:text-[#0052cc] flex items-center gap-1"
      >
        <span>{expanded ? "▾" : "▸"}</span>
        <span>{expanded ? "Hide prompt" : "View prompt"}</span>
      </button>

      {/* Prompt — read or edit */}
      {expanded &&
        (editing ? (
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            className="mt-2 w-full text-[12px] text-[#172b4d] bg-[#f4f5f7] border border-[#dfe1e6] rounded p-3 resize-none h-32 focus:outline-none focus:border-[#0052cc]"
          />
        ) : (
          <p className="mt-2 text-[12px] text-[#5e6c84] leading-relaxed whitespace-pre-wrap bg-[#f4f5f7] rounded p-3">
            {type.prompt}
          </p>
        ))}

      {saveError && <p className="mt-2 text-[11px] text-red-600">{saveError}</p>}
    </div>
  );
}
