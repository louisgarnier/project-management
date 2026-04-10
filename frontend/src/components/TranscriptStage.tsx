"use client";

import { useEffect, useRef, useState } from "react";
import { callsAPI, transcriptionAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call } from "@/types";
import TranscriptionStatusBadge from "@/components/TranscriptionStatusBadge";

interface Props {
  call: Call;
  onAdvance: () => void;
}

export default function TranscriptStage({ call, onAdvance }: Props) {
  const [uploading, setUploading] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [review, setReview] = useState<{ text: string; source: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const mp3Ref = useRef<HTMLInputElement>(null);
  const txtRef = useRef<HTMLInputElement>(null);

  // Elapsed timer during upload/transcription
  useEffect(() => {
    if (!uploading) { setElapsed(0); return; }
    const interval = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(interval);
  }, [uploading]);

  // Prevent tab close during upload
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
      setError("Server is offline. Use the Start server button above.");
      return;
    }

    setUploading(true);
    setError(null);
    try {
      setStatusMsg("Transcribing… this may take a few minutes.");
      logger.info("Starting MP3 transcription", { component: "TranscriptStage", data: { callId: call.id } });
      const transcript = await transcriptionAPI.transcribe(file);
      setReview({ text: transcript, source: file.name });
      logger.info("Transcription complete, showing review", { component: "TranscriptStage" });
    } catch (err) {
      logger.error("Transcription failed", { component: "TranscriptStage", data: err });
      setError(err instanceof Error ? err.message : "Transcription failed. Please try again.");
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
    setError(null);
    try {
      setStatusMsg("Reading file…");
      const text = await file.text();
      setReview({ text, source: file.name });
      logger.info("TXT loaded, showing review", { component: "TranscriptStage" });
    } catch (err) {
      logger.error("TXT read failed", { component: "TranscriptStage", data: err });
      setError(err instanceof Error ? err.message : "Failed to read file. Please try again.");
    } finally {
      setUploading(false);
      setStatusMsg(null);
    }
  }

  function handleDownload() {
    if (!review) return;
    const blob = new Blob([review.text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `transcript_${call.title.replace(/\s+/g, "_")}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    logger.info("Transcript downloaded", { component: "TranscriptStage" });
  }

  async function handleSave() {
    if (!review || !review.text.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await callsAPI.submitTranscript(call.id, review.text, review.source);
      logger.info("Transcript saved and advanced", { component: "TranscriptStage", data: { callId: call.id } });
      onAdvance();
    } catch (err) {
      logger.error("Save failed", { component: "TranscriptStage", data: err });
      setError(err instanceof Error ? err.message : "Save failed. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  // ── Review screen ──────────────────────────────────────────────────────────
  if (review) {
    return (
      <div className="bg-white border border-[#dfe1e6] rounded-lg flex flex-col" style={{ minHeight: "480px" }}>
        <div className="px-4 py-3 border-b border-[#dfe1e6] flex items-center justify-between flex-shrink-0">
          <div>
            <span className="text-[14px] font-semibold text-[#172b4d]">Review Transcript</span>
            <span className="text-[12px] text-[#5e6c84] ml-2">From: {review.source}</span>
          </div>
          <button
            onClick={() => { setReview(null); setError(null); }}
            className="text-[12px] text-[#5e6c84] hover:text-[#172b4d] hover:underline"
          >
            ↩ Replace
          </button>
        </div>

        <div className="flex-1 p-4 flex flex-col">
          <textarea
            className="flex-1 w-full font-mono text-[12px] text-[#172b4d] border border-[#dfe1e6] rounded p-3 resize-none focus:outline-none focus:border-[#0052cc]"
            style={{ minHeight: "320px" }}
            value={review.text}
            onChange={(e) => setReview({ ...review, text: e.target.value })}
          />
          {error && (
            <div className="mt-2 text-[12px] text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
              {error}
            </div>
          )}
        </div>

        <div className="px-4 py-3 border-t border-[#dfe1e6] flex items-center justify-between flex-shrink-0">
          <button
            onClick={handleDownload}
            className="text-[12px] text-[#0052cc] hover:underline"
          >
            ↓ Download .txt
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !review.text.trim()}
            className="text-[13px] font-medium bg-[#0052cc] text-white px-4 py-1.5 rounded hover:bg-[#0747a6] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? "Saving…" : "Save & continue →"}
          </button>
        </div>
      </div>
    );
  }

  // ── Transcribing/uploading state ───────────────────────────────────────────
  if (uploading) {
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
        {error && (
          <div className="mb-3 text-[12px] text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
            {error}
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
    </div>
  );
}
