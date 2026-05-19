"use client";

import { useState, useEffect } from "react";
import { projectsAPI, artifactTypesAPI, libraryAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Project, ArtifactType, LibraryEntry, ContextScope } from "@/types";

const CONTEXT_SCOPE_OPTIONS: { value: ContextScope; label: string }[] = [
  { value: "this_call_transcript",  label: "This call's transcript" },
  { value: "all_call_transcripts",  label: "All call transcripts (chronological)" },
  { value: "this_call_topics",      label: "This call's topics" },
  { value: "all_project_topics",    label: "All project topics (incl. previous calls)" },
];

type Tab = "library" | "create" | "import";

type Props = {
  projectId: string;
  existingTypes?: ArtifactType[];
  onClose: () => void;
  onCreated: (type: ArtifactType) => void;
  onImported: (types: ArtifactType[]) => void;
  onAdded?: () => void;
};

export default function AddArtifactTypeModal({
  projectId,
  existingTypes,
  onClose,
  onCreated,
  onImported,
  onAdded,
}: Props) {
  const [tab, setTab] = useState<Tab>("library");

  // Library state
  const [libraryEntries, setLibraryEntries] = useState<LibraryEntry[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [libraryError, setLibraryError] = useState<string | null>(null);

  // Create state
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [contextScope, setContextScope] = useState<ContextScope>("this_call_topics");
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

  useEffect(() => {
    if (tab !== "library") return;
    setLibraryLoading(true);
    setLibraryError(null);
    libraryAPI
      .list()
      .then((entries) => setLibraryEntries(entries))
      .catch((e) => setLibraryError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLibraryLoading(false));
  }, [tab]);

  async function handleSwitchToImport() {
    setTab("import");
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
      const created = await artifactTypesAPI.create(projectId, { name: name.trim(), prompt: prompt.trim(), context_scope: contextScope });
      logger.info("Created artifact type", { component: "AddArtifactTypeModal", data: { id: created.id } });
      onCreated(created);
      onAdded?.();
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
      onAdded?.();
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

        {/* Tab strip */}
        <div style={{ display: "flex", gap: 0, borderBottom: "1px solid #dfe1e6", marginBottom: 0 }}>
          {(["library", "create", "import"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => {
                if (t === "import") {
                  handleSwitchToImport();
                } else {
                  setTab(t);
                }
              }}
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: tab === t ? "#0052cc" : "#5e6c84",
                background: "none",
                border: "none",
                borderBottom: tab === t ? "2px solid #0052cc" : "2px solid transparent",
                padding: "8px 14px",
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              {t === "library"
                ? "Browse library"
                : t === "create"
                ? "Create new"
                : "Import from another project"}
            </button>
          ))}
        </div>

        <div className="px-6 py-4">
          {/* Library tab */}
          {tab === "library" && (
            <div>
              {libraryLoading && (
                <p style={{ fontSize: 12, color: "#5e6c84" }}>Loading library…</p>
              )}
              {libraryError && (
                <p style={{ fontSize: 12, color: "#ae2a19" }}>Error: {libraryError}</p>
              )}
              {!libraryLoading && !libraryError && libraryEntries.length === 0 && (
                <p style={{ fontSize: 12, color: "#5e6c84" }}>
                  Library is empty. System entries seed automatically on backend startup.
                </p>
              )}
              {libraryEntries
                .filter(
                  (lib) =>
                    !(existingTypes ?? []).some((t) => t.library_ref_id === lib.id)
                )
                .map((lib) => {
                  const kindLabel =
                    lib.kind === "template" ? "TEMPLATE" : lib.kind === "hybrid" ? "HYBRID" : "LLM";
                  const kindColor =
                    lib.kind === "template"
                      ? { bg: "#e3fcef", fg: "#006644" }
                      : lib.kind === "hybrid"
                      ? { bg: "#fff4e6", fg: "#974f0c" }
                      : { bg: "#e9f0ff", fg: "#0052cc" };
                  return (
                    <div
                      key={lib.id}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        padding: "10px 0",
                        borderBottom: "1px solid #f0f1f3",
                      }}
                    >
                      <div style={{ flex: 1, minWidth: 0, marginRight: 12 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: "#172b4d", display: "flex", alignItems: "center", gap: 8 }}>
                          <span style={{
                            fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 3,
                            background: kindColor.bg, color: kindColor.fg, letterSpacing: ".04em",
                          }}>{kindLabel}</span>
                          {lib.name}
                        </div>
                        <div style={{ fontSize: 11, color: "#5e6c84", marginTop: 2 }}>
                          {lib.description || <em>No description</em>}
                        </div>
                        <div style={{ fontSize: 10, color: "#97a0af", marginTop: 2 }}>
                          <span style={{
                            fontSize: 10, fontWeight: 700, padding: "1px 5px", borderRadius: 3,
                            background: lib.is_system ? "#f4f5f7" : "#fff8e6",
                            color: lib.is_system ? "#5e6c84" : "#974f0c",
                          }}>{lib.is_system ? "SYSTEM" : "YOURS"}</span>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={async () => {
                          try {
                            await artifactTypesAPI.fromLibrary(projectId, lib.id);
                            onAdded?.();
                            onClose();
                          } catch (e) {
                            alert(
                              `Failed to add: ${e instanceof Error ? e.message : String(e)}`
                            );
                          }
                        }}
                        style={{
                          fontSize: 11,
                          fontWeight: 600,
                          color: "white",
                          background: "#0052cc",
                          border: "none",
                          borderRadius: 4,
                          padding: "6px 12px",
                          cursor: "pointer",
                          flexShrink: 0,
                        }}
                      >
                        Add
                      </button>
                    </div>
                  );
                })}
              <div className="flex justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="text-[13px] text-[#5e6c84] hover:text-[#172b4d]"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Create new tab */}
          {tab === "create" && (
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
              <div>
                <label style={{ display: "block", marginBottom: 8 }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: "#172b4d", display: "block", marginBottom: 4 }}>
                    Context scope
                  </span>
                  <select
                    value={contextScope}
                    onChange={(e) => setContextScope(e.target.value as ContextScope)}
                    style={{ width: "100%", fontSize: 13, border: "1px solid #dfe1e6", borderRadius: 4, padding: "8px 10px", background: "white", color: "#172b4d" }}
                  >
                    {CONTEXT_SCOPE_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </label>
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

          {/* Import tab */}
          {tab === "import" && (
            <div className="space-y-3">
              {loadingProjects ? (
                <p className="text-[13px] text-[#5e6c84]">Loading projects…</p>
              ) : !projects || projects.length === 0 ? (
                projectsLoadError ? (
                  <div className="flex flex-col gap-2">
                    <p className="text-[13px] text-red-600">Failed to load projects.</p>
                    <button
                      onClick={() => {
                        setProjectsLoadError(false);
                        setProjects(null);
                        handleSwitchToImport();
                      }}
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
                    <label className="block text-[12px] font-medium text-[#172b4d] mb-1">
                      Project
                    </label>
                    <select
                      value={selectedProjectId}
                      onChange={(e) => handleSelectProject(e.target.value)}
                      className="w-full border border-[#dfe1e6] rounded px-3 py-2 text-[13px] focus:outline-none focus:border-[#0052cc] bg-white"
                    >
                      <option value="">Select a project…</option>
                      {projects.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  {typesLoadError && (
                    <p className="text-[13px] text-red-600">
                      Failed to load artifact types. Try selecting the project again.
                    </p>
                  )}

                  {loadingTypes && (
                    <p className="text-[13px] text-[#5e6c84]">Loading types…</p>
                  )}

                  {!loadingTypes && selectedProjectId && sourceTypes.length === 0 && (
                    <p className="text-[13px] text-[#5e6c84]">
                      No artifact types in this project.
                    </p>
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
