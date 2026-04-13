"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { artifactTypesAPI, artifactsAPI } from "@/api/client";
import type { Artifact, ArtifactType, Call } from "@/types";

type Props = {
  callId: string;
  projectId: string;
  defaultOpen?: boolean;
  call?: Call; // when provided, enables regeneration (if not locked)
};

export default function ArtifactsPanel({ callId, projectId, defaultOpen = false, call }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [types, setTypes] = useState<ArtifactType[]>([]);
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const streamAbortRef = useRef<AbortController | null>(null);

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
  useEffect(() => { return () => { streamAbortRef.current?.abort(); }; }, []);

  const typesById = Object.fromEntries(types.map((t) => [t.id, t]));
  const canRegenerate = call && !call.is_locked;

  async function handleRegenerate(artifact: Artifact) {
    // Reset to pending then stream
    const updated = await artifactsAPI.update(artifact.id, { status: "pending" });
    setArtifacts((prev) => prev.map((a) => (a.id === artifact.id ? updated : a)));
    setStreaming(true);

    const controller = new AbortController();
    streamAbortRef.current = controller;

    try {
      const response = await fetch(`/api/sse/api/calls/${callId}/artifacts/stream`, {
        signal: controller.signal,
      });
      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6)) as {
              type: string;
              artifact_id?: string;
              status?: string;
              content?: string | null;
              message?: string | null;
            };
            if (event.type === "complete") break;
            setArtifacts((prev) =>
              prev.map((a) => {
                if (a.id !== event.artifact_id) return a;
                if (event.type === "status") return { ...a, status: (event.status ?? a.status) as Artifact["status"] };
                if (event.type === "done") return { ...a, status: "done", content: event.content ?? null };
                if (event.type === "error") return { ...a, status: "error", error_message: event.message ?? null };
                return a;
              })
            );
          } catch { /* malformed line */ }
        }
      }
    } catch (err: unknown) {
      if ((err as Error)?.name !== "AbortError") {
        console.error("SSE error", err);
      }
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div style={{ background: "white", border: "1px solid #dfe1e6", borderRadius: 8, marginBottom: 12 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "10px 14px", background: "none", border: "none", cursor: "pointer", textAlign: "left" }}
      >
        <span style={{ fontSize: 12, fontWeight: 700, color: "#172b4d" }}>
          Artifacts {artifacts.length > 0 && !loading ? `(${artifacts.length})` : ""}
        </span>
        <span style={{ fontSize: 10, color: "#97a0af" }}>{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div style={{ borderTop: "1px solid #f4f5f7", padding: "10px 14px" }}>
          {loading ? (
            <p style={{ fontSize: 12, color: "#5e6c84" }}>Loading…</p>
          ) : artifacts.length === 0 ? (
            <p style={{ fontSize: 12, color: "#5e6c84" }}>No artifacts generated for this call.</p>
          ) : (
            artifacts.map((a) => (
              <ArtifactRow
                key={a.id}
                artifact={a}
                name={typesById[a.artifact_type_id]?.name ?? "Artifact"}
                canRegenerate={!!canRegenerate && !streaming}
                onRegenerate={() => handleRegenerate(a)}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

function ArtifactRow({ artifact, name, canRegenerate, onRegenerate }: {
  artifact: Artifact;
  name: string;
  canRegenerate: boolean;
  onRegenerate: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  // status may be "stale" at runtime even if not in the TS union (backend can return it)
  const statusStr = artifact.status as string;
  const isStale = statusStr === "stale";
  const isPending = statusStr === "pending" || statusStr === "generating";

  return (
    <div style={{ borderBottom: "1px solid #f4f5f7", paddingBottom: 8, marginBottom: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button
          onClick={() => setExpanded((e) => !e)}
          style={{ background: "none", border: "none", cursor: "pointer", padding: 0,
            fontSize: 12, fontWeight: 600, color: "#172b4d", display: "flex", alignItems: "center", gap: 6, flex: 1 }}
        >
          <span>{expanded ? "▼" : "▶"}</span>
          <span>{name}</span>
        </button>
        {isStale && (
          <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
            background: "#fff4e6", color: "#974f0c", padding: "2px 6px", borderRadius: 3 }}>
            stale
          </span>
        )}
        {isPending && (
          <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase",
            background: "#e9f0ff", color: "#0052cc", padding: "2px 6px", borderRadius: 3 }}>
            {artifact.status}
          </span>
        )}
        {canRegenerate && (
          <button
            onClick={onRegenerate}
            disabled={isPending}
            style={{ fontSize: 10, color: "#0052cc", background: "none",
              border: "1px solid #b3c6e8", borderRadius: 4, padding: "2px 8px",
              cursor: isPending ? "not-allowed" : "pointer", opacity: isPending ? 0.5 : 1 }}
          >
            ↻ Regenerate
          </button>
        )}
      </div>
      {expanded && artifact.content && (
        <pre style={{ marginTop: 8, fontSize: 11, color: "#344563", whiteSpace: "pre-wrap",
          background: "#f4f5f7", borderRadius: 4, padding: "8px 10px", lineHeight: 1.6 }}>
          {artifact.content}
        </pre>
      )}
    </div>
  );
}
