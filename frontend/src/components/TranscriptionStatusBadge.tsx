"use client";

import { useCallback, useEffect, useState } from "react";
import { localServerAPI } from "@/api/client";
import { logger } from "@/utils/logger";

type ServerState = "offline" | "starting" | "online" | "stopping";

export default function TranscriptionStatusBadge() {
  const [state, setState] = useState<ServerState | null>(null);

  const poll = useCallback(async () => {
    const status = await localServerAPI.status();
    if (status.running) {
      setState("online");
    } else if (status.starting) {
      setState("starting");
    } else {
      setState("offline");
    }
  }, []);

  useEffect(() => {
    poll();
    const interval = setInterval(poll, 5_000);
    return () => clearInterval(interval);
  }, [poll]);

  async function handleStart() {
    setState("starting");
    logger.info("Starting transcription server", { component: "TranscriptionStatusBadge" });
    try {
      await localServerAPI.start();
    } catch (err) {
      logger.error("Failed to start server", { component: "TranscriptionStatusBadge", data: err });
      setState("offline");
    }
  }

  async function handleStop() {
    setState("stopping");
    logger.info("Stopping transcription server", { component: "TranscriptionStatusBadge" });
    try {
      await localServerAPI.stop();
    } catch (err) {
      logger.error("Failed to stop server", { component: "TranscriptionStatusBadge", data: err });
      setState("online");
      return;
    }
    await poll();
  }

  if (state === null) return null;

  if (state === "online") {
    return (
      <div className="inline-flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#006644] bg-[#e3fcef] px-2 py-0.5 rounded-full">
          <span className="w-1.5 h-1.5 rounded-full bg-[#36b37e]" />
          Server online
        </span>
        <button
          onClick={handleStop}
          className="text-[11px] text-[#5e6c84] bg-[#f4f5f7] px-2 py-0.5 rounded hover:bg-[#dfe1e6]"
        >
          Stop
        </button>
      </div>
    );
  }

  if (state === "starting" || state === "stopping") {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#5e6c84] bg-[#f4f5f7] px-2 py-0.5 rounded-full">
        <span className="w-1.5 h-1.5 rounded-full bg-[#97a0af] animate-pulse" />
        {state === "starting" ? "Starting…" : "Stopping…"}
      </span>
    );
  }

  // offline
  return (
    <div className="inline-flex items-center gap-2">
      <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#974f0c] bg-[#fff4e6] px-2 py-0.5 rounded-full">
        <span className="w-1.5 h-1.5 rounded-full bg-[#ff8b00]" />
        Server offline
      </span>
      <button
        onClick={handleStart}
        className="text-[11px] text-white bg-[#0052cc] px-2 py-0.5 rounded hover:bg-[#0065ff]"
      >
        Start server
      </button>
    </div>
  );
}
