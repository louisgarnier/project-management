"use client";

import type { ArtifactType, LLMProvider } from "@/types";

// SelectionMode: "generate" uses the LLM configured on the artifact type (or project default)
export type SelectionMode = "generate" | "manual" | "skip";

const LLM_LABEL: Record<string, string> = {
  groq: "Groq (free)",
  claude: "Claude",
  openai: "ChatGPT",
};

type Props = {
  artifactTypes: ArtifactType[];
  selections: Record<string, SelectionMode>;
  projectDefaultLlm: LLMProvider;
  onChange: (typeId: string, mode: SelectionMode) => void;
};

export default function ArtifactSelector({
  artifactTypes,
  selections,
  projectDefaultLlm,
  onChange,
}: Props) {
  return (
    <div className="flex flex-col gap-2">
      {artifactTypes.map((t) => {
        const sel = selections[t.id] ?? "generate";
        const llmLabel = LLM_LABEL[t.llm ?? projectDefaultLlm] ?? "Groq (free)";

        return (
          <div
            key={t.id}
            className="flex items-center justify-between gap-3 px-4 py-3 border border-[#dfe1e6] rounded-lg bg-white"
          >
            <div className="flex flex-col flex-1 min-w-0">
              <span className="text-[13px] font-medium text-[#172b4d] truncate">{t.name}</span>
              {sel === "generate" && (
                <span className="text-[11px] text-[#97a0af] mt-0.5">{llmLabel}</span>
              )}
            </div>

            <div className="flex gap-1 flex-shrink-0">
              {(["generate", "manual", "skip"] as const).map((btn) => (
                <button
                  key={btn}
                  onClick={() => onChange(t.id, btn)}
                  className={`px-3 py-1.5 text-[11px] font-medium rounded transition-colors capitalize ${
                    sel === btn
                      ? btn === "skip"
                        ? "bg-[#f4f5f7] text-[#5e6c84] border border-[#97a0af]"
                        : "bg-[#e9f0ff] text-[#0052cc] border border-[#0052cc]"
                      : "bg-white text-[#5e6c84] border border-[#dfe1e6] hover:bg-[#f4f5f7]"
                  }`}
                >
                  {btn}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
