import type { ArtifactCategory, LLMProvider } from "@/types";

export type ModelTier = "best" | "strong" | "balanced" | "budget" | "fallback";

export interface ModelRecommendation {
  slug: string;
  tier: ModelTier;
  label: string;
  priceHint?: string;
}

/**
 * Curated per-category model recommendations for the OpenRouter picker.
 * This is a frontend UI affordance — backend does not validate against this list.
 * Users can always enter a custom slug.
 *
 * Convention: every category surfaces deepseek/deepseek-v3.2 (cheap default) and
 * anthropic/claude-sonnet-4.6 (premium quality) as the top two picks so they're
 * always one click away. Other options follow.
 */
const _TOP_PICKS: ModelRecommendation[] = [
  { slug: "deepseek/deepseek-v3.2",      tier: "budget", label: "Default · cheap & capable", priceHint: "$0.27 / $1.10" },
  { slug: "anthropic/claude-sonnet-4.6", tier: "best",   label: "Premium · highest quality", priceHint: "$3 / $15" },
];

export const MODEL_RECOMMENDATIONS: Record<ArtifactCategory, ModelRecommendation[]> = {
  call_topics: [
    ..._TOP_PICKS,
    { slug: "openai/gpt-4o",                      tier: "strong",   label: "Strong alt",   priceHint: "$2.5 / $10" },
    { slug: "google/gemini-2.5-pro",              tier: "balanced", label: "Long context", priceHint: "$1.25 / $5" },
    { slug: "meta-llama/llama-3.3-70b-instruct",  tier: "fallback", label: "Fallback" },
  ],
  artifacts: [
    ..._TOP_PICKS,
    { slug: "openai/gpt-4o",         tier: "strong",   label: "Strong alt",   priceHint: "$2.5 / $10" },
    { slug: "google/gemini-2.5-pro", tier: "balanced", label: "Long context", priceHint: "$1.25 / $5" },
  ],
  merge_verification: [
    ..._TOP_PICKS,
    { slug: "openai/gpt-4o",         tier: "strong",   label: "Strong alt" },
    { slug: "google/gemini-2.5-pro", tier: "balanced", label: "Balanced" },
  ],
  not_discussed_check: [
    ..._TOP_PICKS,
    { slug: "google/gemini-2.5-pro", tier: "balanced", label: "Long context" },
    { slug: "openai/gpt-4o-mini",    tier: "fallback", label: "Tiny + cheap" },
  ],
  project_topics: [..._TOP_PICKS],
  topics:         [..._TOP_PICKS],
};

export const PROVIDER_LABELS: Record<LLMProvider | "inherit", string> = {
  inherit:    "Inherit project",
  groq:       "Groq (direct)",
  deepseek:   "DeepSeek (direct)",
  claude:     "Claude (direct)",
  openai:     "OpenAI (direct)",
  openrouter: "OpenRouter ⭐",
};

export const MODEL_COSTS: Record<string, { inputPerMillion: number; outputPerMillion: number }> = {
  "anthropic/claude-sonnet-4.6":       { inputPerMillion: 3,    outputPerMillion: 15  },
  "anthropic/claude-opus-4.7":          { inputPerMillion: 15,   outputPerMillion: 75  },
  "openai/gpt-4o":                      { inputPerMillion: 2.5,  outputPerMillion: 10  },
  "openai/gpt-4o-mini":                 { inputPerMillion: 0.15, outputPerMillion: 0.60 },
  "google/gemini-2.5-pro":              { inputPerMillion: 1.25, outputPerMillion: 5   },
  "deepseek/deepseek-chat":             { inputPerMillion: 0.27, outputPerMillion: 1.10 },
  "deepseek/deepseek-v3.2":             { inputPerMillion: 0.27, outputPerMillion: 1.10 },
  "meta-llama/llama-3.3-70b-instruct":  { inputPerMillion: 0.59, outputPerMillion: 0.79 },
};

/** Estimates the per-call cost for an LLM artifact assuming ~12k input + ~4k output tokens. */
export function estimateCost(modelSlug: string | null | undefined): string {
  if (!modelSlug) return "—";
  const rates = MODEL_COSTS[modelSlug];
  if (!rates) return "—";
  const cost = (12_000 / 1_000_000) * rates.inputPerMillion + (4_000 / 1_000_000) * rates.outputPerMillion;
  return `~$${cost.toFixed(3)}`;
}
