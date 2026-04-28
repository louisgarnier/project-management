"use client";

import { useState } from "react";
import type { LibraryEntry } from "@/types";
import { libraryAPI } from "@/api/client";
import { MODEL_RECOMMENDATIONS } from "@/constants/models";

const KIND_THEME = {
  llm:      { bg: "linear-gradient(90deg, #e9f0ff 0%, #f4f8ff 100%)", accent: "#0052cc", label: "LLM",      icon: "🤖" },
  template: { bg: "linear-gradient(90deg, #e3fcef 0%, #f1fdf8 100%)", accent: "#006644", label: "TEMPLATE", icon: "🔧" },
  hybrid:   { bg: "linear-gradient(90deg, #fff4e6 0%, #fff9f0 100%)", accent: "#974f0c", label: "HYBRID",   icon: "⚡" },
} as const;

export default function LibraryEntryCard({
  entry,
  onUpdated,
  onDeleted,
}: {
  entry: LibraryEntry;
  onUpdated: () => void;
  onDeleted: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState<LibraryEntry>(entry);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const theme = KIND_THEME[entry.kind ?? "llm"];

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await libraryAPI.update(entry.id, {
        name: draft.name,
        description: draft.description,
        prompt: draft.prompt,
        llm: draft.llm,
        model: draft.model,
        context_scope: draft.context_scope,
        seeded_by_default: draft.seeded_by_default,
      });
      onUpdated();
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function del() {
    if (!confirm(`Delete library entry "${entry.name}"?`)) return;
    try {
      await libraryAPI.delete(entry.id);
      onDeleted();
    } catch (e) {
      alert(`Failed to delete: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

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

            {/* SYSTEM / YOURS chip */}
            <span style={{
              fontSize: 9, fontWeight: 700, padding: "3px 7px", borderRadius: 4,
              background: "white", border: "1px solid rgba(0,0,0,.08)",
              color: entry.is_system ? "#5e6c84" : "#974f0c",
              flexShrink: 0,
            }}>
              {entry.is_system ? "SYSTEM" : "YOURS"}
            </span>

            {/* AUTO-SEEDED chip */}
            {entry.seeded_by_default && (
              <span style={{
                fontSize: 9, fontWeight: 700, padding: "3px 7px", borderRadius: 4,
                background: "white", border: "1px solid rgba(0,0,0,.08)",
                color: "#006644", flexShrink: 0,
              }}>
                AUTO-SEEDED
              </span>
            )}

            {/* Category chip — show if not 'artifacts' */}
            {entry.category && entry.category !== "artifacts" && (
              <span style={{
                fontSize: 9, fontWeight: 700, padding: "3px 7px", borderRadius: 4,
                background: "white", border: "1px solid rgba(0,0,0,.08)",
                color: "#5e6c84", flexShrink: 0, letterSpacing: ".04em",
              }}>
                WORKFLOW
              </span>
            )}

            {/* Name */}
            {editing ? (
              <input
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                style={{
                  fontSize: 15, fontWeight: 700, color: "#172b4d",
                  outline: "none", flex: 1, minWidth: 0,
                  background: "transparent", border: "none",
                  borderBottom: "2px solid #0052cc",
                }}
              />
            ) : (
              <h3 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {entry.name}
              </h3>
            )}
          </div>

          {/* RIGHT: action buttons */}
          <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
            {editing ? (
              <>
                <button
                  type="button"
                  onClick={() => { setDraft(entry); setEditing(false); setError(null); }}
                  style={{ fontSize: 11, color: "#97a0af", background: "none", border: "none", cursor: "pointer", padding: "5px 8px" }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={save}
                  disabled={saving}
                  style={{
                    fontSize: 11, fontWeight: 600, color: "white",
                    background: "#0052cc", border: "none", borderRadius: 4,
                    padding: "5px 12px", cursor: saving ? "default" : "pointer",
                    opacity: saving ? 0.6 : 1,
                  }}
                >
                  {saving ? "Saving…" : "Save"}
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
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
                  type="button"
                  onClick={() => { setEditing(true); setExpanded(true); }}
                  style={{
                    fontSize: 11, fontWeight: 600,
                    background: "white", border: `1px solid ${theme.accent}`,
                    color: theme.accent, borderRadius: 4,
                    padding: "5px 12px", cursor: "pointer",
                  }}
                >
                  Edit
                </button>
                {!entry.is_system && (
                  <button
                    type="button"
                    onClick={del}
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

        {/* Description (view mode) */}
        {!editing && (
          <p style={{ fontSize: 12, color: "#5e6c84", lineHeight: 1.5, margin: "0 0 12px 0" }}>
            {entry.description || <em>No description</em>}
          </p>
        )}

        {/* Metadata grid — view mode */}
        {!editing && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 4 }}>
            {/* KIND DETAILS */}
            <div style={{ background: "#fafbfc", padding: "8px 10px", borderRadius: 4, border: "1px solid #ebecf0" }}>
              <div style={{ fontSize: 9, color: "#97a0af", fontWeight: 600, letterSpacing: ".05em", marginBottom: 2 }}>KIND DETAILS</div>
              {entry.kind === "template" ? (
                <div style={{ color: "#172b4d", fontSize: 12, fontWeight: 600 }}>No LLM · deterministic</div>
              ) : (
                <>
                  <div style={{ color: "#172b4d", fontSize: 12, fontWeight: 600 }}>
                    {entry.llm ?? "openrouter"}
                  </div>
                  {entry.model && (
                    <div style={{ color: "#5e6c84", fontSize: 10, fontFamily: "ui-monospace, Menlo, monospace", marginTop: 2 }}>
                      {entry.model}
                    </div>
                  )}
                </>
              )}
            </div>

            {/* CATEGORY */}
            <div style={{ background: "#fafbfc", padding: "8px 10px", borderRadius: 4, border: "1px solid #ebecf0" }}>
              <div style={{ fontSize: 9, color: "#97a0af", fontWeight: 600, letterSpacing: ".05em", marginBottom: 2 }}>CATEGORY</div>
              <div style={{ color: "#172b4d", fontSize: 12, fontWeight: 600 }}>
                {entry.category ?? "—"}
              </div>
            </div>

            {/* SEEDED */}
            <div style={{
              padding: "8px 10px", borderRadius: 4,
              background: entry.seeded_by_default ? "#e3fcef" : "#fafbfc",
              border: entry.seeded_by_default ? "1px solid #abf5d1" : "1px solid #ebecf0",
            }}>
              <div style={{ fontSize: 9, color: entry.seeded_by_default ? "#006644" : "#97a0af", fontWeight: 600, letterSpacing: ".05em", marginBottom: 2 }}>NEW PROJECTS</div>
              <div style={{ color: entry.seeded_by_default ? "#006644" : "#172b4d", fontSize: 12, fontWeight: 600 }}>
                {entry.seeded_by_default ? "Auto-seeded" : "Not seeded"}
              </div>
            </div>
          </div>
        )}

        {/* Edit mode */}
        {editing && (
          <div style={{ marginTop: 4 }}>
            {error && (
              <div style={{ background: "#fff1f0", border: "1px solid #ffbdad", borderRadius: 4, padding: "6px 10px", fontSize: 11, color: "#ae2a19", marginBottom: 8 }}>
                {error}
              </div>
            )}
            <label style={{ fontSize: 11, color: "#5e6c84", display: "block" }}>Description</label>
            <input
              value={draft.description}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              style={{ fontSize: 12, border: "1px solid #dfe1e6", borderRadius: 4, padding: "4px 6px", width: "100%", fontFamily: "inherit", boxSizing: "border-box" }}
            />
            {entry.kind === "llm" && (
              <>
                <label style={{ fontSize: 11, color: "#5e6c84", display: "block", marginTop: 8 }}>Prompt</label>
                <textarea
                  value={draft.prompt || ""}
                  onChange={(e) => setDraft({ ...draft, prompt: e.target.value })}
                  rows={8}
                  style={{ width: "100%", fontSize: 12, border: "1px solid #dfe1e6", borderRadius: 4, padding: "6px 8px", fontFamily: "ui-monospace, Menlo, monospace", boxSizing: "border-box" }}
                />
                <label style={{ fontSize: 11, color: "#5e6c84", display: "block", marginTop: 8 }}>Default model (OpenRouter slug)</label>
                <input
                  type="text"
                  list={`openrouter-models-lib-${entry.id}`}
                  value={draft.model || ""}
                  onChange={(e) => setDraft({ ...draft, model: e.target.value })}
                  placeholder="e.g. deepseek/deepseek-v3.2 — type any slug or click ▾ for suggestions"
                  style={{ fontSize: 12, border: "1px solid #dfe1e6", borderRadius: 4, padding: "4px 6px", fontFamily: "ui-monospace, Menlo, monospace", width: "100%", boxSizing: "border-box" }}
                />
                <datalist id={`openrouter-models-lib-${entry.id}`}>
                  {(MODEL_RECOMMENDATIONS[entry.category ?? "artifacts"] ?? []).map((m) => (
                    <option key={m.slug} value={m.slug}>
                      {m.label}{m.priceHint ? ` · ${m.priceHint}` : ""}
                    </option>
                  ))}
                </datalist>
              </>
            )}
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#5e6c84", marginTop: 8 }}>
              <input
                type="checkbox"
                checked={draft.seeded_by_default}
                onChange={(e) => setDraft({ ...draft, seeded_by_default: e.target.checked })}
              />
              Auto-add to new projects (seeded by default)
            </label>
          </div>
        )}
      </div>
      )}
    </div>
  );
}
