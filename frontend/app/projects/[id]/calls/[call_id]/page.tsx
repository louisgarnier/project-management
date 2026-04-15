"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { artifactsAPI, callsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call } from "@/types";
import TranscriptStage from "@/components/TranscriptStage";
import TranscriptPanel from "@/components/TranscriptPanel";
import ContextFiles from "@/components/ContextFiles";
import ArtifactsStage from "@/components/ArtifactsStage";
import ArtifactsPanel from "@/components/ArtifactsPanel";
import TopicsStage from "@/components/TopicsStage";
import TopicsPanel from "@/components/TopicsPanel";
import CallTopicsStage from "@/components/CallTopicsStage";
import ProjectMatchingStage from "@/components/ProjectMatchingStage";
import ProjectUpdatesStage from "@/components/ProjectUpdatesStage";
import ProjectMatchingHistoricalView from "@/components/ProjectMatchingHistoricalView";
import ProjectUpdatesHistoricalView from "@/components/ProjectUpdatesHistoricalView";
import CallTopicsHistoricalView from "@/components/CallTopicsHistoricalView";

const STAGES = ["transcript", "call_topics", "project_matching", "project_updates", "artifacts", "done"] as const;

const STAGE_LABELS: Record<string, string> = {
  transcript:       "Transcript",
  call_topics:      "Call Topics",
  project_matching: "Project Matching",
  project_updates:  "Project Updates",
  artifacts:        "Artifacts",
  done:             "Done",
};

const ROLLBACK_CLEARS: Record<string, string[]> = {
  transcript:       ["Call Topics", "Project Matching", "Project Updates", "Artifacts"],
  call_topics:      ["Project Matching", "Project Updates", "Artifacts"],
  project_matching: ["Project Updates", "Artifacts"],
  project_updates:  ["Artifacts"],
  artifacts:        ["Artifacts"],
};

