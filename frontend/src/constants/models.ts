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
 */
export const MODEL_RECOMMENDATIONS: Record<ArtifactCategory, ModelRecommendation[]> = {
  call_topics: [
    { slug: "anthropic/claude-sonnet-4.6",       tier: "best",     label: "Best quality · default", priceHint: "$3 / $15 per 1M tok" },
    { slug: "openai/gpt-4o",                      tier: "strong",   label: "Strong alt",             priceHint: "$2.5 / $10" },
    { slug: "google/gemini-2.5-pro",              tier: "balanced", label: "Long context",           priceHint: "$1.25 / $5" },
    { slug: "deepseek/deepseek-chat",             tier: "budget",   label: "Budget",                 priceHint: "$0.27 / $1.10" },
    { slug: "meta-llama/llama-3.3-70b-instruct",  tier: "fallback", label: "Fallback" },
  ],
  artifacts: [
    { slug: "anthropic/claude-sonnet-4.6", tier: "best",     label: "Best quality · default", priceHint: "$3 / $15 per 1M tok" },
    { slug: "openai/gpt-4o",               tier: "strong",   label: "Strong alt",             priceHint: "$2.5 / $10" },
    { slug: "google/gemini-2.5-pro",       tier: "balanced", label: "Long context",           priceHint: "$1.25 / $5" },
    { slug: "deepseek/deepseek-chat",      tier: "budget",   label: "Budget",                 priceHint: "$0.27 / $1.10" },
  ],
  merge_verification: [
    { slug: "anthropic/claude-sonnet-4.6", tier: "best",     label: "Best quality · default" },
    { slug: "openai/gpt-4o",               tier: "strong",   label: "Strong alt" },
    { slug: "google/gemini-2.5-pro",       tier: "balanced", label: "Balanced" },
  ],
  not_discussed_check: [
    { slug: "google/gemini-2.5-pro", tier: "best",   label: "Best — long context, default" },
    { slug: "openai/gpt-4o-mini",    tier: "strong",  label: "Strong alt" },
    { slug: "deepseek/deepseek-chat", tier: "budget", label: "Budget" },
  ],
  topics: [],
  project_topics: [],
};

export const PROVIDER_LABELS: Record<LLMProvider | "inherit", string> = {
  inherit:    "Inherit project",
  groq:       "Groq (direct)",
  deepseek:   "DeepSeek (direct)",
  claude:     "Claude (direct)",
  openai:     "OpenAI (direct)",
  openrouter: "OpenRouter ⭐",
};
