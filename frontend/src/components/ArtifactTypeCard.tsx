"use client";

import { useState, useEffect } from "react";
import type { ArtifactType, LLMProvider, ContextScope, LibraryEntry, SystemSettings } from "@/types";
import { MODEL_RECOMMENDATIONS, PROVIDER_LABELS, estimateCost } from "@/constants/models";
import { artifactTypesAPI } from "@/api/client";
import PublishToLibraryDialog from "@/components/PublishToLibraryDialog";

type Props = {
  type: ArtifactType;
  projectDefaultLlm: LLMProvider | null;
  projectDefaultModel?: string | null;
  systemSettings?: SystemSettings | null;
  onDelete: (id: string) => void;
  onUpdate: (id: string, data: { name?: string; prompt?: string; llm?: LLMProvider | null; model?: string | null; context_scope?: ContextScope; is_default?: boolean }) => Promise<void>;
  hideDelete?: boolean;
  hideDefaultToggle?: boolean;
};

export default function ArtifactTypeCard({ type, projectDefaultLlm, projectDefaultModel, systemSettings, onDelete, onUpdate, hideDelete, hideDefaultToggle }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(type.name);
  const [prompt, setPrompt] = useState(type.prompt);
  const [llm, setLlm] = useState<LLMProvider | null>(type.llm);
  const [model, setModel] = useState<string | null>(type.model ?? null);
  const [contextScope, setContextScope] = useState<ContextScope>(type.context_scope ?? "call");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [promptExpanded, setPromptExpanded] = useState(false);

  // New state for diff-vs-canonical badge + publish stub
  const [librarySource, setLibrarySource] = useState<LibraryEntry | null>(null);
  const [isEdited, setIsEdited] = useState(false);
  const [publishDialogOpen, setPublishDialogOpen] = useState(false);

  useEffect(() => {
    let active = true;
    artifactTypesAPI.getLibrarySource(type.id).then((src) => {
      if (!active) return;
      setLibrarySource(src);
      if (src && src.prompt !== null && type.prompt !== null) {
        setIsEdited((src.prompt || "").trim() !== (type.prompt || "").trim());
      }
    }).catch(() => {
      // non-canonical custom types — no source, no diff
    });
    return () => { active = false; };
  }, [type.id, type.prompt]);

  function handleCancelEdit() {
    setEditing(false);
    setName(type.name);
    setPrompt(type.prompt);
    setLlm(type.llm);
    setModel(type.model ?? null);
    setContextScope(type.context_scope ?? "call");
    setSaveError(null);
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(null);
    try {
      await onUpdate(type.id, { name, prompt, llm, model, context_scope: contextScope });
      setEditing(false);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  const effectiveKind = type.kind ?? "llm";

  const effectiveLlm: LLMProvider =
    type.llm ??
    projectDefaultLlm ??
    systemSettings?.default_llm ??
    "openrouter";
  const effectiveModel: string | null =
    type.model ??
    (type.llm === null || type.llm === undefined ? projectDefaultModel ?? null : null) ??
    systemSettings?.default_model ??
    null;

  return (
    <div
      className="border rounded-lg p-4 bg-white transition-colors"
      style={{ borderColor: editing ? "#ff8b00" : "#dfe1e6" }}
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {!hideDefaultToggle && (
            <button
              title={type.is_default ? "Included in new projects — click to remove" : "Not included in new projects — click to add"}
              onClick={() => onUpdate(type.id, { is_default: !type.is_default })}
              className="flex-shrink-0 flex items-center gap-1 text-[9px] font-bold px-[5px] py-[1px] rounded uppercase tracking-[.04em] transition-colors"
              style={
                type.is_default
                  ? { background: "#e9f0ff", color: "#0052cc", border: "1px solid #b3c6e8" }
                  : { background: "#f4f5f7", color: "#97a0af", border: "1px solid #dfe1e6" }
              }
            >
              {type.is_default ? "✓ Default" : "+ Default"}
            </button>
          )}

          {/* Diff-vs-canonical badge (LLM kind only) */}
          {librarySource && effectiveKind === "llm" && (
            isEdited ? (
              <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", background: "#fff4e6", color: "#974f0c", borderRadius: 3 }}>
                ✎ edited
              </span>
            ) : (
              <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", background: "#f4f5f7", color: "#5e6c84", borderRadius: 3 }}>
                ⟲ canonical
              </span>
            )
          )}

          {editing ? (
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="text-[14px] font-semibold text-[#172b4d] border-b-2 border-[#0052cc] outline-none flex-1 min-w-0 bg-transparent"
            />
          ) : (
            <h3 className="text-[14px] font-semibold text-[#172b4d] truncate">{type.name}</h3>
          )}
        </div>

        {/* Provider + context scope — always visible in header (LLM and hybrid kinds) */}
        {effectiveKind !== "template" && (
          <div className="flex items-center gap-2 flex-shrink-0">
            {editing ? (
              <>
                <select
                  value={llm ?? "inherit"}
                  onChange={(e) => {
                    const val = e.target.value;
                    setLlm(val === "inherit" ? null : (val as LLMProvider));
                    if (val !== "openrouter") setModel(null);
                  }}
                  className="text-[11px] border border-[#dfe1e6] rounded px-2 py-1 bg-white text-[#172b4d] focus:outline-none focus:border-[#0052cc]"
                >
                  <option value="inherit">{PROVIDER_LABELS.inherit}</option>
                  <option value="groq">{PROVIDER_LABELS.groq}</option>
                  <option value="deepseek">{PROVIDER_LABELS.deepseek}</option>
                  <option value="claude">{PROVIDER_LABELS.claude}</option>
                  <option value="openai">{PROVIDER_LABELS.openai}</option>
                  <option value="openrouter">{PROVIDER_LABELS.openrouter}</option>
                </select>
                <select
                  value={contextScope}
                  onChange={(e) => setContextScope(e.target.value as ContextScope)}
                  className="text-[11px] border border-[#dfe1e6] rounded px-2 py-1 bg-white text-[#172b4d] focus:outline-none focus:border-[#0052cc]"
                >
                  <option value="call">Call only</option>
                  <option value="project">Full project</option>
                </select>
              </>
            ) : (
              <>
                <span className="text-[11px] text-[#5e6c84] bg-[#f4f5f7] px-2 py-[3px] rounded">
                  {PROVIDER_LABELS[effectiveLlm]}
                  {effectiveLlm === "openrouter" && effectiveModel ? ` · ${effectiveModel}` : ""}
                  {!type.llm && (
                    <span style={{ fontSize: 9, color: "#97a0af", marginLeft: 4 }}>
                      (inherited)
                    </span>
                  )}
                </span>
                <span
                  className="text-[10px] font-medium px-2 py-[3px] rounded"
                  style={
                    (type.context_scope ?? "call") === "project"
                      ? { background: "#e3fcef", color: "#006644" }
                      : { background: "#f4f5f7", color: "#5e6c84" }
                  }
                >
                  {(type.context_scope ?? "call") === "project" ? "Full project" : "Call only"}
                </span>
              </>
            )}
          </div>
        )}

        <div className="flex items-center gap-3 flex-shrink-0">
          {editing ? (
            <>
              <button
                onClick={handleCancelEdit}
                className="text-[11px] text-[#97a0af] hover:text-[#172b4d]"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !name.trim()}
                className="text-[11px] text-[#0052cc] hover:underline disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => {
                  setEditing(true);
                  setExpanded(true);
                }}
                className="text-[11px] text-[#5e6c84] hover:text-[#0052cc] hover:underline"
              >
                Edit
              </button>
              {!hideDelete && (
                <button
                  onClick={() => {
                    if (confirm(`Delete "${type.name}"? This cannot be undone.`)) {
                      onDelete(type.id);
                    }
                  }}
                  className="text-[11px] text-[#97a0af] hover:text-red-500"
                >
                  ✕
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Expand toggle */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="mt-2 text-[11px] text-[#5e6c84] hover:text-[#0052cc] flex items-center gap-1"
      >
        <span>{expanded ? "▾" : "▸"}</span>
        <span>{expanded ? "Hide details" : "View details"}</span>
      </button>

      {/* Card body — forked on kind */}
      {expanded && (
        <>
          {effectiveKind === "template" ? (
            /* ── Template kind ── */
            <div style={{ padding: "8px 0 4px" }}>
              <p style={{ fontSize: 12, color: "#5e6c84", lineHeight: 1.5 }}>
                {librarySource?.description || "Deterministic template — renders from your topic data with no LLM call."}
              </p>
              <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center" }}>
                <button
                  type="button"
                  onClick={async () => {
                    const latestCall = window.prompt("Call ID to preview with?");
                    if (!latestCall) return;
                    try {
                      const { content } = await artifactTypesAPI.preview(type.id, latestCall);
                      alert(content);
                    } catch (e) {
                      alert(`Preview failed: ${e instanceof Error ? e.message : String(e)}`);
                    }
                  }}
                  style={{ fontSize: 11, color: "#0052cc", background: "none", border: "1px solid #b3c6e8", borderRadius: 4, padding: "4px 10px", cursor: "pointer" }}
                >
                  ▷ Preview
                </button>
                <span style={{ fontSize: 11, color: "#006644" }}>Cost: $0 (template)</span>
              </div>
            </div>
          ) : effectiveKind === "hybrid" ? (
            /* ── Hybrid kind ── */
            <div style={{ padding: "8px 0 4px" }}>
              <p style={{ fontSize: 12, color: "#5e6c84", lineHeight: 1.5 }}>
                <strong>Hybrid artifact:</strong> {librarySource?.description || "Template skeleton + LLM-generated intro & closing."}
              </p>
              {editing && (() => {
                let parts: { intro?: string; closing?: string } = {};
                try { parts = JSON.parse(type.prompt || "{}"); } catch { /* ignore */ }
                return (
                  <>
                    <label style={{ fontSize: 11, color: "#5e6c84", display: "block", marginTop: 8 }}>Intro prompt</label>
                    <textarea
                      value={parts.intro || ""}
                      onChange={(e) => {
                        const next = JSON.stringify({ intro: e.target.value, closing: parts.closing || "" });
                        setPrompt(next);
                      }}
                      rows={2}
                      style={{ width: "100%", fontSize: 12, border: "1px solid #dfe1e6", borderRadius: 4, padding: "6px 8px", fontFamily: "inherit", boxSizing: "border-box" }}
                    />
                    <label style={{ fontSize: 11, color: "#5e6c84", display: "block", marginTop: 6 }}>Closing prompt</label>
                    <textarea
                      value={parts.closing || ""}
                      onChange={(e) => {
                        const next = JSON.stringify({ intro: parts.intro || "", closing: e.target.value });
                        setPrompt(next);
                      }}
                      rows={2}
                      style={{ width: "100%", fontSize: 12, border: "1px solid #dfe1e6", borderRadius: 4, padding: "6px 8px", fontFamily: "inherit", boxSizing: "border-box" }}
                    />
                  </>
                );
              })()}
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <span style={{ fontSize: 11, color: "#5e6c84" }}>
                  Cost: {type.llm === "openrouter" ? estimateCost(type.model) : "—"} (2 short LLM calls)
                </span>
              </div>
            </div>
          ) : (
            /* ── LLM kind (default) — keep existing markup intact ── */
            editing ? (
              <>
                {/* OpenRouter model picker */}
                {llm === "openrouter" && (
                  <div style={{ marginTop: 10, marginBottom: 8 }}>
                    <label style={{ fontSize: 11, color: "#5e6c84", display: "block", marginBottom: 4 }}>
                      Model (OpenRouter slug)
                    </label>
                    <input
                      type="text"
                      list={`openrouter-models-${type.id}`}
                      value={model ?? ""}
                      onChange={(e) => setModel(e.target.value)}
                      placeholder="e.g. deepseek/deepseek-v3.2 — type any slug or click ▾ for suggestions"
                      style={{ fontSize: 12, border: "1px solid #dfe1e6", borderRadius: 4, padding: "6px 8px", fontFamily: "ui-monospace, Menlo, monospace", width: "100%", boxSizing: "border-box" }}
                    />
                    <datalist id={`openrouter-models-${type.id}`}>
                      {(MODEL_RECOMMENDATIONS[type.category] ?? []).map((m) => (
                        <option key={m.slug} value={m.slug}>
                          {m.label}{m.priceHint ? ` · ${m.priceHint}` : ""}
                        </option>
                      ))}
                    </datalist>
                    <p style={{ fontSize: 10, color: "#97a0af", marginTop: 4 }}>
                      Any model on <a href="https://openrouter.ai/models" target="_blank" rel="noopener noreferrer" style={{ color: "#0052cc" }}>openrouter.ai/models</a> works — paste its slug here.
                    </p>
                  </div>
                )}

                {/* Cost estimate when editing with OpenRouter */}
                {llm === "openrouter" && (
                  <div style={{ padding: "4px 0", fontSize: 11, color: "#5e6c84" }}>
                    Cost estimate: {estimateCost(model)} per call
                  </div>
                )}

                {/* Expandable prompt textarea */}
                <div style={{ position: "relative", marginTop: 8 }}>
                  <textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    rows={promptExpanded ? 25 : 6}
                    style={{
                      width: "100%", fontSize: 12, fontFamily: "ui-monospace, Menlo, monospace",
                      color: "#172b4d", border: "1px solid #dfe1e6", borderRadius: 4,
                      padding: "8px 10px", resize: "vertical", boxSizing: "border-box",
                      minHeight: promptExpanded ? 500 : 120,
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setPromptExpanded((v) => !v)}
                    title={promptExpanded ? "Collapse" : "Expand for easier editing"}
                    style={{ position: "absolute", top: 6, right: 6, background: "rgba(255,255,255,.9)", border: "1px solid #dfe1e6", borderRadius: 3, padding: "2px 6px", fontSize: 10, cursor: "pointer" }}
                  >
                    {promptExpanded ? "⤡ Collapse" : "⤢ Expand"}
                  </button>
                </div>

                {/* Runtime context disclosure — call_topics only */}
                {type.category === "call_topics" && (
                  <details style={{ marginTop: 8, fontSize: 11 }}>
                    <summary style={{ cursor: "pointer", color: "#5e6c84" }}>
                      Show runtime context (appended automatically at extraction time)
                    </summary>
                    <pre style={{ fontSize: 10, background: "#fafbfc", padding: 8, borderRadius: 4, color: "#5e6c84", whiteSpace: "pre-wrap", marginTop: 6 }}>
{`Project context: {projects.context}

Existing project topic names (vocabulary alignment):
  - {name 1}
  - {name 2}
  ...

Response schema: { ... fixed JSON shape ... }

Transcript:
{full transcript}`}
                    </pre>
                    <p style={{ fontSize: 10, color: "#97a0af", marginTop: 4 }}>
                      These blocks are added automatically by the extraction pipeline — they cannot be edited here.
                    </p>
                  </details>
                )}

                {/* Action row: Reset to default (left) + Publish stub */}
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10 }}>
                  <button
                    type="button"
                    onClick={async () => {
                      if (!confirm("Overwrite your current prompt and settings with the latest default? Your edits will be lost.")) return;
                      try {
                        const def = await artifactTypesAPI.getDefaults(type.category);
                        setPrompt(def.prompt);
                        setLlm(def.llm);
                        setModel(def.model);
                      } catch (err) {
                        setSaveError(err instanceof Error ? err.message : "Failed to load defaults");
                      }
                    }}
                    style={{ fontSize: 11, color: "#5e6c84", background: "none", border: "1px solid #dfe1e6", borderRadius: 4, padding: "4px 10px", cursor: "pointer", marginRight: "auto" }}
                  >
                    ⟲ Reset to default
                  </button>

                  {/* Publish to library stub — only for custom (non-library-linked) LLM types */}
                  {!type.library_ref_id && (
                    <button
                      type="button"
                      onClick={() => setPublishDialogOpen(true)}
                      style={{ fontSize: 11, color: "#5e6c84", background: "none", border: "1px solid #dfe1e6", borderRadius: 4, padding: "4px 10px", cursor: "pointer" }}
                    >
                      ↗ Publish to library
                    </button>
                  )}
                </div>
              </>
            ) : (
              <>
                <p className="mt-2 text-[12px] text-[#5e6c84] leading-relaxed whitespace-pre-wrap bg-[#f4f5f7] rounded p-3">
                  {type.prompt}
                </p>
                {type.model && (
                  <p className="mt-1 text-[10px] text-[#97a0af]">Model: {type.model}</p>
                )}
              </>
            )
          )}
        </>
      )}

      {saveError && <p className="mt-2 text-[11px] text-red-600">{saveError}</p>}

      <PublishToLibraryDialog
        type={type}
        open={publishDialogOpen}
        onClose={() => setPublishDialogOpen(false)}
        onPublished={() => {
          // Refresh so library_ref_id shows up and Publish button hides.
          // Reload the full page because ArtifactTypeCard doesn't have a parent
          // refresh callback; acceptable as a minimal UX here.
          window.location.reload();
        }}
      />
    </div>
  );
}
