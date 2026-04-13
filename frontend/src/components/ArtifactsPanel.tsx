"use client";

import { useCallback, useEffect, useState } from "react";
import { artifactTypesAPI, artifactsAPI } from "@/api/client";
import type { Artifact, ArtifactType } from "@/types";

type Props = {
  callId: string;
  projectId: string;
  defaultOpen?: boolean;
};

export default function ArtifactsPanel({ callId, projectId, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [types, setTypes] = useState<ArtifactType[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!open) return;
    setLoading(true);
    try {
      const [arts, artTypes] = await Promise.all([
        artifactsAPI.list(callId),
        artifactTypesAPI.list(projectId),
      ]);
      setArtifacts(arts);
      setTypes(artTypes);
    } finally {
      setLoading(false);
    }
  }, [open, callId, projectId]);

  useEffect(() => { load(); }, [load]);

  const doneArtifacts = artifacts.filter((a) => a.status === "done");
  const typesById = Object.fromEntries(types.map((t) => [t.id, t]));

  return (
    <div style={{ background: "white", border: "1px solid #dfe1e6", borderRadius: 8, marginBottom: 12 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "10px 14px", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}
      >
        <span style={{ fontSize: 12, fontWeight: 700, color: "#172b4d" }}>
          Artifacts {doneArtifacts.length > 0 && !loading ? `(${doneArtifacts.length})` : ""}
        </span>
        <span style={{ fontSize: 10, color: "#97a0af" }}>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div style={{ borderTop: "1px solid #f4f5f7", padding: "10px 14px" }}>
          {loading ? (
            <p style={{ fontSize: 12, color: "#5e6c84" }}>Loading…</p>
          ) : doneArtifacts.length === 0 ? (
            <p style={{ fontSize: 12, color: "#5e6c84" }}>No artifacts generated for this call.</p>
          ) : (
            doneArtifacts.map((a) => (
              <ArtifactRow key={a.id} artifact={a} name={typesById[a.artifact_type_id]?.name ?? "Artifact"} />
            ))
          )}
        </div>
      )}
    </div>
  );
}

function ArtifactRow({ artifact, name }: { artifact: Artifact; name: string }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div style={{ borderBottom: "1px solid #f4f5f7", paddingBottom: 8, marginBottom: 8 }}>
      <button
        onClick={() => setExpanded((e) => !e)}
        style={{ background: "none", border: "none", cursor: "pointer", padding: 0,
          fontSize: 12, fontWeight: 600, color: "#172b4d", display: "flex", alignItems: "center", gap: 6 }}
      >
        <span>{expanded ? "▼" : "▶"}</span>
        <span>{name}</span>
      </button>
      {expanded && artifact.content && (
        <pre style={{ marginTop: 8, fontSize: 11, color: "#344563", whiteSpace: "pre-wrap",
          background: "#f4f5f7", borderRadius: 4, padding: "8px 10px", lineHeight: 1.6 }}>
          {artifact.content}
        </pre>
      )}
    </div>
  );
}
