"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { artifactTypesAPI, projectsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { ArtifactType, LLMProvider, Project } from "@/types";
import ArtifactTypeCard from "@/components/ArtifactTypeCard";
import AddArtifactTypeModal from "@/components/AddArtifactTypeModal";

export default function ArtifactsPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;

  const [types, setTypes] = useState<ArtifactType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [project, setProject] = useState<Project | null>(null);
  const [savingLlm, setSavingLlm] = useState(false);
  const [llmSaveError, setLlmSaveError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      logger.info("Fetching artifact types", { component: "ArtifactsPage", data: { projectId } });
      const [data, proj] = await Promise.all([
        artifactTypesAPI.list(projectId),
        projectsAPI.get(projectId),
      ]);
      setTypes(data);
      setProject(proj);
    } catch (err) {
      logger.error("Failed to load", { component: "ArtifactsPage", data: err });
      setError("Failed to load artifact types.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load]);

  async function handleDelete(typeId: string) {
    try {
      await artifactTypesAPI.delete(projectId, typeId);
      setTypes((prev) => prev.filter((t) => t.id !== typeId));
      logger.info("Deleted artifact type", { component: "ArtifactsPage", data: { typeId } });
    } catch (err) {
      logger.error("Failed to delete artifact type", { component: "ArtifactsPage", data: err });
    }
  }

  async function handleUpdateDefaultLlm(llm: LLMProvider) {
    if (!project) return;
    setSavingLlm(true);
    setLlmSaveError(null);
    try {
      const updated = await projectsAPI.update(projectId, { default_llm: llm });
      setProject(updated);
      logger.info("Updated project default LLM", { component: "ArtifactsPage", data: { llm } });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to save";
      setLlmSaveError(msg);
      logger.error("Failed to update default LLM", { component: "ArtifactsPage", data: err });
    } finally {
      setSavingLlm(false);
    }
  }

  async function handleUpdate(typeId: string, data: { name?: string; prompt?: string; llm?: LLMProvider | null }) {
    const updated = await artifactTypesAPI.update(projectId, typeId, data);
    setTypes((prev) => prev.map((t) => (t.id === typeId ? updated : t)));
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-5 pt-4 pb-3 bg-white border-b border-[#dfe1e6] flex-shrink-0">
        <h1 className="text-[18px] font-bold text-[#172b4d]">Artifact Types</h1>
        <div className="flex items-center gap-3">
          {project && (
            <div className="flex flex-col items-end gap-1">
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-[#5e6c84]">Project default:</span>
                <select
                  value={project.default_llm}
                  onChange={(e) => handleUpdateDefaultLlm(e.target.value as LLMProvider)}
                  disabled={savingLlm}
                  className="text-[12px] border border-[#dfe1e6] rounded px-2 py-1 bg-white text-[#172b4d] focus:outline-none focus:border-[#0052cc] disabled:opacity-50"
                >
                  <option value="groq">Groq (free)</option>
                  <option value="claude">Claude</option>
                  <option value="openai">ChatGPT (OpenAI)</option>
                </select>
                {savingLlm && <span className="text-[11px] text-[#5e6c84]">Saving…</span>}
              </div>
              {llmSaveError && (
                <span className="text-[11px] text-red-600">{llmSaveError}</span>
              )}
            </div>
          )}
          <button
            onClick={() => setShowModal(true)}
            className="bg-[#0052cc] text-white px-4 py-[6px] rounded text-[13px] font-medium hover:bg-[#0065ff]"
          >
            + Add artifact type
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        {loading ? (
          <p className="text-[13px] text-[#5e6c84]">Loading…</p>
        ) : error ? (
          <div className="flex flex-col items-center gap-3 py-12">
            <p className="text-[13px] text-red-600">{error}</p>
            <button onClick={load} className="text-[13px] text-[#0052cc] underline">Retry</button>
          </div>
        ) : types.length === 0 ? (
          <p className="text-[13px] text-[#5e6c84]">No artifact types yet.</p>
        ) : (
          <div className="flex flex-col gap-3">
            {types.map((t) => (
              <ArtifactTypeCard
                key={t.id}
                type={t}
                projectDefaultLlm={project?.default_llm ?? "groq"}
                onDelete={handleDelete}
                onUpdate={handleUpdate}
              />
            ))}
          </div>
        )}
      </div>

      {showModal && (
        <AddArtifactTypeModal
          projectId={projectId}
          onClose={() => setShowModal(false)}
          onCreated={(t) => setTypes((prev) => [...prev, t])}
          onImported={(ts) => setTypes((prev) => [...prev, ...ts])}
        />
      )}
    </div>
  );
}
