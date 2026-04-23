"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { artifactTypesAPI, projectsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { ArtifactType, LLMProvider, Project } from "@/types";
import ArtifactTypeCard from "@/components/ArtifactTypeCard";
import AddArtifactTypeModal from "@/components/AddArtifactTypeModal";

const LLM_OPTIONS: { value: LLMProvider; label: string }[] = [
  { value: "groq",       label: "Groq – Llama 3.3 (free)" },
  { value: "deepseek",   label: "DeepSeek Chat (~free)" },
  { value: "claude",     label: "Claude Haiku" },
  { value: "openai",     label: "GPT-4o mini" },
  { value: "openrouter", label: "OpenRouter ⭐" },
];

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
  const [defaultModel, setDefaultModel] = useState<string>("");
  const [projectContext, setProjectContext] = useState<string>("");
  const [contextSaving, setContextSaving] = useState(false);

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
      setProjectContext(proj.context ?? "");
      setDefaultModel(proj.default_model ?? "");
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

  async function handleUpdateDefaultLlm(llm: LLMProvider, model: string | null = null) {
    if (!project) return;
    setSavingLlm(true);
    setLlmSaveError(null);
    try {
      const updated = await projectsAPI.updateDefaultLlm(projectId, llm, model);
      setProject(updated);
      setDefaultModel(updated.default_model ?? "");
      logger.info("Updated project default LLM", { component: "ArtifactsPage", data: { llm, model } });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to save";
      setLlmSaveError(msg);
      logger.error("Failed to update default LLM", { component: "ArtifactsPage", data: err });
    } finally {
      setSavingLlm(false);
    }
  }

  async function handleContextBlur() {
    setContextSaving(true);
    try {
      const updated = await projectsAPI.update(projectId, { context: projectContext });
      setProject(updated);
    } catch (err) {
      logger.error("Failed to save project context", { component: "ArtifactsPage", data: err });
    } finally {
      setContextSaving(false);
    }
  }

  async function handleUpdate(typeId: string, data: { name?: string; prompt?: string; llm?: LLMProvider | null; is_default?: boolean }) {
    const updated = await artifactTypesAPI.update(projectId, typeId, data);
    setTypes((prev) => prev.map((t) => (t.id === typeId ? updated : t)));
  }

  const artifactTypes = types.filter((t) => t.category === "artifacts" || !t.category);
  const workflowPrompts = types.filter((t) =>
    ["call_topics", "project_topics", "merge_verification", "not_discussed_check", "topics"].includes(t.category)
  );

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-5 pt-4 pb-3 bg-white border-b border-[#dfe1e6] flex-shrink-0">
        <h1 className="text-[18px] font-bold text-[#172b4d]">Artifact Types</h1>
        <div className="flex items-center gap-3">
          {project && (
            <div className="flex flex-col items-end gap-1">
              <div className="flex items-end gap-2">
                <div className="flex flex-col gap-0.5">
                  <span className="text-[11px] text-[#5e6c84]">Project default provider</span>
                  <select
                    value={project.default_llm}
                    onChange={(e) => {
                      const v = e.target.value as LLMProvider;
                      handleUpdateDefaultLlm(v, v === "openrouter" ? (project.default_model ?? defaultModel) : null);
                    }}
                    disabled={savingLlm}
                    className="text-[12px] border border-[#dfe1e6] rounded px-2 py-1 bg-white text-[#172b4d] focus:outline-none focus:border-[#0052cc] disabled:opacity-50"
                  >
                    {LLM_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
                {project.default_llm === "openrouter" && (
                  <div className="flex flex-col gap-0.5">
                    <span className="text-[11px] text-[#5e6c84]">Default model</span>
                    <input
                      type="text"
                      value={defaultModel}
                      onChange={(e) => setDefaultModel(e.target.value)}
                      onBlur={() => handleUpdateDefaultLlm("openrouter", defaultModel || null)}
                      placeholder="anthropic/claude-sonnet-4.6"
                      disabled={savingLlm}
                      className="text-[12px] border border-[#dfe1e6] rounded px-2 py-1 bg-white text-[#172b4d] focus:outline-none focus:border-[#0052cc] disabled:opacity-50 font-mono w-52"
                    />
                  </div>
                )}
                {savingLlm && <span className="text-[11px] text-[#5e6c84] pb-1.5">Saving…</span>}
              </div>
              {llmSaveError && (
                <span className="text-[11px] text-red-600">{llmSaveError}</span>
              )}
            </div>
          )}
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
        ) : (
          <>
            {/* ── Project context ── */}
            <div className="border border-[#dfe1e6] rounded-lg p-4 bg-white mb-6">
              <div className="flex items-center justify-between mb-1">
                <h2 className="text-[13px] font-bold text-[#172b4d]">Project context</h2>
                {contextSaving && <span className="text-[10px] text-[#5e6c84]">Saving…</span>}
              </div>
              <p className="text-[11px] text-[#5e6c84] mb-2">
                Prepended to every prompt for this project — artifact generation, topic extraction, and topic merge.
              </p>
              <textarea
                value={projectContext}
                onChange={(e) => setProjectContext(e.target.value)}
                onBlur={handleContextBlur}
                rows={4}
                placeholder="e.g. This is a software project with ACME Corp. The client is a mid-size e-commerce company focused on improving their checkout flow. Always use formal language."
                className="w-full text-[12px] text-[#172b4d] border border-[#dfe1e6] rounded px-3 py-2 resize-y focus:outline-none focus:border-[#0052cc] placeholder-[#97a0af]"
              />
            </div>

            {/* ── Tier 1 — Workflow Prompts ── */}
            <div style={{ margin: "24px 0 8px" }}>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#5e6c84", letterSpacing: ".05em", marginBottom: 4 }}>
                ⚙️ Tier 1 — Workflow Prompts
              </div>
              <div style={{ fontSize: 11, color: "#97a0af", marginBottom: 10 }}>
                System-essential prompts the extraction / merge / verification pipeline uses. 4 per project. Edit to customize, Reset to restore canonical.
              </div>
            </div>
            <div className="flex flex-col gap-3">
              {workflowPrompts.map((t) => (
                <ArtifactTypeCard
                  key={t.id}
                  type={t}
                  projectDefaultLlm={project?.default_llm ?? "groq"}
                  onDelete={() => {}}
                  onUpdate={handleUpdate}
                  hideDelete
                  hideDefaultToggle
                />
              ))}
              {workflowPrompts.length === 0 && (
                <div style={{ padding: "16px 0", fontSize: 12, color: "#97a0af", textAlign: "center" }}>
                  No workflow prompts found for this project. Run migration 021 + backend startup to seed them.
                </div>
              )}
            </div>

            {/* ── Tier 2 — Artifact Prompts ── */}
            <div style={{ margin: "24px 0 8px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#5e6c84", letterSpacing: ".05em", marginBottom: 4 }}>
                  📝 Tier 2 — Artifact Prompts
                </div>
                <div style={{ fontSize: 11, color: "#97a0af" }}>
                  Library-backed or custom artifacts this project generates. Add from library, publish yours to the library, or create custom.
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowModal(true)}
                style={{ fontSize: 13, fontWeight: 600, color: "white", background: "#0052cc", border: "none", borderRadius: 6, padding: "8px 14px", cursor: "pointer" }}
              >
                + Add artifact type
              </button>
            </div>
            <div className="flex flex-col gap-3 pb-6">
              {artifactTypes.map((t) => (
                <ArtifactTypeCard
                  key={t.id}
                  type={t}
                  projectDefaultLlm={project?.default_llm ?? "groq"}
                  onDelete={handleDelete}
                  onUpdate={handleUpdate}
                />
              ))}
              {artifactTypes.length === 0 && (
                <div style={{ padding: "16px 0", fontSize: 12, color: "#97a0af", textAlign: "center" }}>
                  No artifact types. Click &quot;+ Add artifact type&quot; to browse the library.
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {showModal && (
        <AddArtifactTypeModal
          projectId={projectId}
          existingTypes={types}
          onClose={() => setShowModal(false)}
          onCreated={(t) => setTypes((prev) => [...prev, t])}
          onImported={(ts) => setTypes((prev) => [...prev, ...ts])}
          onAdded={() => load()}
        />
      )}
    </div>
  );
}
