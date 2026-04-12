"use client";

import { useState } from "react";
import { projectsAPI, artifactTypesAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Project, ArtifactType } from "@/types";

type Mode = "create" | "import";

type Props = {
  projectId: string;
  onClose: () => void;
  onCreated: (type: ArtifactType) => void;
  onImported: (types: ArtifactType[]) => void;
};

export default function AddArtifactTypeModal({ projectId, onClose, onCreated, onImported }: Props) {
  const [mode, setMode] = useState<Mode>("create");

  // Create state
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [saving, setSaving] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Import state
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [sourceTypes, setSourceTypes] = useState<ArtifactType[]>([]);
  const [loadingTypes, setLoadingTypes] = useState(false);
  const [selectedTypeIds, setSelectedTypeIds] = useState<Set<string>>(new Set());
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [projectsLoadError, setProjectsLoadError] = useState(false);
  const [typesLoadError, setTypesLoadError] = useState(false);

  async function handleSwitchToImport() {
    setMode("import");
    if (projects !== null) return;
    setLoadingProjects(true);
    try {
      const all = await projectsAPI.list();
      setProjects(all.filter((p) => p.id !== projectId));
    } catch (err) {
      logger.error("Failed to load projects for import", { component: "AddArtifactTypeModal", data: err });
      setProjectsLoadError(true);
      setProjects([]);
    } finally {
      setLoadingProjects(false);
    }
  }

  async function handleSelectProject(pid: string) {
    setSelectedProjectId(pid);
    setSourceTypes([]);
    setSelectedTypeIds(new Set());
    setTypesLoadError(false);
    if (!pid) return;
    setLoadingTypes(true);
    try {
      const types = await artifactTypesAPI.list(pid);
      setSourceTypes(types);
    } catch (err) {
      logger.error("Failed to load source artifact types", { component: "AddArtifactTypeModal", data: err });
      setTypesLoadError(true);
    } finally {
      setLoadingTypes(false);
    }
  }

  function toggleTypeId(id: string) {
    setSelectedTypeIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !prompt.trim()) return;
    setSaving(true);
    setCreateError(null);
    try {
      const created = await artifactTypesAPI.create(projectId, { name: name.trim(), prompt: prompt.trim() });
      logger.info("Created artifact type", { component: "AddArtifactTypeModal", data: { id: created.id } });
      onCreated(created);
      onClose();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create");
    } finally {
      setSaving(false);
    }
  }

  async function handleImport() {
    if (selectedTypeIds.size === 0) return;
    setImporting(true);
    setImportError(null);
    try {
      const imported = await artifactTypesAPI.import(projectId, [...selectedTypeIds]);
      logger.info("Imported artifact types", { component: "AddArtifactTypeModal", data: { count: imported.length } });
      onImported(imported);
      onClose();
    } catch (err) {
      setImportError(err instanceof Error ? err.message : "Failed to import");
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-lg w-full max-w-lg">
        {/* Header */}
        <div className="px-6 pt-5 pb-4 border-b border-[#dfe1e6]">
          <h2 className="text-[16px] font-semibold text-[#172b4d]">Add artifact type</h2>
        </div>

        {/* Mode tabs */}
        <div className="flex gap-1 px-6 pt-4">
          <button
            onClick={() => setMode("create")}
            className={`px-3 py-1.5 text-[12px] font-medium rounded transition-colors ${
              mode === "create"
                ? "bg-[#e9f0ff] text-[#0052cc]"
                : "text-[#5e6c84] hover:bg-[#f4f5f7]"
            }`}
          >
            Create new
          </button>
          <button
            onClick={handleSwitchToImport}
            className={`px-3 py-1.5 text-[12px] font-medium rounded transition-colors ${
              mode === "import"
                ? "bg-[#e9f0ff] text-[#0052cc]"
                : "text-[#5e6c84] hover:bg-[#f4f5f7]"
            }`}
          >
            Import from another project
          </button>
        </div>

        <div className="px-6 py-4">
          {/* Create new */}
          {mode === "create" && (
            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label className="block text-[12px] font-medium text-[#172b4d] mb-1">Name</label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full border border-[#dfe1e6] rounded px-3 py-2 text-[13px] focus:outline-none focus:border-[#0052cc]"
                  placeholder="e.g. Risk Register"
                  required
                />
              </div>
              <div>
                <label className="block text-[12px] font-medium text-[#172b4d] mb-1">Prompt</label>
                <textarea
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  className="w-full border border-[#dfe1e6] rounded px-3 py-2 text-[13px] focus:outline-none focus:border-[#0052cc] resize-none h-28"
                  placeholder="Instructions for Claude when generating this artifact…"
                  required
                />
              </div>
              {createError && <p className="text-[12px] text-red-600">{createError}</p>}
              <div className="flex justify-end gap-3 pt-1">
                <button
                  type="button"
                  onClick={onClose}
                  className="text-[13px] text-[#5e6c84] hover:text-[#172b4d]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving || !name.trim() || !prompt.trim()}
                  className="px-4 py-2 bg-[#0052cc] text-white text-[13px] font-medium rounded hover:bg-[#0747a6] disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {saving ? "Creating…" : "Create"}
                </button>
              </div>
            </form>
          )}

          {/* Import */}
          {mode === "import" && (
            <div className="space-y-3">
              {loadingProjects ? (
                <p className="text-[13px] text-[#5e6c84]">Loading projects…</p>
              ) : !projects || projects.length === 0 ? (
                projectsLoadError ? (
                  <div className="flex flex-col gap-2">
                    <p className="text-[13px] text-red-600">Failed to load projects.</p>
                    <button
                      onClick={() => { setProjectsLoadError(false); setProjects(null); handleSwitchToImport(); }}
                      className="text-[13px] text-[#0052cc] underline self-start"
                    >
                      Retry
                    </button>
                  </div>
                ) : (
                  <p className="text-[13px] text-[#5e6c84]">No other projects found.</p>
                )
              ) : (
                <>
                  <div>
                    <label className="block text-[12px] font-medium text-[#172b4d] mb-1">Project</label>
                    <select
                      value={selectedProjectId}
                      onChange={(e) => handleSelectProject(e.target.value)}
                      className="w-full border border-[#dfe1e6] rounded px-3 py-2 text-[13px] focus:outline-none focus:border-[#0052cc] bg-white"
                    >
                      <option value="">Select a project…</option>
                      {projects.map((p) => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                    </select>
                  </div>

                  {typesLoadError && (
                    <p className="text-[13px] text-red-600">Failed to load artifact types. Try selecting the project again.</p>
                  )}

                  {loadingTypes && (
                    <p className="text-[13px] text-[#5e6c84]">Loading types…</p>
                  )}

                  {!loadingTypes && selectedProjectId && sourceTypes.length === 0 && (
                    <p className="text-[13px] text-[#5e6c84]">No artifact types in this project.</p>
                  )}

                  {!loadingTypes && sourceTypes.length > 0 && (
                    <div className="border border-[#dfe1e6] rounded divide-y divide-[#dfe1e6] max-h-52 overflow-y-auto">
                      {sourceTypes.map((t) => (
                        <label
                          key={t.id}
                          className="flex items-center gap-3 px-3 py-2.5 cursor-pointer hover:bg-[#f4f5f7]"
                        >
                          <input
                            type="checkbox"
                            checked={selectedTypeIds.has(t.id)}
                            onChange={() => toggleTypeId(t.id)}
                            className="accent-[#0052cc]"
                          />
                          <span className="text-[13px] text-[#172b4d] flex-1">{t.name}</span>
                          <span
                            className="text-[9px] font-bold px-[5px] py-[1px] rounded uppercase tracking-[.04em]"
                            style={
                              t.is_default
                                ? { background: "#e9f0ff", color: "#0052cc" }
                                : { background: "#f3f0ff", color: "#5243aa" }
                            }
                          >
                            {t.is_default ? "Default" : "Custom"}
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                </>
              )}

              {importError && <p className="text-[12px] text-red-600">{importError}</p>}

              <div className="flex justify-end gap-3 pt-1">
                <button
                  type="button"
                  onClick={onClose}
                  className="text-[13px] text-[#5e6c84] hover:text-[#172b4d]"
                >
                  Cancel
                </button>
                <button
                  onClick={handleImport}
                  disabled={importing || selectedTypeIds.size === 0}
                  className="px-4 py-2 bg-[#0052cc] text-white text-[13px] font-medium rounded hover:bg-[#0747a6] disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {importing
                    ? "Importing…"
                    : selectedTypeIds.size > 0
                    ? `Import (${selectedTypeIds.size})`
                    : "Import"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
