"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { artifactTypesAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { ArtifactType } from "@/types";
import ArtifactTypeCard from "@/components/ArtifactTypeCard";
import AddArtifactTypeModal from "@/components/AddArtifactTypeModal";

export default function ArtifactsPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;

  const [types, setTypes] = useState<ArtifactType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      logger.info("Fetching artifact types", { component: "ArtifactsPage", data: { projectId } });
      const data = await artifactTypesAPI.list(projectId);
      setTypes(data);
    } catch (err) {
      logger.error("Failed to load artifact types", { component: "ArtifactsPage", data: err });
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

  async function handleUpdate(typeId: string, data: { name?: string; prompt?: string }) {
    const updated = await artifactTypesAPI.update(projectId, typeId, data);
    setTypes((prev) => prev.map((t) => (t.id === typeId ? updated : t)));
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-5 pt-4 pb-3 bg-white border-b border-[#dfe1e6] flex-shrink-0">
        <h1 className="text-[18px] font-bold text-[#172b4d]">Artifact Types</h1>
        <button
          onClick={() => setShowModal(true)}
          className="bg-[#0052cc] text-white px-4 py-[6px] rounded text-[13px] font-medium hover:bg-[#0065ff]"
        >
          + Add artifact type
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        {loading ? (
          <p className="text-[13px] text-[#5e6c84]">Loading…</p>
        ) : error ? (
          <div className="flex flex-col items-center gap-3 py-12">
            <p className="text-[13px] text-red-600">{error}</p>
            <button onClick={load} className="text-[13px] text-[#0052cc] underline">Retry</button>
          </div>
        ) : types.length === 0 ? (
          <p className="text-[13px] text-[#5e6c84]">No artifact types yet.</p>
        ) : (
          <div className="flex flex-col gap-3">
            {types.map((t) => (
              <ArtifactTypeCard
                key={t.id}
                type={t}
                onDelete={handleDelete}
                onUpdate={handleUpdate}
              />
            ))}
          </div>
        )}
      </div>

      {showModal && (
        <AddArtifactTypeModal
          projectId={projectId}
          onClose={() => setShowModal(false)}
          onCreated={(t) => setTypes((prev) => [...prev, t])}
          onImported={(ts) => setTypes((prev) => [...prev, ...ts])}
        />
      )}
    </div>
  );
}
