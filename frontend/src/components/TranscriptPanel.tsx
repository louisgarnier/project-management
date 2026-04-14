"use client";

import { useState } from "react";
import { callsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call } from "@/types";

interface Props {
  call: Call;
  onSaved: (updated: Call) => void;
  defaultOpen?: boolean;
  readonly?: boolean;
}

export default function TranscriptPanel({ call, onSaved, defaultOpen = false, readonly = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const [text, setText] = useState(call.transcript ?? "");
  const [savedText, setSavedText] = useState(call.transcript ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isDirty = text !== savedText;

  async function handleSave() {
    if (!isDirty || !text.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await callsAPI.updateTranscript(call.id, text);
      logger.info("Transcript updated", { component: "TranscriptPanel", data: { callId: call.id } });
      onSaved(updated);
      setSavedText(text); // keep isDirty accurate regardless of when parent re-renders
    } catch (err) {
      logger.error("Transcript update failed", { component: "TranscriptPanel", data: err });
      setError(err instanceof Error ? err.message : "Save failed. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  function handleDownload() {
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `transcript_${call.title.replace(/\s+/g, "_")}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 100);
  }

  return (
    <div className="bg-white border border-[#dfe1e6] rounded-lg mt-4">
      {/* Header — always visible, click to expand/collapse */}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-[#f8f9ff] transition-colors rounded-lg"
      >
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-semibold text-[#172b4d]">Transcript</span>
          {call.transcript_source && (
            <span className="text-[11px] text-[#5e6c84]">· {call.transcript_source}</span>
          )}
          {isDirty && (
            <span className="text-[10px] text-[#ff8b00] font-medium">unsaved</span>
          )}
        </div>
        <span className="text-[#5e6c84] text-[12px]">{open ? "▲" : "▼"}</span>
      </button>

      {/* Body — only when expanded */}
      {open && (
        <div className="border-t border-[#dfe1e6]">
          {readonly ? (
            <pre className="p-4 font-mono text-[12px] text-[#172b4d] whitespace-pre-wrap leading-relaxed max-h-[400px] overflow-y-auto">
              {call.transcript ?? ""}
            </pre>
          ) : (
            <>
              <div className="p-4 flex flex-col">
                <textarea
                  className="w-full font-mono text-[12px] text-[#172b4d] border border-[#dfe1e6] rounded p-3 resize-none focus:outline-none focus:border-[#0052cc]"
                  style={{
                    minHeight: "280px",
                    opacity: call.is_locked ? 0.7 : 1,
                    cursor: call.is_locked ? "not-allowed" : "auto",
                  }}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  disabled={call.is_locked}
                  placeholder="Paste transcript here…"
                />
                {error && (
                  <div className="mt-2 text-[12px] text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
                    {error}
                  </div>
                )}
              </div>
              <div className="px-4 py-3 border-t border-[#dfe1e6] flex items-center justify-between">
                <button
                  onClick={handleDownload}
                  className="text-[12px] text-[#0052cc] hover:underline"
                >
                  ↓ Download .txt
                </button>
                {call.is_locked ? (
                  <span style={{ fontSize: 11, color: "#97a0af" }}>🔒 Locked — unlock to edit</span>
                ) : (
                  <button
                    onClick={handleSave}
                    disabled={!isDirty || saving || !text.trim()}
                    className="text-[13px] font-medium bg-[#0052cc] text-white px-4 py-1.5 rounded hover:bg-[#0747a6] disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {saving ? "Saving…" : "Save changes"}
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
