"use client";

import { useState } from "react";
import type { LibraryEntry } from "@/types";
import { libraryAPI } from "@/api/client";

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
  const [draft, setDraft] = useState<LibraryEntry>(entry);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const kindIcon = entry.kind === "template" ? "🔧" : entry.kind === "hybrid" ? "⚡" : "🤖";

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
    <div style={{ border: "1px solid #dfe1e6", borderRadius: 6, padding: 14, marginBottom: 10, background: "white" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {editing ? (
            <input
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              style={{ fontSize: 14, fontWeight: 600, color: "#172b4d", border: "1px solid #dfe1e6", borderRadius: 4, padding: "4px 6px", width: "100%", fontFamily: "inherit" }}
            />
          ) : (
            <div style={{ fontSize: 14, fontWeight: 600, color: "#172b4d" }}>
              {kindIcon} {entry.name}
            </div>
          )}
          <div style={{ fontSize: 11, color: "#5e6c84", marginTop: 2 }}>
            {entry.is_system ? "🏛 system" : "👤 yours"}
            {entry.seeded_by_default && <span style={{ marginLeft: 8 }}>🌱 seeded on new projects</span>}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          {editing ? (
            <>
              <button
                type="button"
                onClick={save}
                disabled={saving}
                style={{ fontSize: 11, fontWeight: 600, color: "white", background: "#0052cc", border: "none", borderRadius: 4, padding: "5px 10px", cursor: saving ? "default" : "pointer", opacity: saving ? 0.6 : 1 }}
              >
                {saving ? "Saving…" : "Save"}
              </button>
              <button
                type="button"
                onClick={() => { setDraft(entry); setEditing(false); setError(null); }}
                style={{ fontSize: 11, color: "#5e6c84", background: "none", border: "1px solid #dfe1e6", borderRadius: 4, padding: "5px 10px", cursor: "pointer" }}
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() => setEditing(true)}
                style={{ fontSize: 11, color: "#5e6c84", background: "none", border: "1px solid #dfe1e6", borderRadius: 4, padding: "5px 10px", cursor: "pointer" }}
              >
                Edit
              </button>
              {!entry.is_system && (
                <button
                  type="button"
                  onClick={del}
                  style={{ fontSize: 11, color: "#ae2a19", background: "none", border: "1px solid #ffbdad", borderRadius: 4, padding: "5px 10px", cursor: "pointer" }}
                >
                  Delete
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {editing ? (
        <div style={{ marginTop: 10 }}>
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
                value={draft.model || ""}
                onChange={(e) => setDraft({ ...draft, model: e.target.value })}
                placeholder="anthropic/claude-sonnet-4.6"
                style={{ fontSize: 12, border: "1px solid #dfe1e6", borderRadius: 4, padding: "4px 6px", fontFamily: "ui-monospace, Menlo, monospace", width: "100%", boxSizing: "border-box" }}
              />
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
      ) : (
        <div style={{ fontSize: 12, color: "#5e6c84", marginTop: 6 }}>
          {entry.description || <em>No description</em>}
        </div>
      )}
    </div>
  );
}
