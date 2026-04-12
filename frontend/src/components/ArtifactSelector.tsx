"use client";

import type { ArtifactType, LLMProvider } from "@/types";

// SelectionMode: the LLM provider means "generate with this LLM"; "manual" and "skip" are special
export type SelectionMode = LLMProvider | "manual" | "skip";

const LLM_OPTIONS: { value: LLMProvider; label: string }[] = [
  { value: "groq", label: "Groq (free)" },
  { value: "claude", label: "Claude" },
  { value: "openai", label: "ChatGPT" },
];

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
        const sel = selections[t.id] ?? t.llm ?? projectDefaultLlm;
        const isGenerate = sel !== "manual" && sel !== "skip";
        const activeLlm: LLMProvider = isGenerate ? (sel as LLMProvider) : (t.llm ?? projectDefaultLlm);

        return (
          <div
            key={t.id}
            className="flex items-center justify-between gap-3 px-4 py-3 border border-[#dfe1e6] rounded-lg bg-white"
          >
            <span className="text-[13px] font-medium text-[#172b4d] flex-1 min-w-0 truncate">
              {t.name}
            </span>

            {/* Generate / Manual / Skip toggles */}
            <div className="flex gap-1 flex-shrink-0">
              {(["generate", "manual", "skip"] as const).map((btn) => {
                const active =
                  btn === "generate" ? isGenerate : sel === btn;
                return (
                  <button
                    key={btn}
                    onClick={() => {
                      if (btn === "generate") onChange(t.id, activeLlm);
                      else onChange(t.id, btn);
                    }}
                    className={`px-3 py-1.5 text-[11px] font-medium rounded transition-colors capitalize ${
                      active
                        ? btn === "skip"
                          ? "bg-[#f4f5f7] text-[#5e6c84] border border-[#97a0af]"
                          : "bg-[#e9f0ff] text-[#0052cc] border border-[#0052cc]"
                        : "bg-white text-[#5e6c84] border border-[#dfe1e6] hover:bg-[#f4f5f7]"
                    }`}
                  >
                    {btn}
                  </button>
                );
              })}
            </div>

            {/* LLM dropdown — only when Generate is active */}
            {isGenerate && (
              <select
                value={activeLlm}
                onChange={(e) => onChange(t.id, e.target.value as LLMProvider)}
                className="text-[11px] border border-[#dfe1e6] rounded px-2 py-1.5 bg-white text-[#172b4d] focus:outline-none focus:border-[#0052cc] flex-shrink-0"
              >
                {LLM_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            )}
          </div>
        );
      })}
    </div>
  );
}
