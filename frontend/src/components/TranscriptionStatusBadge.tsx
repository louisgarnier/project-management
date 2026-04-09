"use client";

import { useEffect, useState } from "react";
import { transcriptionAPI } from "@/api/client";

export default function TranscriptionStatusBadge() {
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    const check = async () => setOnline(await transcriptionAPI.health());
    check();
    const interval = setInterval(check, 30_000);
    return () => clearInterval(interval);
  }, []);

  if (online === null) return null;

  return online ? (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#006644] bg-[#e3fcef] px-2 py-0.5 rounded-full">
      <span className="w-1.5 h-1.5 rounded-full bg-[#36b37e]" />
      Server online
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#974f0c] bg-[#fff4e6] px-2 py-0.5 rounded-full">
      <span className="w-1.5 h-1.5 rounded-full bg-[#ff8b00]" />
      Server offline
    </span>
  );
}
