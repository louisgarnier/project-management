"use client";

import { useEffect, useRef, useState } from "react";
import { callsAPI, transcriptionAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call } from "@/types";
import TranscriptionStatusBadge from "@/components/TranscriptionStatusBadge";
import OfflineModal from "@/components/OfflineModal";

interface Props {
  call: Call;
  onAdvance: () => void;
}

export default function TranscriptStage({ call, onAdvance }: Props) {
  const [uploading, setUploading] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showOfflineModal, setShowOfflineModal] = useState(false);
  const mp3Ref = useRef<HTMLInputElement>(null);
  const txtRef = useRef<HTMLInputElement>(null);

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
      logger.info("Transcription server offline — showing modal", { component: "TranscriptStage" });
      setShowOfflineModal(true);
      return;
    }

    setUploading(true);
    setError(null);
    let success = false;
    try {
      setStatusMsg("Transcribing… this may take a few minutes.");
      logger.info("Starting MP3 transcription", { component: "TranscriptStage", data: { callId: call.id } });
      const transcript = await transcriptionAPI.transcribe(file);
      setStatusMsg("Saving transcript…");
      await callsAPI.submitTranscript(call.id, transcript);
      logger.info("Transcript submitted", { component: "TranscriptStage", data: { callId: call.id } });
      success = true;
    } catch (err) {
      logger.error("Transcription failed", { component: "TranscriptStage", data: err });
      setError(err instanceof Error ? err.message : "Transcription failed. Please try again.");
    } finally {
      setUploading(false);
      setStatusMsg(null);
    }
    if (success) onAdvance();
  }

  async function handleTxtChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    setUploading(true);
    setError(null);
    let success = false;
    try {
      setStatusMsg("Reading file…");
      logger.info("Submitting .txt transcript", { component: "TranscriptStage", data: { callId: call.id } });
      const transcript = await file.text();
      setStatusMsg("Saving transcript…");
      await callsAPI.submitTranscript(call.id, transcript);
      logger.info("Transcript submitted", { component: "TranscriptStage", data: { callId: call.id } });
      success = true;
    } catch (err) {
      logger.error("TXT upload failed", { component: "TranscriptStage", data: err });
      setError(err instanceof Error ? err.message : "Upload failed. Please try again.");
    } finally {
      setUploading(false);
      setStatusMsg(null);
    }
    if (success) onAdvance();
  }

  if (uploading) {
    return (
      <div className="bg-white border border-[#dfe1e6] rounded-lg">
        <div className="px-4 py-3 border-b border-[#dfe1e6] flex items-center justify-between">
          <span className="text-[14px] font-semibold text-[#172b4d]">Get Transcript</span>
          <TranscriptionStatusBadge />
        </div>
        <div className="p-8 text-center">
          <div className="text-[13px] font-medium text-[#172b4d] mb-1">{statusMsg}</div>
          <div className="text-[12px] text-[#5e6c84]">Do not close this tab.</div>
        </div>
      </div>
    );
  }

  return (
    <>
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

          {/* MP3 upload */}
          <div
            onClick={() => mp3Ref.current?.click()}
            className="border-2 border-dashed border-[#dfe1e6] rounded-md p-6 text-center cursor-pointer hover:border-[#0052cc] hover:bg-[#f8f9ff] transition-colors mb-3"
          >
            <div className="text-2xl mb-2">🎵</div>
            <div className="text-[14px] font-semibold text-[#172b4d] mb-1">Upload MP3</div>
            <div className="text-[12px] text-[#5e6c84]">Transcribed locally via Whisper + pyannote</div>
          </div>
          <input ref={mp3Ref} type="file" accept=".mp3" className="hidden" onChange={handleMp3Change} />

          <div className="flex items-center gap-2 my-3">
            <hr className="flex-1 border-[#dfe1e6]" />
            <span className="text-[11px] text-[#97a0af] uppercase tracking-wide">or</span>
            <hr className="flex-1 border-[#dfe1e6]" />
          </div>

          {/* TXT upload */}
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

      {showOfflineModal && (
        <OfflineModal onDismiss={() => setShowOfflineModal(false)} />
      )}
    </>
  );
}
