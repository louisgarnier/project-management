"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { callsAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call } from "@/types";
import KanbanBoard from "@/components/KanbanBoard";
import NewCallModal from "@/components/NewCallModal";

export default function BoardPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;

  const [calls, setCalls] = useState<Call[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [activeTab, setActiveTab] = useState<"kanban" | "topics">("kanban");

  const loadCalls = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      logger.info("Fetching calls", { component: "BoardPage", data: { projectId } });
      const data = await callsAPI.list(projectId);
      logger.info(`Loaded ${data.length} calls`, { component: "BoardPage" });
      setCalls(data);
    } catch (err) {
      logger.error("Failed to load calls", { component: "BoardPage", data: err });
      setError("Failed to load calls. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadCalls();
  }, [loadCalls]);

  async function handleCreate(title: string) {
    await callsAPI.create(projectId, { title });
    await loadCalls();
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-5 pt-4 pb-3 bg-white border-b border-[#dfe1e6] flex-shrink-0">
        <h1 className="text-[18px] font-bold text-[#172b4d]">Board</h1>
      </div>

      {/* Tabs */}
      <div className="flex px-5 bg-white border-b border-[#dfe1e6] flex-shrink-0">
        <button
          onClick={() => setActiveTab("kanban")}
          className={`px-4 py-[9px] text-[13px] font-medium border-b-2 -mb-px transition-colors ${
            activeTab === "kanban"
              ? "text-[#0052cc] border-[#0052cc]"
              : "text-[#5e6c84] border-transparent hover:text-[#172b4d]"
          }`}
        >
          Kanban
        </button>
        <button
          onClick={() => setActiveTab("topics")}
          className={`px-4 py-[9px] text-[13px] font-medium border-b-2 -mb-px transition-colors ${
            activeTab === "topics"
              ? "text-[#0052cc] border-[#0052cc]"
              : "text-[#5e6c84] border-transparent hover:text-[#172b4d]"
          }`}
        >
          Topics
        </button>
      </div>

      {/* Content */}
      {activeTab === "topics" ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-[13px] text-[#5e6c84]">Topics view coming soon.</p>
        </div>
      ) : loading ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-[13px] text-[#5e6c84]">Loading…</p>
        </div>
      ) : error ? (
        <div className="flex-1 flex items-center justify-center flex-col gap-3">
          <p className="text-[13px] text-red-600">{error}</p>
          <button onClick={loadCalls} className="text-[13px] text-[#0052cc] underline">
            Retry
          </button>
        </div>
      ) : (
        <KanbanBoard calls={calls} onNewCall={() => setShowModal(true)} />
      )}

      {showModal && <NewCallModal onClose={() => setShowModal(false)} onCreate={handleCreate} />}
    </div>
  );
}
