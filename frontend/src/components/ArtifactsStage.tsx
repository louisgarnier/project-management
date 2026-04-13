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
  const [projectDefaultLlm, setProjectDefaultLlm] = useState<LLMProvider>("groq");
  const [applyLlm, setApplyLlm] = useState<LLMProvider>("groq");
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
      setArtifactTypes(types);
      setProjectDefaultLlm(project.default_llm);
      setApplyLlm(project.default_llm);

      // Default each type to its stored llm, or the project default
      const defaultSels: Record<string, SelectionMode> = {};
      types.forEach((t) => {
        defaultSels[t.id] = t.llm ?? project.default_llm;
      });
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

  function handleSelectionChange(typeId: string, mode: SelectionMode) {
    setSelections((prev) => ({ ...prev, [typeId]: mode }));
  }

  function handleApplyToAll() {
    setSelections((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((id) => {
        if (next[id] !== "manual" && next[id] !== "skip") {
          next[id] = applyLlm;
        }
      });
      return next;
    });
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
        mode: mode as ArtifactMode,  // "groq" | "claude" | "openai" | "manual"
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

  async function handleRetry(artifactId: string) {
    // Reset this artifact to pending with the current project default LLM, then re-stream
    try {
      const updated = await artifactsAPI.update(artifactId, {
        status: "pending",
        mode: projectDefaultLlm,
      });
      setArtifacts((prev) => prev.map((a) => (a.id === artifactId ? updated : a)));
      logger.info("Artifact reset for retry", { component: "ArtifactsStage", data: { artifactId, llm: projectDefaultLlm } });
      setPhase("generating");
      await streamArtifacts();
    } catch (err) {
      logger.error("Retry failed", { component: "ArtifactsStage", data: err });
    }
  }

  async function handleRegenerateAll() {
    // Reset all non-done, non-manual artifacts to pending with project default LLM, then re-stream
    try {
      const toReset = artifacts.filter((a) => a.status !== "done" && a.status !== "generating");
      await Promise.all(
        toReset.map((a) =>
          artifactsAPI.update(a.id, { status: "pending", mode: projectDefaultLlm })
        )
      );
      setArtifacts((prev) =>
        prev.map((a) =>
          toReset.some((r) => r.id === a.id)
            ? { ...a, status: "pending", mode: projectDefaultLlm }
            : a
        )
      );
      logger.info("All artifacts reset for regeneration", { component: "ArtifactsStage", data: { llm: projectDefaultLlm } });
      setPhase("generating");
      await streamArtifacts();
    } catch (err) {
      logger.error("Regenerate all failed", { component: "ArtifactsStage", data: err });
    }
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
          <>
            {artifactTypes.length > 0 && (
              <div className="flex items-center gap-2 px-4 py-2 bg-[#f4f5f7] rounded-lg border border-[#dfe1e6]">
                <span className="text-[11px] text-[#5e6c84]">Apply to all generate:</span>
                <select
                  value={applyLlm}
                  onChange={(e) => setApplyLlm(e.target.value as LLMProvider)}
                  className="text-[11px] border border-[#dfe1e6] rounded px-2 py-1 bg-white text-[#172b4d] focus:outline-none focus:border-[#0052cc]"
                >
                  <option value="groq">Groq (free)</option>
                  <option value="claude">Claude</option>
                  <option value="openai">ChatGPT (OpenAI)</option>
                </select>
                <button
                  onClick={handleApplyToAll}
                  className="px-3 py-1 text-[11px] font-medium text-[#0052cc] border border-[#0052cc] rounded hover:bg-[#e9f0ff] transition-colors"
                >
                  Apply to all
                </button>
              </div>
            )}
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
              Regenerate all with {projectDefaultLlm === "groq" ? "Groq" : projectDefaultLlm === "openai" ? "ChatGPT" : "Claude"}
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