export default function CallDetailPage() {
  const params = useParams<{ id: string; call_id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { id: projectId, call_id: callId } = params;

  const viewStage = searchParams.get("view"); // set when navigating from a historical card

  const [call, setCall] = useState<Call | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showResetModal, setShowResetModal] = useState(false);
  const [resetDeleteArtifacts, setResetDeleteArtifacts] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [rollbackTarget, setRollbackTarget] = useState<string | null>(null);
  const [rolling, setRolling] = useState(false);
  const [rollbackError, setRollbackError] = useState<string | null>(null);
  const [isLocking, setIsLocking] = useState(false);
  const [lockError, setLockError] = useState<string | null>(null);
  async function handleConfirmReset() {
    setResetting(true);
    try {
      if (resetDeleteArtifacts) {
        await artifactsAPI.deleteAll(callId);
      }
      const updated = await callsAPI.resetTranscript(callId);
      logger.info("Transcript reset", { component: "CallDetailPage", data: { callId, deletedArtifacts: resetDeleteArtifacts } });
      setCall(updated);
      setShowResetModal(false);
      setResetDeleteArtifacts(false);
    } catch (err) {
      logger.error("Failed to reset transcript", { component: "CallDetailPage", data: err });
    } finally {
      setResetting(false);
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

  async function handleRollback() {
    if (!rollbackTarget) return;
    setRolling(true);
    setRollbackError(null);
    try {
      await callsAPI.rollback(callId, rollbackTarget);
      setRollbackTarget(null);
      await loadCall();
      if (viewStage) {
        router.push(`/projects/${projectId}/calls/${callId}`);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      // 409 means the call is already at (or before) the target stage —
      // treat this as success: the state is already what we want, just reload.
      if (msg.includes("already at or before")) {
        setRollbackTarget(null);
        await loadCall();
        if (viewStage) {
          router.push(`/projects/${projectId}/calls/${callId}`);
        }
      } else {
        setRollbackError(msg || "Rollback failed");
      }
    } finally {
      setRolling(false);
    }
  }

  function renderRollbackModal() {
    if (!rollbackTarget) return null;
    return (
      <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
        <div className="bg-white rounded-lg shadow-lg w-full max-w-sm p-6">
          <h2 className="text-[16px] font-semibold text-[#172b4d] mb-2">
            Edit from {STAGE_LABELS[rollbackTarget] ?? rollbackTarget}?
          </h2>
          <p className="text-[13px] text-[#5e6c84] mb-3">
            Rolling back will clear the following data for this call:
          </p>
          <ul className="text-[12px] text-[#172b4d] mb-4 space-y-1">
            {(ROLLBACK_CLEARS[rollbackTarget] ?? []).map((item) => (
              <li key={item} className="flex items-center gap-2">
                <span className="text-red-400">✕</span> {item}
              </li>
            ))}
          </ul>
          <p className="text-[11px] text-[#97a0af] mb-4">
            Data from other calls is never affected.
          </p>
          {rollbackError && (
            <p className="text-[12px] text-red-600 mb-3">{rollbackError}</p>
          )}
          <div className="flex justify-end gap-3">
            <button
              onClick={() => { setRollbackTarget(null); setRollbackError(null); }}
              disabled={rolling}
              className="text-[13px] text-[#5e6c84] hover:text-[#172b4d] disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={handleRollback}
              disabled={rolling}
              className="px-4 py-2 bg-[#de350b] text-white text-[13px] font-medium rounded hover:bg-red-700 disabled:opacity-50"
            >
              {rolling ? "Rolling back…" : "Confirm & Edit"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  useEffect(() => {
    loadCall();
  }, [loadCall]);

  async function handleLock() {
    setIsLocking(true);
    setLockError(null);
    try {
      const updated = await callsAPI.lock(callId);
      setCall(updated);
    } catch (err) {
      logger.error("Failed to lock call", { component: "CallDetailPage", data: err });
      setLockError("Failed to lock call. Please try again.");
    } finally {
      setIsLocking(false);
    }
  }

  async function handleUnlock() {
    setIsLocking(true);
    setLockError(null);
    try {
      const updated = await callsAPI.unlock(callId);
      setCall(updated);
    } catch (err) {
      logger.error("Failed to unlock call", { component: "CallDetailPage", data: err });
      setLockError("Failed to unlock call. Please try again.");
    } finally {
      setIsLocking(false);
    }
  }

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
          <div className="flex items-center justify-between">
            <h1 className="text-[18px] font-bold text-[#172b4d]">{call.title}</h1>
            <button
              onClick={() => setRollbackTarget(viewStage!)}
              className="text-[12px] font-medium px-3 py-1.5 rounded border border-[#dfe1e6] text-[#5e6c84] hover:border-[#0052cc] hover:text-[#0052cc] transition-colors"
            >
              ✏️ Edit
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          <TranscriptPanel
            call={call}
            onSaved={(updated) => setCall(updated)}
            defaultOpen={true}
            readonly
          />
          <ContextFiles call={call} readonly />
          {call.kanban_stage === "artifacts" && (
            <div className="mt-4 text-right">
              <button
                onClick={() => setShowResetModal(true)}
                className="text-[11px] text-[#97a0af] hover:text-red-500 hover:underline"
              >
                ↩ Reset transcript
              </button>
            </div>
          )}
        </div>
        {renderRollbackModal()}
      </div>
    );
  }

  // Artifacts-only mode: navigated from a historical artifacts card
  if (viewStage === "artifacts") {
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
          <ArtifactsPanel callId={callId} projectId={projectId} defaultOpen call={call} />
          {call.transcript && <TranscriptPanel call={call} onSaved={(updated) => setCall(updated)} />}
          <ContextFiles call={call} readonly />
        </div>
      </div>
    );
  }

  // Call Topics-only mode: navigated from a historical call_topics card
  if (viewStage === "call_topics") {
    return (
      <div className="h-full flex flex-col">
        <div className="px-5 pt-4 pb-3 bg-white border-b border-[#dfe1e6] flex-shrink-0">
          <button
            onClick={() => router.push(`/projects/${projectId}/board`)}
            className="text-[12px] text-[#5e6c84] hover:text-[#0052cc] hover:underline mb-2 block"
          >
            ← Board
          </button>
          <div className="flex items-center justify-between">
            <h1 className="text-[18px] font-bold text-[#172b4d]">{call.title}</h1>
            <button
              onClick={() => setRollbackTarget(viewStage!)}
              className="text-[12px] font-medium px-3 py-1.5 rounded border border-[#dfe1e6] text-[#5e6c84] hover:border-[#0052cc] hover:text-[#0052cc] transition-colors"
            >
              ✏️ Edit
            </button>
          </div>
        </div>
        <CallTopicsHistoricalView callId={callId} call={call} />
        {renderRollbackModal()}
      </div>
    );
  }

  // Project Matching historical view — read-only two-column layout
  if (viewStage === "project_matching") {
    return (
      <div className="h-full flex flex-col">
        <div className="px-5 pt-4 pb-3 bg-white border-b border-[#dfe1e6] flex-shrink-0">
          <button onClick={() => router.push(`/projects/${projectId}/board`)}
            className="text-[12px] text-[#5e6c84] hover:text-[#0052cc] hover:underline mb-2 block">
            ← Board
          </button>
          <div className="flex items-center justify-between">
            <h1 className="text-[18px] font-bold text-[#172b4d]">{call.title}</h1>
            <button
              onClick={() => setRollbackTarget(viewStage!)}
              className="text-[12px] font-medium px-3 py-1.5 rounded border border-[#dfe1e6] text-[#5e6c84] hover:border-[#0052cc] hover:text-[#0052cc] transition-colors"
            >
              ✏️ Edit
            </button>
          </div>
        </div>
        <ProjectMatchingHistoricalView callId={callId} projectId={projectId} />
        {renderRollbackModal()}
      </div>
    );
  }

  // Project Updates historical view
  if (viewStage === "project_updates") {
    return (
      <div className="h-full flex flex-col">
        <div className="px-5 pt-4 pb-3 bg-white border-b border-[#dfe1e6] flex-shrink-0">
          <button
            onClick={() => router.push(`/projects/${projectId}/board`)}
            className="text-[12px] text-[#5e6c84] hover:text-[#0052cc] hover:underline mb-2 block"
          >
            ← Board
          </button>
          <div className="flex items-center justify-between">
            <h1 className="text-[18px] font-bold text-[#172b4d]">{call.title}</h1>
            <button
              onClick={() => setRollbackTarget(viewStage!)}
              className="text-[12px] font-medium px-3 py-1.5 rounded border border-[#dfe1e6] text-[#5e6c84] hover:border-[#0052cc] hover:text-[#0052cc] transition-colors"
            >
              ✏️ Edit
            </button>
          </div>
        </div>
        <ProjectUpdatesHistoricalView callId={callId} projectId={projectId} />
        {renderRollbackModal()}
      </div>
    );
  }

  // Done view: navigated from a historical done card
  if (viewStage === "done") {
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
          <TopicsPanel callId={callId} projectId={projectId} defaultOpen call={call} />
          <ArtifactsPanel callId={callId} projectId={projectId} call={call} />
          {call.transcript && <TranscriptPanel call={call} onSaved={(updated) => setCall(updated)} />}
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
              {isDone ? (
                <button
                  onClick={() => setRollbackTarget(stage)}
                  className="text-[12px] font-medium px-2.5 py-1 rounded text-[#36b37e] hover:bg-[#e3fcef] hover:text-[#006644] transition-colors"
                  title={`Edit from ${STAGE_LABELS[stage] ?? stage}`}
                >
                  {STAGE_LABELS[stage] ?? stage}
                </button>
              ) : (
                <span
                  className={`text-[12px] font-medium px-2.5 py-1 rounded ${
                    isCurrent
                      ? "bg-[#e9f0ff] text-[#0052cc]"
                      : "text-[#97a0af]"
                  }`}
                >
                  {isCurrent && "● "}
                  {STAGE_LABELS[stage] ?? stage}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Stage content — two rendering paths:
          Path A: project_matching / project_updates need flex-1 + overflow-hidden so their
                  internal two-column layouts can stretch to fill available height.
          Path B: all other stages scroll normally inside overflow-y-auto. */}
      {call.kanban_stage === "project_matching" || call.kanban_stage === "project_updates" ? (
        <div className="flex-1 overflow-hidden flex flex-col">
          {call.kanban_stage === "project_matching" && (
            <ProjectMatchingStage
              callId={call.id}
              projectId={call.project_id}
              onMatchingComplete={() => loadCall()}
            />
          )}
          {call.kanban_stage === "project_updates" && (
            <ProjectUpdatesStage
              callId={call.id}
              projectId={call.project_id}
              call={call}
              onValidated={() => loadCall()}
              onPollCall={loadCall}
            />
          )}
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-5">
          {call.kanban_stage === "transcript" && (
            <TranscriptStage
              key={call.transcript ? "has-transcript" : "empty"}
              call={call}
              onAdvance={loadCall}
              onDeleteTranscript={call.transcript ? async () => {
                await callsAPI.resetTranscript(callId);
                await loadCall();
              } : undefined}
            />
          )}
          {call.kanban_stage === "call_topics" && (
            <CallTopicsStage
              call={call}
              onAggregateComplete={() => loadCall()}
              onAutoAdvanced={() => loadCall()}
              onPollCall={loadCall}
            />
          )}
          {call.kanban_stage === "artifacts" && (
            <>
              <ArtifactsStage call={call} onAdvance={loadCall} />
              {call.transcript && (
                <TranscriptPanel
                  call={call}
                  onSaved={(updated) => setCall(updated)}
                />
              )}
              <ContextFiles call={call} readonly />
              <div className="mt-4 text-right">
                <button
                  onClick={() => setShowResetModal(true)}
                  className="text-[11px] text-[#97a0af] hover:text-red-500 hover:underline"
                >
                  ↩ Reset transcript
                </button>
              </div>
            </>
          )}
          {call.kanban_stage === "done" && (
            <>
              <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8,
                padding: "12px 16px", marginBottom: 16, fontSize: 13, color: "#15803d",
                display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontWeight: 600 }}>✓ Call complete — all topics validated and artifacts saved.</span>
                {call.is_locked ? (
                  <button
                    onClick={handleUnlock}
                    disabled={isLocking}
                    style={{ fontSize: 12, fontWeight: 600, background: "white", color: "#5e6c84",
                      border: "1px solid #dfe1e6", borderRadius: 6, padding: "5px 14px",
                      cursor: isLocking ? "not-allowed" : "pointer", opacity: isLocking ? 0.6 : 1 }}
                  >
                    {isLocking ? "…" : "🔓 Unlock"}
                  </button>
                ) : (
                  <button
                    onClick={handleLock}
                    disabled={isLocking}
                    style={{ fontSize: 12, fontWeight: 600, background: "#172b4d", color: "white",
                      border: "none", borderRadius: 6, padding: "5px 14px",
                      cursor: isLocking ? "not-allowed" : "pointer", opacity: isLocking ? 0.6 : 1 }}
                  >
                    {isLocking ? "…" : "🔒 Lock Call"}
                  </button>
                )}
              </div>
              {call.is_locked && (
                <div style={{ fontSize: 11, color: "#97a0af", background: "#f4f5f7",
                  borderRadius: 6, padding: "6px 12px", marginBottom: 12 }}>
                  🔒 This call is locked. Unlock to edit transcript, topics, or regenerate artifacts.
                </div>
              )}
              {lockError && (
                <div style={{ fontSize: 11, color: "#ae2a19", background: "#fff1f0",
                  border: "1px solid #ffc2c2", borderRadius: 4, padding: "5px 10px", marginBottom: 8 }}>
                  {lockError}
                </div>
              )}
              <TopicsPanel callId={callId} projectId={projectId} defaultOpen call={call} />
              <ArtifactsPanel callId={callId} projectId={projectId} call={call} />
              {call.transcript && (
                <TranscriptPanel call={call} onSaved={(updated) => setCall(updated)} />
              )}
              <ContextFiles call={call} readonly />
            </>
          )}
        </div>
      )}

      {/* Rollback confirmation modal */}
      {renderRollbackModal()}

      {/* Reset transcript modal */}
      {showResetModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-lg w-full max-w-sm p-6">
            <h2 className="text-[16px] font-semibold text-[#172b4d] mb-2">Reset transcript</h2>
            <p className="text-[13px] text-[#5e6c84] mb-4">
              This will delete the transcript and roll back to the Get Transcript stage.
            </p>
            <label className="flex items-center gap-3 mb-5 cursor-pointer">
              <input
                type="checkbox"
                checked={resetDeleteArtifacts}
                onChange={(e) => setResetDeleteArtifacts(e.target.checked)}
                className="accent-[#0052cc] w-4 h-4"
              />
              <span className="text-[13px] text-[#172b4d]">Also delete generated artifacts</span>
            </label>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => { setShowResetModal(false); setResetDeleteArtifacts(false); }}
                disabled={resetting}
                className="text-[13px] text-[#5e6c84] hover:text-[#172b4d] disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmReset}
                disabled={resetting}
                className="px-4 py-2 bg-red-600 text-white text-[13px] font-medium rounded hover:bg-red-700 disabled:opacity-50"
              >
                {resetting ? "Resetting…" : "Reset"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
