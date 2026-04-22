"use client";

import type { ArtifactType, LLMProvider } from "@/types";

// SelectionMode: "generate" uses the LLM configured on the artifact type (or project default)
export type SelectionMode = "generate" | "manual" | "skip";

const LLM_LABEL: Record<string, string> = {
  groq:       "Groq – Llama 3.3 (free)",
  deepseek:   "DeepSeek Chat (~free)",
  claude:     "Claude Haiku",
  openai:     "GPT-4o mini",
  openrouter: "OpenRouter",
};

type Props = {
  artifactTypes: ArtifactType[];
  selections: Record<string, SelectionMode>;
  projectDefaultLlm: LLMProvider;
  projectDefaultModel?: string | null;
  onChange: (typeId: string, mode: SelectionMode) => void;
};

export default function ArtifactSelector({
  artifactTypes,
  selections,
  projectDefaultLlm,
  projectDefaultModel,
  onChange,
}: Props) {
  return (
    <div className="flex flex-col gap-2">
      {artifactTypes.map((t) => {
        const sel = selections[t.id] ?? "generate";
        const effectiveLlm = t.llm ?? projectDefaultLlm;
        const effectiveModel = t.llm === "openrouter"
          ? t.model
          : (effectiveLlm === "openrouter" ? (projectDefaultModel ?? null) : null);
        const baseLlmLabel = LLM_LABEL[effectiveLlm] ?? "Groq (free)";
        const llmLabel = effectiveModel ? `${baseLlmLabel} · ${effectiveModel}` : baseLlmLabel;

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
