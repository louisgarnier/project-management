"use client";

import type { ArtifactType } from "@/types";

export type ArtifactMode = "claude" | "manual" | "skip";

type Props = {
  artifactTypes: ArtifactType[];
  selections: Record<string, ArtifactMode>;
  onChange: (typeId: string, mode: ArtifactMode) => void;
};

const MODES: { value: ArtifactMode; label: string }[] = [
  { value: "claude", label: "Generate via Claude" },
  { value: "manual", label: "Manual" },
  { value: "skip", label: "Skip" },
];

export default function ArtifactSelector({ artifactTypes, selections, onChange }: Props) {
  return (
    <div className="flex flex-col gap-2">
      {artifactTypes.map((t) => {
        const selected = selections[t.id] ?? "claude";
        return (
          <div
            key={t.id}
            className="flex items-center justify-between gap-4 px-4 py-3 border border-[#dfe1e6] rounded-lg bg-white"
          >
            <span className="text-[13px] font-medium text-[#172b4d] flex-1 min-w-0 truncate">
              {t.name}
            </span>
            <div className="flex gap-1 flex-shrink-0">
              {MODES.map((m) => (
                <button
                  key={m.value}
                  onClick={() => onChange(t.id, m.value)}
                  className={`px-3 py-1.5 text-[11px] font-medium rounded transition-colors ${
                    selected === m.value
                      ? m.value === "skip"
                        ? "bg-[#f4f5f7] text-[#5e6c84] border border-[#97a0af]"
                        : "bg-[#e9f0ff] text-[#0052cc] border border-[#0052cc]"
                      : "bg-white text-[#5e6c84] border border-[#dfe1e6] hover:bg-[#f4f5f7]"
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
