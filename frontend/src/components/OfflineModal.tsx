"use client";

import { useEffect } from "react";
import { transcriptionAPI } from "@/api/client";

interface Props {
  onDismiss: () => void;
}

export default function OfflineModal({ onDismiss }: Props) {
  useEffect(() => {
    const interval = setInterval(async () => {
      const online = await transcriptionAPI.health();
      if (online) onDismiss();
    }, 3_000);
    return () => clearInterval(interval);
  }, [onDismiss]);

  return (
    <div className="fixed inset-0 bg-[#09101e]/54 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-sm w-full mx-4 shadow-xl">
        <h2 className="text-[16px] font-bold text-[#172b4d] mb-1.5">
          ⚠️ Transcription server is offline
        </h2>
        <p className="text-[13px] text-[#5e6c84] mb-4 leading-relaxed">
          To transcribe MP3 files, start the local server on your machine.
        </p>

        <div className="flex flex-col gap-2.5 mb-5">
          <div className="flex gap-2.5 items-start">
            <span className="w-5 h-5 rounded-full bg-[#e9f0ff] text-[#0052cc] text-[11px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
              1
            </span>
            <span className="text-[13px] text-[#172b4d]">Open a terminal</span>
          </div>
          <div className="flex gap-2.5 items-start">
            <span className="w-5 h-5 rounded-full bg-[#e9f0ff] text-[#0052cc] text-[11px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
              2
            </span>
            <div className="text-[13px] text-[#172b4d]">
              Navigate to your Call Tracker folder:
              <br />
              <code className="font-mono text-[12px] bg-[#f4f5f7] px-1.5 py-0.5 rounded">
                cd ~/Claude/Project\ management
              </code>
            </div>
          </div>
          <div className="flex gap-2.5 items-start">
            <span className="w-5 h-5 rounded-full bg-[#e9f0ff] text-[#0052cc] text-[11px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
              3
            </span>
            <div className="text-[13px] text-[#172b4d]">
              Run the transcription server:
              <br />
              <code className="font-mono text-[12px] bg-[#f4f5f7] px-1.5 py-0.5 rounded">
                ./run_transcription.sh
              </code>
            </div>
          </div>
        </div>

        <p className="text-[11px] text-[#36b37e] mb-4">
          ✅ This dialog closes automatically when the server comes back online.
        </p>

        <div className="flex justify-end">
          <button
            onClick={onDismiss}
            className="text-[13px] text-[#5e6c84] bg-[#f4f5f7] px-3 py-1.5 rounded hover:bg-[#dfe1e6]"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
