"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { callsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call } from "@/types";
import TranscriptStage from "@/components/TranscriptStage";
import TranscriptPanel from "@/components/TranscriptPanel";
import ContextFiles from "@/components/ContextFiles";

const STAGES = ["transcript", "artifacts", "topics", "done"] as const;

export default function CallDetailPage() {
  const params = useParams<{ id: string; call_id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { id: projectId, call_id: callId } = params;

  const viewStage = searchParams.get("view"); // set when navigating from a historical card

  const [call, setCall] = useState<Call | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function handleResetTranscript() {
    if (!confirm("Delete the transcript and roll back to Get Transcript stage? This cannot be undone.")) return;
    try {
      const updated = await callsAPI.resetTranscript(callId);
      logger.info("Transcript reset", { component: "CallDetailPage", data: { callId } });
      setCall(updated);
    } catch (err) {
      logger.error("Failed to reset transcript", { component: "CallDetailPage", data: err });
    }
  }

  const loadCall = useCallback(async () => {
    try {
      logger.info("Fetching call", { component: "CallDetailPage", data: { callId } });
      const data = await callsAPI.getCall(callId);
      setCall(data);
    } catch (err) {
      logger.error("Failed to load call", { component: "CallDetailPage", data: err });
      setError("Failed to load call.");
    } finally {
      setLoading(false);
    }
  }, [callId]);

  useEffect(() => {
    loadCall();
  }, [loadCall]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-[13px] text-[#5e6c84]">Loading…</p>
      </div>
    );
  }

  if (error || !call) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-[13px] text-red-600">{error ?? "Call not found."}</p>
      </div>
    );
  }

  // Transcript-only mode: navigated from a historical "Get Transcript" card
  if (viewStage === "transcript" && call.transcript) {
    return (
      <div className="h-full flex flex-col">
        <div className="px-5 pt-4 pb-3 bg-white border-b border-[#dfe1e6] flex-shrink-0">
          <button
            onClick={() => router.push(`/projects/${projectId}/board`)}
            className="text-[12px] text-[#5e6c84] hover:text-[#0052cc] hover:underline mb-2 block"
          >
            ← Board
          </button>
          <h1 className="text-[18px] font-bold text-[#172b4d]">{call.title}</h1>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          <TranscriptPanel
            call={call}
            onSaved={(updated) => setCall(updated)}
            defaultOpen={true}
          />
          <ContextFiles call={call} readonly />
        </div>
      </div>
    );
  }

  const currentIdx = STAGES.indexOf(call.kanban_stage);
  const isPastTranscript = call.kanban_stage !== "transcript";

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="px-5 pt-4 pb-3 bg-white border-b border-[#dfe1e6] flex-shrink-0">
        <button
          onClick={() => router.push(`/projects/${projectId}/board`)}
          className="text-[12px] text-[#5e6c84] hover:text-[#0052cc] hover:underline mb-2 block"
        >
          ← Board
        </button>
        <h1 className="text-[18px] font-bold text-[#172b4d]">{call.title}</h1>
      </div>

      {/* Stage progress */}
      <div className="px-5 py-2.5 bg-white border-b border-[#dfe1e6] flex items-center gap-1 flex-shrink-0">
        {STAGES.map((stage, i) => {
          const isCurrent = stage === call.kanban_stage;
          const isDone = i < currentIdx;
          return (
            <div key={stage} className="flex items-center gap-1">
              {i > 0 && <span className="text-[#dfe1e6] text-sm mx-0.5">›</span>}
              <span
                className={`text-[12px] font-medium px-2.5 py-1 rounded ${
                  isCurrent
                    ? "bg-[#e9f0ff] text-[#0052cc]"
                    : isDone
                    ? "text-[#36b37e]"
                    : "text-[#97a0af]"
                }`}
              >
                {isCurrent && "● "}
                {stage.charAt(0).toUpperCase() + stage.slice(1)}
              </span>
            </div>
          );
        })}
      </div>

      {/* Stage content */}
      <div className="flex-1 overflow-y-auto p-5">
        {call.kanban_stage === "transcript" && (
          <TranscriptStage call={call} onAdvance={loadCall} />
        )}
        {isPastTranscript && (
          <>
            <div className="flex items-center justify-center py-12">
              <p className="text-[13px] text-[#5e6c84]">
                {call.kanban_stage.charAt(0).toUpperCase() + call.kanban_stage.slice(1)} stage — coming soon.
              </p>
            </div>
            {call.transcript && (
              <TranscriptPanel
                call={call}
                onSaved={(updated) => setCall(updated)}
              />
            )}
            <ContextFiles call={call} readonly />
            {call.kanban_stage === "artifacts" && (
              <div className="mt-4 text-right">
                <button
                  onClick={handleResetTranscript}
                  className="text-[11px] text-[#97a0af] hover:text-red-500 hover:underline"
                >
                  ↩ Reset transcript
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
