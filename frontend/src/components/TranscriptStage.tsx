"use client";

import { useEffect, useRef, useState } from "react";
import { callsAPI, transcriptionAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call } from "@/types";
import TranscriptionStatusBadge from "@/components/TranscriptionStatusBadge";
import ContextFiles from "@/components/ContextFiles";

interface Props {
  call: Call;
  onAdvance: () => void;
}

// Rough estimate: ~15s fixed overhead (Metal buffer init) + ~8s/MB
function estimateSeconds(bytes: number): number {
  return Math.round(15 + (bytes / (1024 * 1024)) * 8);
}

function formatRemaining(seconds: number): string {
  if (seconds <= 0) return "Almost done…";
  if (seconds < 60) return `~${seconds}s remaining`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s > 0 ? `~${m}m ${s}s remaining` : `~${m}m remaining`;
}

export default function TranscriptStage({ call, onAdvance }: Props) {
  const [uploading, setUploading] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [estimatedSecs, setEstimatedSecs] = useState<number | null>(null);

  // Review screen state — transcript lives here until user clicks "Save & continue"
  const [pendingTranscript, setPendingTranscript] = useState<string | null>(null);
  const [pendingFilename, setPendingFilename] = useState<string | null>(null);
  const [editedTranscript, setEditedTranscript] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const mp3Ref = useRef<HTMLInputElement>(null);
  const txtRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!uploading) { setElapsed(0); return; }
    const interval = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(interval);
  }, [uploading]);

  useEffect(() => {
    if (!uploading) return;
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [uploading]);

  async function handleMp3Change(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    const online = await transcriptionAPI.health();
    if (!online) {
      setUploadError("Server is offline. Use the Start server button above.");
      return;
    }

    setEstimatedSecs(estimateSeconds(file.size));
    setUploading(true);
    setUploadError(null);
    try {
      setStatusMsg("Transcribing… this may take a few minutes.");
      logger.info("Starting MP3 transcription", { component: "TranscriptStage", data: { callId: call.id } });
      const transcript = await transcriptionAPI.transcribe(file);
      logger.info("Transcription complete", { component: "TranscriptStage", data: { callId: call.id } });
      setPendingTranscript(transcript);
      setPendingFilename(file.name);
      setEditedTranscript(transcript);
    } catch (err) {
      logger.error("Transcription failed", { component: "TranscriptStage", data: err });
      setUploadError(err instanceof Error ? err.message : "Transcription failed. Please try again.");
    } finally {
      setUploading(false);
      setStatusMsg(null);
    }
  }

  async function handleTxtChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    setUploading(true);
    setUploadError(null);
    try {
      setStatusMsg("Reading file…");
      const text = await file.text();
      setPendingTranscript(text);
      setPendingFilename(file.name);
      setEditedTranscript(text);
      logger.info("TXT file read", { component: "TranscriptStage", data: { callId: call.id } });
    } catch (err) {
      logger.error("TXT read failed", { component: "TranscriptStage", data: err });
      setUploadError(err instanceof Error ? err.message : "Failed to read file. Please try again.");
    } finally {
      setUploading(false);
      setStatusMsg(null);
    }
  }

  function handleDownload() {
    const filename = `transcript_${call.title.replace(/\s+/g, "_")}.txt`;
    const blob = new Blob([editedTranscript], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleReplace() {
    setPendingTranscript(null);
    setPendingFilename(null);
    setEditedTranscript("");
    setSaveError(null);
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      await callsAPI.submitTranscript(call.id, editedTranscript, pendingFilename ?? undefined);
      logger.info("Transcript saved", { component: "TranscriptStage", data: { callId: call.id } });
      onAdvance();
    } catch (err) {
      logger.error("Transcript save failed", { component: "TranscriptStage", data: err });
      setSaveError(err instanceof Error ? err.message : "Failed to save. Please try again.");
      setSaving(false);
    }
  }

  // ── Transcribing / reading state ───────────────────────────────────────────
  if (uploading) {
    const remaining = estimatedSecs !== null ? estimatedSecs - elapsed : null;
    return (
      <div className="bg-white border border-[#dfe1e6] rounded-lg">
        <div className="px-4 py-3 border-b border-[#dfe1e6] flex items-center justify-between">
          <span className="text-[14px] font-semibold text-[#172b4d]">Get Transcript</span>
          <TranscriptionStatusBadge />
        </div>
        <div className="p-8 text-center">
          <div className="text-2xl mb-3 animate-spin">⏳</div>
          <div className="text-[13px] font-medium text-[#172b4d] mb-1">{statusMsg}</div>
          <div className="text-[12px] text-[#5e6c84] mb-2">Do not close this tab.</div>
          <div className="text-[12px] font-mono text-[#97a0af]">
            {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")} elapsed
            {remaining !== null && (
              <span className="ml-2 text-[#5e6c84]">· {formatRemaining(remaining)}</span>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ── Review screen ──────────────────────────────────────────────────────────
  if (pendingTranscript !== null) {
    return (
      <div className="bg-white border border-[#dfe1e6] rounded-lg">
        <div className="px-4 py-3 border-b border-[#dfe1e6] flex items-center justify-between">
          <div>
            <span className="text-[14px] font-semibold text-[#172b4d]">Review Transcript</span>
            {pendingFilename && (
              <span className="ml-2 text-[12px] text-[#5e6c84]">From: {pendingFilename}</span>
            )}
          </div>
          <TranscriptionStatusBadge />
        </div>
        <div className="p-4">
          {saveError && (
            <div className="mb-3 text-[12px] text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
              {saveError}
            </div>
          )}

          <textarea
            value={editedTranscript}
            onChange={(e) => setEditedTranscript(e.target.value)}
            className="w-full h-64 text-[12px] font-mono text-[#172b4d] bg-[#f4f5f7] border border-[#dfe1e6] rounded p-3 resize-none focus:outline-none focus:border-[#0052cc] mb-4"
            spellCheck={false}
          />

          <ContextFiles call={call} />

          <div className="flex items-center justify-between mt-4">
            <div className="flex items-center gap-4">
              <button
                onClick={handleDownload}
                className="text-[12px] text-[#5e6c84] hover:text-[#0052cc] hover:underline"
              >
                ↓ Download .txt
              </button>
              <button
                onClick={handleReplace}
                className="text-[12px] text-[#5e6c84] hover:text-[#172b4d] hover:underline"
              >
                ← Replace
              </button>
            </div>
            <button
              onClick={handleSave}
              disabled={saving || !editedTranscript.trim()}
              className="px-4 py-2 bg-[#0052cc] text-white text-[13px] font-semibold rounded hover:bg-[#0747a6] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? "Saving…" : "Save & continue →"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Upload screen ──────────────────────────────────────────────────────────
  return (
    <div className="bg-white border border-[#dfe1e6] rounded-lg">
      <div className="px-4 py-3 border-b border-[#dfe1e6] flex items-center justify-between">
        <span className="text-[14px] font-semibold text-[#172b4d]">Get Transcript</span>
        <TranscriptionStatusBadge />
      </div>
      <div className="p-4">
        {uploadError && (
          <div className="mb-3 text-[12px] text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
            {uploadError}
          </div>
        )}

        <div
          onClick={() => mp3Ref.current?.click()}
          className="border-2 border-dashed border-[#dfe1e6] rounded-md p-6 text-center cursor-pointer hover:border-[#0052cc] hover:bg-[#f8f9ff] transition-colors mb-3"
        >
          <div className="text-2xl mb-2">🎵</div>
          <div className="text-[14px] font-semibold text-[#172b4d] mb-1">Upload MP3</div>
          <div className="text-[12px] text-[#5e6c84]">Transcribed locally via mlx-whisper</div>
        </div>
        <input ref={mp3Ref} type="file" accept=".mp3" className="hidden" onChange={handleMp3Change} />

        <div className="flex items-center gap-2 my-3">
          <hr className="flex-1 border-[#dfe1e6]" />
          <span className="text-[11px] text-[#97a0af] uppercase tracking-wide">or</span>
          <hr className="flex-1 border-[#dfe1e6]" />
        </div>

        <div
          onClick={() => txtRef.current?.click()}
          className="border-2 border-dashed border-[#dfe1e6] rounded-md p-6 text-center cursor-pointer hover:border-[#0052cc] hover:bg-[#f8f9ff] transition-colors"
        >
          <div className="text-2xl mb-2">📄</div>
          <div className="text-[14px] font-semibold text-[#172b4d] mb-1">Upload transcript (.txt)</div>
          <div className="text-[12px] text-[#5e6c84]">Already have a transcript? Upload it directly.</div>
        </div>
        <input ref={txtRef} type="file" accept=".txt" className="hidden" onChange={handleTxtChange} />
      </div>
      <ContextFiles call={call} />
    </div>
  );
}
