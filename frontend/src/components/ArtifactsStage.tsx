"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { artifactTypesAPI, artifactsAPI, callsAPI, projectsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Artifact, ArtifactMode, ArtifactType, Call, LLMProvider } from "@/types";
import ArtifactSelector, { type SelectionMode } from "@/components/ArtifactSelector";
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
  const [selections, setSelections] = useState<Record<string, SelectionMode>>({});
  const [newTypeSelections, setNewTypeSelections] = useState<Record<string, SelectionMode>>({});
  const [projectDefaultLlm, setProjectDefaultLlm] = useState<LLMProvider>("groq");
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [phase, setPhase] = useState<Phase>("select");
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [advancing, setAdvancing] = useState(false);
  const streamAbortRef = useRef<AbortController | null>(null);

  // Load artifact types and check for existing artifacts
  const init = useCallback(async () => {
    try {
      const [types, existing, project] = await Promise.all([
        artifactTypesAPI.list(projectId),
        artifactsAPI.list(callId),
        projectsAPI.get(projectId),
      ]);
      const artifactTypes = types.filter((t) => t.category !== "topics");
      setArtifactTypes(artifactTypes);
      setProjectDefaultLlm(project.default_llm);

      // Default all types to "generate"
      const defaultSels: Record<string, SelectionMode> = {};
      artifactTypes.forEach((t) => { defaultSels[t.id] = "generate"; });
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

  // Re-fetch project default whenever reviewing phase is shown — keeps fallback LLM in sync
  useEffect(() => {
    if (phase === "reviewing") {
      projectsAPI.get(projectId).then((p) => {
        setProjectDefaultLlm(p.default_llm);
      }).catch(() => {});
    }
  }, [phase, projectId]);

  function handleSelectionChange(typeId: string, mode: SelectionMode) {
    setSelections((prev) => ({ ...prev, [typeId]: mode }));
  }

  const nonSkipped = Object.entries(selections).filter(([, m]) => m !== "skip");
  const canGenerate = nonSkipped.length > 0;

  async function handleGenerate() {
    setGenerating(true);
    setGenerateError(null);
    try {
      // POST selections (exclude skipped) — resolve LLM from artifact type settings
      const payload = nonSkipped.map(([typeId, sel]) => {
        const type = artifactTypes.find((t) => t.id === typeId);
        const mode: ArtifactMode = sel === "manual" ? "manual" : (type?.llm ?? projectDefaultLlm);
        return { artifact_type_id: typeId, mode };
      });
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

  async function handleDeleteArtifact(artifactId: string) {
    await artifactsAPI.delete(artifactId);
    setArtifacts((prev) => prev.filter((a) => a.id !== artifactId));
    logger.info("Deleted artifact", { component: "ArtifactsStage", data: { artifactId } });
  }

  async function handleRetry(artifactId: string) {
    // Use the LLM from the artifact type's settings (falls back to project default)
    try {
      const artifact = artifacts.find((a) => a.id === artifactId);
      const llm = (artifact ? (typeMap[artifact.artifact_type_id]?.llm ?? projectDefaultLlm) : projectDefaultLlm) as ArtifactMode;
      const updated = await artifactsAPI.update(artifactId, { status: "pending", mode: llm });
      setArtifacts((prev) => prev.map((a) => (a.id === artifactId ? updated : a)));
      logger.info("Artifact reset for retry", { component: "ArtifactsStage", data: { artifactId, llm } });
      setPhase("generating");
      await streamArtifacts();
    } catch (err) {
      logger.error("Retry failed", { component: "ArtifactsStage", data: err });
    }
  }

  async function handleRegenerateAll() {
    // Use each artifact type's configured LLM (falls back to project default)
    try {
      const toReset = artifacts.filter((a) => a.status !== "done" && a.status !== "generating");
      const resetWithLlm = toReset.map((a) => ({
        artifact: a,
        llm: (typeMap[a.artifact_type_id]?.llm ?? projectDefaultLlm) as ArtifactMode,
      }));
      await Promise.all(
        resetWithLlm.map(({ artifact, llm }) =>
          artifactsAPI.update(artifact.id, { status: "pending", mode: llm })
        )
      );
      setArtifacts((prev) =>
        prev.map((a) => {
          const entry = resetWithLlm.find((r) => r.artifact.id === a.id);
          return entry ? { ...a, status: "pending", mode: entry.llm } : a;
        })
      );
      logger.info("Regenerate all", { component: "ArtifactsStage", data: { count: toReset.length } });
      setPhase("generating");
      await streamArtifacts();
    } catch (err) {
      logger.error("Regenerate all failed", { component: "ArtifactsStage", data: err });
    }
  }

  const typeMap = Object.fromEntries(artifactTypes.map((t) => [t.id, t]));

  // Artifact types that have no artifact row yet for this call
  const coveredTypeIds = new Set(artifacts.map((a) => a.artifact_type_id));
  const newTypes = artifactTypes.filter((t) => !coveredTypeIds.has(t.id));

  async function handleGenerateNew() {
    const toProcess = newTypes.filter((t) => (newTypeSelections[t.id] ?? "generate") !== "skip");
    if (toProcess.length === 0) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      const payload = toProcess.map((t) => {
        const sel = newTypeSelections[t.id] ?? "generate";
        const mode: ArtifactMode = sel === "manual" ? "manual" : (t.llm ?? projectDefaultLlm);
        return { artifact_type_id: t.id, mode };
      });
      const created = await artifactsAPI.createSelections(callId, payload);
      setArtifacts((prev) => [...prev, ...created]);
      // Clear processed types from newTypeSelections
      setNewTypeSelections((prev) => {
        const updated = { ...prev };
        toProcess.forEach((t) => delete updated[t.id]);
        return updated;
      });
      setPhase("generating");
      logger.info("Generated new artifact types", { component: "ArtifactsStage", data: { count: created.length } });
      await streamArtifacts();
    } catch (err) {
      logger.error("Generate new failed", { component: "ArtifactsStage", data: err });
      setGenerateError(err instanceof Error ? err.message : "Failed to generate");
      setGenerating(false);
    }
  }

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
          <>
            <ArtifactSelector
              artifactTypes={artifactTypes}
              selections={selections}
              projectDefaultLlm={projectDefaultLlm}
              onChange={handleSelectionChange}
            />
          </>
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
        <div className="flex items-center gap-3">
          {phase === "generating" && (
            <span className="text-[12px] text-[#5e6c84]">
              {artifacts.filter((a) => a.status === "done").length} / {artifacts.length} done
            </span>
          )}
          {phase === "reviewing" && artifacts.some((a) => a.status === "error" || a.status === "pending") && (
            <button
              onClick={handleRegenerateAll}
              className="text-[11px] text-[#0052cc] border border-[#0052cc] px-3 py-1 rounded hover:bg-[#e9f0ff] transition-colors"
            >
              Regenerate failed
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-3">
        {artifacts.map((a) => (
          <ArtifactCard
            key={a.id}
            artifact={a}
            artifactType={typeMap[a.artifact_type_id]}
            onMarkDone={handleMarkDone}
            onRetry={handleRetry}
            onDelete={handleDeleteArtifact}
          />
        ))}
      </div>

      {phase === "reviewing" && newTypes.length > 0 && (
        <div className="border border-dashed border-[#b3c6e8] rounded-lg p-4 bg-[#f4f5f7]">
          <p className="text-[12px] font-semibold text-[#172b4d] mb-3">
            {newTypes.length} new artifact type{newTypes.length > 1 ? "s" : ""} available
          </p>
          <ArtifactSelector
            artifactTypes={newTypes}
            selections={newTypeSelections}
            projectDefaultLlm={projectDefaultLlm}
            onChange={(typeId, mode) =>
              setNewTypeSelections((prev) => ({ ...prev, [typeId]: mode }))
            }
          />
          {generateError && <p className="text-[11px] text-red-600 mt-2">{generateError}</p>}
          <div className="flex justify-end mt-3">
            <button
              onClick={handleGenerateNew}
              disabled={generating || newTypes.every((t) => (newTypeSelections[t.id] ?? "generate") === "skip")}
              className="px-4 py-2 bg-[#0052cc] text-white text-[13px] font-medium rounded hover:bg-[#0747a6] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {generating ? "Generating…" : "Generate selected →"}
            </button>
          </div>
        </div>
      )}

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
