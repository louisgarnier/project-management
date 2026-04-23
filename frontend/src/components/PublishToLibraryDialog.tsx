"use client";

import { useState } from "react";
import type { ArtifactType } from "@/types";
import { artifactTypesAPI } from "@/api/client";

export default function PublishToLibraryDialog({
  type,
  open,
  onClose,
  onPublished,
}: {
  type: ArtifactType;
  open: boolean;
  onClose: () => void;
  onPublished: () => void;
}) {
  const [name, setName] = useState(type.name);
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await artifactTypesAPI.publishToLibrary(type.id, { name, description });
      onPublished();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(9,30,66,.54)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
      <form onSubmit={handleSubmit} style={{ background: "white", borderRadius: 8, padding: 20, width: 480, maxWidth: "92vw" }}>
        <h3 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", margin: "0 0 12px" }}>Publish to Library</h3>
        <p style={{ fontSize: 12, color: "#5e6c84", margin: "0 0 14px" }}>
          Copies this artifact type&apos;s prompt + model into the shared library. Other projects will be able to add a copy of it.
        </p>

        <label style={{ fontSize: 11, color: "#5e6c84", display: "block", marginBottom: 3 }}>Name</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          style={{ width: "100%", fontSize: 12, border: "1px solid #dfe1e6", borderRadius: 4, padding: "5px 8px", marginBottom: 10, boxSizing: "border-box", fontFamily: "inherit" }}
          required
        />

        <label style={{ fontSize: 11, color: "#5e6c84", display: "block", marginBottom: 3 }}>Description</label>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="One-line description of what this artifact produces"
          style={{ width: "100%", fontSize: 12, border: "1px solid #dfe1e6", borderRadius: 4, padding: "5px 8px", marginBottom: 14, boxSizing: "border-box", fontFamily: "inherit" }}
        />

        {error && (
          <div style={{ background: "#fff1f0", border: "1px solid #ffbdad", borderRadius: 4, padding: "6px 10px", fontSize: 11, color: "#ae2a19", marginBottom: 10 }}>
            {error}
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" onClick={onClose} style={{ fontSize: 12, color: "#5e6c84", background: "none", border: "1px solid #dfe1e6", borderRadius: 4, padding: "6px 14px", cursor: "pointer" }}>
            Cancel
          </button>
          <button type="submit" disabled={submitting} style={{ fontSize: 12, fontWeight: 600, color: "white", background: "#0052cc", border: "none", borderRadius: 4, padding: "6px 14px", cursor: submitting ? "default" : "pointer", opacity: submitting ? 0.6 : 1 }}>
            {submitting ? "Publishing…" : "Publish"}
          </button>
        </div>
      </form>
    </div>
  );
}
