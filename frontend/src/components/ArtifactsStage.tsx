"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { artifactTypesAPI, artifactsAPI, callsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Artifact, ArtifactType, Call } from "@/types";
import ArtifactSelector, { type ArtifactMode } from "@/components/ArtifactSelector";
import ArtifactCard from "@/components/ArtifactCard";

type Phase = "select" | "generating" | "reviewing";

type Props = {
  call: Call;
  onAdvance: () => void;
};

export default function ArtifactsStage({ call, onAdvance }: Props) {
  const projectId = call.project_id;
  const callId = call.id;

  const [artifactTypes, setArtifactTypes] = useState<ArtifactType[]>([]);
  const [selections, setSelections] = useState<Record<string, ArtifactMode>>({});
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [phase, setPhase] = useState<Phase>("select");
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [advancing, setAdvancing] = useState(false);
  const streamAbortRef = useRef<AbortController | null>(null);

  // Load artifact types and check for existing artifacts
  const init = useCallback(async () => {
    try {
      const [types, existing] = await Promise.all([
        artifactTypesAPI.list(projectId),
        artifactsAPI.list(callId),
      ]);
      setArtifactTypes(types);
      // Default all to "claude"
      const defaultSels: Record<string, ArtifactMode> = {};
      types.forEach((t) => { defaultSels[t.id] = "claude"; });
      setSelections(defaultSels);

      if (existing.length > 0) {
        setArtifacts(existing);
        setPhase("reviewing");
      }
    } catch (err) {
      logger.error("Failed to init ArtifactsStage", { component: "ArtifactsStage", data: err });
    }
  }, [projectId, callId]);

  useEffect(() => {
    init();
    return () => { streamAbortRef.current?.abort(); };
  }, [init]);

  function handleSelectionChange(typeId: string, mode: ArtifactMode) {
    setSelections((prev) => ({ ...prev, [typeId]: mode }));
  }

  const nonSkipped = Object.entries(selections).filter(([, m]) => m !== "skip");
  const canGenerate = nonSkipped.length > 0;

  async function handleGenerate() {
    setGenerating(true);
    setGenerateError(null);
    try {
      // POST selections (exclude skipped)
      const payload = nonSkipped.map(([typeId, mode]) => ({
        artifact_type_id: typeId,
        mode: mode as "claude" | "manual",
      }));
      const created = await artifactsAPI.createSelections(callId, payload);
      setArtifacts(created);
      setPhase("generating");
      logger.info("Artifact selections created", { component: "ArtifactsStage", data: { count: created.length } });

      // Open SSE stream
      await streamArtifacts();
    } catch (err) {
      logger.error("Generate failed", { component: "ArtifactsStage", data: err });
      setGenerateError(err instanceof Error ? err.message : "Failed to generate");
      setGenerating(false);
    }
  }

  async function streamArtifacts() {
    const controller = new AbortController();
    streamAbortRef.current = controller;

    try {
      const response = await fetch(`/api/sse/api/calls/${callId}/artifacts/stream`, {
        signal: controller.signal,
      });

      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            logger.info("SSE event", { component: "ArtifactsStage", data: event });
            handleSseEvent(event);
          } catch {
            // malformed line — skip
          }
        }
      }
    } catch (err: unknown) {
      if ((err as Error)?.name !== "AbortError") {
        logger.error("SSE stream error", { component: "ArtifactsStage", data: err });
      }
    } finally {
      setGenerating(false);
      setPhase("reviewing");
    }
  }

  function handleSseEvent(event: { type: string; artifact_id?: string; status?: string; content?: string; message?: string }) {
    if (event.type === "complete") return;

    setArtifacts((prev) =>
      prev.map((a) => {
        if (a.id !== event.artifact_id) return a;
        if (event.type === "status") return { ...a, status: event.status as Artifact["status"] };
        if (event.type === "done") return { ...a, status: "done", content: event.content ?? null };
        if (event.type === "error") return { ...a, status: "error", error_message: event.message ?? null };
        return a;
      })
    );
  }

  async function handleMarkDone(artifactId: string, content: string) {
    const updated = await artifactsAPI.update(artifactId, { content, status: "done" });
    setArtifacts((prev) => prev.map((a) => (a.id === artifactId ? updated : a)));
    logger.info("Artifact marked done", { component: "ArtifactsStage", data: { artifactId } });
  }

  function handleRetry(_artifactId: string) {
    // Re-opens SSE stream for any remaining pending/error artifacts
    void streamArtifacts();
  }

  const typeMap = Object.fromEntries(artifactTypes.map((t) => [t.id, t]));

  // "Proceed" enabled when every artifact is done
  const allDone = artifacts.length > 0 && artifacts.every((a) => a.status === "done");

  async function handleProceed() {
    setAdvancing(true);
    try {
      await callsAPI.advanceStage(callId);
      logger.info("Advanced to topics", { component: "ArtifactsStage", data: { callId } });
      onAdvance();
    } catch (err) {
      logger.error("Failed to advance stage", { component: "ArtifactsStage", data: err });
      setAdvancing(false);
    }
  }

  // ── Render ──

  if (phase === "select") {
    return (
      <div className="flex flex-col gap-4 max-w-3xl">
        <div>
          <h2 className="text-[15px] font-semibold text-[#172b4d] mb-1">Select artifacts to generate</h2>
          <p className="text-[12px] text-[#5e6c84]">
            Choose how each artifact type should be handled for this call.
          </p>
        </div>

        {artifactTypes.length === 0 ? (
          <p className="text-[13px] text-[#5e6c84]">No artifact types configured. Add some in the Artifacts tab.</p>
        ) : (
          <ArtifactSelector
            artifactTypes={artifactTypes}
            selections={selections}
            onChange={handleSelectionChange}
          />
        )}

        {generateError && <p className="text-[12px] text-red-600">{generateError}</p>}

        <div className="flex justify-end pt-2">
          <button
            onClick={handleGenerate}
            disabled={!canGenerate || generating}
            className="px-5 py-2 bg-[#0052cc] text-white text-[13px] font-medium rounded hover:bg-[#0747a6] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {generating ? "Starting…" : "Generate →"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 max-w-3xl">
      <div className="flex items-center justify-between">
        <h2 className="text-[15px] font-semibold text-[#172b4d]">
          {phase === "generating" ? "Generating artifacts…" : "Artifacts"}
        </h2>
        {phase === "generating" && (
          <span className="text-[12px] text-[#5e6c84]">
            {artifacts.filter((a) => a.status === "done").length} / {artifacts.length} done
          </span>
        )}
      </div>

      <div className="flex flex-col gap-3">
        {artifacts.map((a) => (
          <ArtifactCard
            key={a.id}
            artifact={a}
            artifactType={typeMap[a.artifact_type_id]}
            onMarkDone={handleMarkDone}
            onRetry={handleRetry}
          />
        ))}
      </div>

      {phase === "reviewing" && (
        <div className="flex justify-end pt-2">
          <button
            onClick={handleProceed}
            disabled={!allDone || advancing}
            className="px-5 py-2 bg-[#0052cc] text-white text-[13px] font-medium rounded hover:bg-[#0747a6] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {advancing ? "Advancing…" : "Proceed to Topics →"}
          </button>
        </div>
      )}
    </div>
  );
}
