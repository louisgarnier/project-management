"use client";

import { useState } from "react";
import type { Artifact, ArtifactType } from "@/types";

type Props = {
  artifact: Artifact;
  artifactType: ArtifactType | undefined;
  onMarkDone: (id: string, content: string) => Promise<void>;
  onRetry: (id: string) => void;
};

export default function ArtifactCard({ artifact, artifactType, onMarkDone, onRetry }: Props) {
  const [content, setContent] = useState(artifact.content ?? "");
  const [marking, setMarking] = useState(false);
  const [markError, setMarkError] = useState<string | null>(null);

  const isDone = artifact.status === "done";
  const isGenerating = artifact.status === "generating";
  const isPending = artifact.status === "pending";
  const isError = artifact.status === "error";

  async function handleMarkDone() {
    setMarking(true);
    setMarkError(null);
    try {
      await onMarkDone(artifact.id, content);
    } catch (err) {
      setMarkError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setMarking(false);
    }
  }

  const borderColor = isDone
    ? "#36b37e"
    : isError
    ? "#ff5630"
    : isGenerating
    ? "#ff8b00"
    : "#dfe1e6";

  return (
    <div
      className="border rounded-lg p-4 bg-white transition-colors"
      style={{ borderColor }}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <h3 className="text-[14px] font-semibold text-[#172b4d]">
          {artifactType?.name ?? "Artifact"}
        </h3>
        <StatusBadge status={artifact.status} mode={artifact.mode} />
      </div>

      {/* Content area */}
      {(isPending || isGenerating) && artifact.mode === "claude" ? (
        <div className="flex items-center gap-2 py-4">
          {isGenerating && (
            <svg className="animate-spin h-4 w-4 text-[#ff8b00]" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
          )}
          <p className="text-[12px] text-[#5e6c84]">
            {isGenerating ? "Generating…" : "Waiting to generate…"}
          </p>
        </div>
      ) : isError ? (
        <div className="py-3">
          <p className="text-[12px] text-red-600 mb-2">{artifact.error_message ?? "Generation failed."}</p>
          <button
            onClick={() => onRetry(artifact.id)}
            className="text-[11px] text-[#0052cc] hover:underline"
          >
            Retry
          </button>
        </div>
      ) : (
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder={artifact.mode === "manual" ? "Write your notes here…" : ""}
          className="w-full text-[12px] text-[#172b4d] bg-[#f4f5f7] border border-[#dfe1e6] rounded p-3 resize-none min-h-[100px] focus:outline-none focus:border-[#0052cc]"
        />
      )}

      {/* Mark Done */}
      {!isDone && !isGenerating && !isPending && !isError && (
        <div className="mt-3 flex items-center justify-between">
          {markError && <p className="text-[11px] text-red-600">{markError}</p>}
          <div className="flex-1" />
          <button
            onClick={handleMarkDone}
            disabled={marking || (!content.trim() && artifact.mode === "manual")}
            className="px-3 py-1.5 bg-[#0052cc] text-white text-[11px] font-medium rounded hover:bg-[#0747a6] disabled:opacity-50"
          >
            {marking ? "Saving…" : "Mark Done ✓"}
          </button>
        </div>
      )}

      {isDone && (
        <div className="mt-2 flex items-center gap-1">
          <span className="text-[11px] text-[#36b37e] font-medium">✓ Done</span>
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status, mode }: { status: string; mode: string }) {
  const configs: Record<string, { label: string; bg: string; color: string }> = {
    pending:    { label: "Pending",    bg: "#f4f5f7", color: "#5e6c84" },
    generating: { label: "Generating", bg: "#fff4e6", color: "#974f0c" },
    done:       { label: "Done",       bg: "#e3fcef", color: "#006644" },
    error:      { label: "Error",      bg: "#ffebe6", color: "#bf2600" },
  };
  const cfg = configs[status] ?? configs.pending;
  return (
    <span
      className="text-[9px] font-bold px-[5px] py-[1px] rounded uppercase tracking-[.04em]"
      style={{ background: cfg.bg, color: cfg.color }}
    >
      {mode === "manual" && status === "pending" ? "Manual" : cfg.label}
    </span>
  );
}
