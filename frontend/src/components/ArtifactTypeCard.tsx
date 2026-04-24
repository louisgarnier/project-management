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

const KIND_THEME = {
  llm:      { bg: "linear-gradient(90deg, #e9f0ff 0%, #f4f8ff 100%)", accent: "#0052cc", label: "LLM",      icon: "🤖" },
  template: { bg: "linear-gradient(90deg, #e3fcef 0%, #f1fdf8 100%)", accent: "#006644", label: "TEMPLATE", icon: "🔧" },
  hybrid:   { bg: "linear-gradient(90deg, #fff4e6 0%, #fff9f0 100%)", accent: "#974f0c", label: "HYBRID",   icon: "⚡" },
} as const;

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
  const theme = KIND_THEME[effectiveKind];

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
    <div style={{
      borderRadius: 8,
      overflow: "hidden",
      border: `1px solid ${editing ? "#ff8b00" : "#dfe1e6"}`,
      marginBottom: 10,
    }}>
      {/* ── Header strip ── */}
      <div style={{
        background: theme.bg,
        borderBottom: `2px solid ${theme.accent}`,
        padding: "10px 14px",
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>

          {/* LEFT: kind badge + status chips + name */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1, minWidth: 0 }}>
            {/* Kind badge */}
            <span style={{
              fontSize: 10, fontWeight: 700, padding: "3px 8px",
              background: theme.accent, color: "white", borderRadius: 4,
              letterSpacing: ".04em", flexShrink: 0,
            }}>
              {theme.icon} {theme.label}
            </span>

            {/* Default toggle */}
            {!hideDefaultToggle && (
              <button
                title={type.is_default ? "Included in new projects — click to remove" : "Not included in new projects — click to add"}
                onClick={() => onUpdate(type.id, { is_default: !type.is_default })}
                style={{
                  flexShrink: 0,
                  display: "flex", alignItems: "center", gap: 4,
                  fontSize: 9, fontWeight: 700, padding: "3px 7px", borderRadius: 4,
                  letterSpacing: ".04em", cursor: "pointer",
                  background: "white", border: "1px solid rgba(0,0,0,.08)",
                  color: type.is_default ? "#0052cc" : "#97a0af",
                }}
              >
                {type.is_default ? "✓ Default" : "+ Default"}
              </button>
            )}

            {/* Diff-vs-canonical badge (LLM kind only) */}
            {librarySource && effectiveKind === "llm" && (
              isEdited ? (
                <span style={{ fontSize: 9, fontWeight: 700, padding: "3px 7px", background: "white", border: "1px solid rgba(0,0,0,.08)", color: "#974f0c", borderRadius: 4, flexShrink: 0 }}>
                  ✎ edited
                </span>
              ) : (
                <span style={{ fontSize: 9, fontWeight: 700, padding: "3px 7px", background: "white", border: "1px solid rgba(0,0,0,.08)", color: "#5e6c84", borderRadius: 4, flexShrink: 0 }}>
                  ⟲ canonical
                </span>
              )
            )}

            {/* Name */}
            {editing ? (
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                style={{
                  fontSize: 15, fontWeight: 700, color: "#172b4d",
                  outline: "none", flex: 1, minWidth: 0,
                  background: "transparent", border: "none",
                  borderBottom: "2px solid #0052cc",
                }}
              />
            ) : (
              <h3 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {type.name}
              </h3>
            )}
          </div>

          {/* RIGHT: action buttons */}
          <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
            {editing ? (
              <>
                <button
                  onClick={handleCancelEdit}
                  style={{ fontSize: 11, color: "#97a0af", background: "none", border: "none", cursor: "pointer", padding: "5px 8px" }}
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving || !name.trim()}
                  style={{
                    fontSize: 11, fontWeight: 600, color: "white",
                    background: "#0052cc", border: "none", borderRadius: 4,
                    padding: "5px 12px", cursor: saving ? "default" : "pointer",
                    opacity: (saving || !name.trim()) ? 0.6 : 1,
                  }}
                >
                  {saving ? "Saving…" : "Save"}
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => setExpanded((v) => !v)}
                  title={expanded ? "Collapse" : "Expand"}
                  style={{
                    fontSize: 13, color: "#5e6c84", background: "white",
                    border: "1px solid rgba(0,0,0,.08)", borderRadius: 4,
                    padding: "3px 10px", cursor: "pointer", lineHeight: 1,
                  }}
                >
                  {expanded ? "▾" : "▸"}
                </button>
                <button
                  onClick={() => {
                    setEditing(true);
                    setExpanded(true);
                  }}
                  style={{
                    fontSize: 11, fontWeight: 600,
                    background: "white", border: `1px solid ${theme.accent}`,
                    color: theme.accent, borderRadius: 4,
                    padding: "5px 12px", cursor: "pointer",
                  }}
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
                    style={{ fontSize: 13, color: "#97a0af", background: "none", border: "none", cursor: "pointer", padding: "5px 6px", lineHeight: 1 }}
                    title="Delete"
                  >
                    ✕
                  </button>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* ── Body (collapsed by default; expands via chevron or enters edit mode) ── */}
      {(expanded || editing) && (
      <div style={{ background: "white", padding: "14px 16px" }}>

        {/* Description (from librarySource when available) */}
        {librarySource?.description && !editing && (
          <p style={{ fontSize: 12, color: "#5e6c84", lineHeight: 1.5, margin: "0 0 12px 0" }}>
            {librarySource.description}
          </p>
        )}

        {/* Metadata grid — visible when NOT editing */}
        {!editing && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 12 }}>
            {/* PROVIDER */}
            <div style={{ background: "#fafbfc", padding: "8px 10px", borderRadius: 4, border: "1px solid #ebecf0" }}>
              <div style={{ fontSize: 9, color: "#97a0af", fontWeight: 600, letterSpacing: ".05em", marginBottom: 2 }}>PROVIDER</div>
              {effectiveKind === "template" ? (
                <div style={{ color: "#172b4d", fontSize: 12, fontWeight: 600 }}>No LLM · deterministic</div>
              ) : (
                <>
                  <div style={{ color: "#172b4d", fontSize: 12, fontWeight: 600 }}>
                    {PROVIDER_LABELS[effectiveLlm]}
                    {!type.llm && <span style={{ color: "#97a0af", fontWeight: 400, fontSize: 10 }}> (inherited)</span>}
                  </div>
                  {effectiveLlm === "openrouter" && effectiveModel && (
                    <div style={{ color: "#5e6c84", fontSize: 10, fontFamily: "ui-monospace, Menlo, monospace", marginTop: 2 }}>
                      {effectiveModel}
                    </div>
                  )}
                </>
              )}
            </div>

            {/* SCOPE */}
            <div style={{ background: "#fafbfc", padding: "8px 10px", borderRadius: 4, border: "1px solid #ebecf0" }}>
              <div style={{ fontSize: 9, color: "#97a0af", fontWeight: 600, letterSpacing: ".05em", marginBottom: 2 }}>SCOPE</div>
              <div style={{ color: "#172b4d", fontSize: 12, fontWeight: 600 }}>
                {(type.context_scope ?? "call") === "project" ? "Full project" : "Call only"}
              </div>
            </div>

            {/* COST */}
            <div style={{
              padding: "8px 10px", borderRadius: 4,
              background: effectiveKind === "template" ? "#e3fcef" : "#fafbfc",
              border: effectiveKind === "template" ? "1px solid #abf5d1" : "1px solid #ebecf0",
            }}>
              <div style={{ fontSize: 9, color: effectiveKind === "template" ? "#006644" : "#97a0af", fontWeight: 600, letterSpacing: ".05em", marginBottom: 2 }}>COST/CALL</div>
              <div style={{ color: effectiveKind === "template" ? "#006644" : "#172b4d", fontSize: 12, fontWeight: 700 }}>
                {effectiveKind === "template" ? "$0" :
                 effectiveKind === "hybrid" ? `${estimateCost(effectiveModel)} × 2` :
                 estimateCost(effectiveModel)}
              </div>
            </div>
          </div>
        )}

        {/* Edit mode — provider/scope pickers (LLM + hybrid only) */}
        {editing && effectiveKind !== "template" && (
          <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
            <select
              value={llm ?? "inherit"}
              onChange={(e) => {
                const val = e.target.value;
                setLlm(val === "inherit" ? null : (val as LLMProvider));
                if (val !== "openrouter") setModel(null);
              }}
              style={{ fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "5px 8px", background: "white", color: "#172b4d" }}
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
              style={{ fontSize: 11, border: "1px solid #dfe1e6", borderRadius: 4, padding: "5px 8px", background: "white", color: "#172b4d" }}
            >
              <option value="call">Call only</option>
              <option value="project">Full project</option>
            </select>
          </div>
        )}

        {/* Kind-conditional content — always rendered inside the body
             (the whole body is gated by expanded/editing above) */}
        {true && (
          <>
            {effectiveKind === "template" ? (
              /* ── Template kind ── */
              <div style={{ paddingTop: 4 }}>
                {!librarySource?.description && (
                  <p style={{ fontSize: 12, color: "#5e6c84", lineHeight: 1.5 }}>
                    Deterministic template — renders from your topic data with no LLM call.
                  </p>
                )}
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
              <div style={{ paddingTop: 4 }}>
                {!librarySource?.description && (
                  <p style={{ fontSize: 12, color: "#5e6c84", lineHeight: 1.5 }}>
                    <strong>Hybrid artifact:</strong> Template skeleton + LLM-generated intro &amp; closing.
                  </p>
                )}
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
              /* ── LLM kind ── */
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

                    {/* Publish to library — only for custom (non-library-linked) LLM types */}
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
                  <p style={{ marginTop: 0, fontSize: 12, color: "#5e6c84", lineHeight: 1.6, whiteSpace: "pre-wrap", background: "#f4f5f7", borderRadius: 4, padding: "10px 12px" }}>
                    {type.prompt}
                  </p>
                  {type.model && (
                    <p style={{ marginTop: 4, fontSize: 10, color: "#97a0af" }}>Model: {type.model}</p>
                  )}
                </>
              )
            )}
          </>
        )}

        {saveError && <p style={{ marginTop: 8, fontSize: 11, color: "#ae2a19" }}>{saveError}</p>}
      </div>
      )}

      <PublishToLibraryDialog
        type={type}
        open={publishDialogOpen}
        onClose={() => setPublishDialogOpen(false)}
        onPublished={() => {
          window.location.reload();
        }}
      />
    </div>
  );
}
