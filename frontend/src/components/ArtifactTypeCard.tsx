"use client";

import { useState } from "react";
import type { ArtifactType, LLMProvider, ContextScope } from "@/types";

const LLM_OPTIONS: { value: LLMProvider; label: string }[] = [
  { value: "groq",     label: "Groq – Llama 3.3 (free)" },
  { value: "deepseek", label: "DeepSeek Chat (~free)" },
  { value: "claude",   label: "Claude Haiku" },
  { value: "openai",   label: "GPT-4o mini" },
];

const LLM_LABELS: Record<LLMProvider, string> = Object.fromEntries(
  LLM_OPTIONS.map((o) => [o.value, o.label])
) as Record<LLMProvider, string>;

type Props = {
  type: ArtifactType;
  projectDefaultLlm: LLMProvider;
  onDelete: (id: string) => void;
  onUpdate: (id: string, data: { name?: string; prompt?: string; llm?: LLMProvider | null; context_scope?: ContextScope }) => Promise<void>;
  hideDelete?: boolean;
};

export default function ArtifactTypeCard({ type, projectDefaultLlm, onDelete, onUpdate, hideDelete }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(type.name);
  const [prompt, setPrompt] = useState(type.prompt);
  const [llm, setLlm] = useState<LLMProvider | null>(type.llm);
  const [contextScope, setContextScope] = useState<ContextScope>(type.context_scope ?? "call");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  function handleCancelEdit() {
    setEditing(false);
    setName(type.name);
    setPrompt(type.prompt);
    setLlm(type.llm);
    setContextScope(type.context_scope ?? "call");
    setSaveError(null);
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      await onUpdate(type.id, { name, prompt, llm, context_scope: contextScope });
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
            {type.is_default ? "Default" : "Artifacts"}
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

        {/* LLM + context scope — always visible in header */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {editing ? (
            <>
              <select
                value={llm ?? ""}
                onChange={(e) => setLlm((e.target.value as LLMProvider) || null)}
                className="text-[11px] border border-[#dfe1e6] rounded px-2 py-1 bg-white text-[#172b4d] focus:outline-none focus:border-[#0052cc]"
              >
                <option value="">Default ({LLM_LABELS[projectDefaultLlm]})</option>
                {LLM_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              <select
                value={contextScope}
                onChange={(e) => setContextScope(e.target.value as ContextScope)}
                className="text-[11px] border border-[#dfe1e6] rounded px-2 py-1 bg-white text-[#172b4d] focus:outline-none focus:border-[#0052cc]"
              >
                <option value="call">Call only</option>
                <option value="project">Full project</option>
              </select>
            </>
          ) : (
            <>
              <span className="text-[11px] text-[#5e6c84] bg-[#f4f5f7] px-2 py-[3px] rounded">
                {type.llm
                  ? LLM_LABELS[type.llm]
                  : `Default · ${LLM_LABELS[projectDefaultLlm]}`}
              </span>
              <span
                className="text-[10px] font-medium px-2 py-[3px] rounded"
                style={
                  (type.context_scope ?? "call") === "project"
                    ? { background: "#e3fcef", color: "#006644" }
                    : { background: "#f4f5f7", color: "#5e6c84" }
                }
              >
                {(type.context_scope ?? "call") === "project" ? "Full project" : "Call only"}
              </span>
            </>
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
              {!hideDelete && (
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
