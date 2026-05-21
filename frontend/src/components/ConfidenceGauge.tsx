"use client";

import type { VerifyNewResult } from "@/types";

type ConfidenceLevel = {
  pct: number;
  label: "High" | "Moderate" | "Low";
  color: string;
  bg: string;
  rationale: string[];
};

/** Computes a 0-100 confidence score from the existing Pass ① signals.
 *
 * Tuned so that:
 *   - Mechanical skip (no LLM call, 0 qualified) → 95%
 *   - LLM verdict with all checks passing → 85%+
 *   - LLM verdict with needs_manual_review → ≤ 50%
 *   - Sanity flag set → −15%
 *   - Partial verbatim citation pass → proportional multiplier
 */
export function computeConfidence(result: VerifyNewResult | undefined): ConfidenceLevel | null {
  if (!result) return null;

  const rationale: string[] = [];
  let base = 0;

  // ── Base score depending on the path taken ──
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mechanicalSkip = (result as any).mechanical_skip === true;
  if (mechanicalSkip) {
    base = 95;
    rationale.push("Mechanical pre-filter: 0 candidates qualified → no LLM call needed");
  } else if (result.needs_manual_review) {
    base = 40;
    rationale.push("LLM verdict flagged for manual review");
  } else if (result.verdict === "truly_new") {
    base = 85;
    rationale.push("LLM confirmed truly new with verified citations");
  } else if (result.verdict === "should_be_merged_with") {
    base = 85;
    rationale.push("LLM proposed merge with verified citations");
  } else {
    base = 60;
  }

  // ── Verbatim citation pass rate (only meaningful if citations exist) ──
  const verdictCits = (result.citations ?? []).filter(
    (c) => !c.for || c.for === "verdict",
  );
  if (verdictCits.length > 0) {
    const failedCount = (result.failed_citations ?? []).length;
    const verifiedCount = Math.max(verdictCits.length - failedCount, 0);
    const rate = verifiedCount / verdictCits.length;
    const multiplier = 0.7 + 0.3 * rate;  // 70-100% scaling
    base = base * multiplier;
    if (failedCount > 0) {
      rationale.push(
        `${verifiedCount} of ${verdictCits.length} citation(s) verified verbatim (${Math.round(rate * 100)}%)`,
      );
    } else {
      rationale.push(`All ${verdictCits.length} citation(s) verified verbatim`);
    }
  }

  // ── Sanity flag penalty ──
  if (result.sanity_flag) {
    base -= 15;
    rationale.push(`Sanity flag: ${result.sanity_flag.replaceAll("_", " ")}`);
  }

  // ── Pre-filter target score nudge ──
  if (result.verdict === "should_be_merged_with" && result.matched_topic_id && result.lexical_precheck) {
    const target = (result.lexical_precheck.scored_topics ?? []).find(
      (s) => s.topic_id === result.matched_topic_id,
    );
    if (target) {
      if (target.combined_score >= 0.5) {
        base += 5;
        rationale.push(`Strong mechanical signal for merge target (combined score ${target.combined_score})`);
      } else if (target.combined_score < 0.15) {
        base -= 10;
        rationale.push(`Weak mechanical signal for merge target (score ${target.combined_score} below threshold)`);
      }
    }
  }

  // ── Task-fit evaluations boost ──
  const evals = result.evaluations ?? [];
  const yesCount = evals.filter((e) => e.task_fit === "yes").length;
  if (yesCount > 0 && result.verdict === "should_be_merged_with") {
    base += 5;
    rationale.push(`${yesCount} task-fit evaluation(s) confirmed YES`);
  }

  // ── Clamp + label ──
  const pct = Math.max(0, Math.min(100, Math.round(base)));
  let label: "High" | "Moderate" | "Low";
  let color: string;
  let bg: string;
  if (pct >= 80) {
    label = "High";
    color = "#006644";
    bg = "#e3fcef";
  } else if (pct >= 50) {
    label = "Moderate";
    color = "#974f0c";
    bg = "#fff4e6";
  } else {
    label = "Low";
    color = "#ae2a19";
    bg = "#fff1f0";
  }

  return { pct, label, color, bg, rationale };
}


type Props = {
  result: VerifyNewResult | undefined;
};

export default function ConfidenceGauge({ result }: Props) {
  const conf = computeConfidence(result);
  if (!conf) return null;

  // Directional label: what is the % confidence FOR?
  let directional = "system recommendation";
  if (result?.verdict === "should_be_merged_with" && result.matched_topic_name) {
    directional = `merge with "${result.matched_topic_name}"`;
  } else if (result?.verdict === "truly_new") {
    directional = "truly new (no merge)";
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mechanicalSkip = (result as any)?.mechanical_skip === true;
  if (mechanicalSkip) {
    directional = "truly new (no merge — mechanical skip)";
  }

  return (
    <div
      style={{
        marginTop: 6,
        marginBottom: 8,
        padding: "6px 10px",
        background: conf.bg,
        border: `1px solid ${conf.color}40`,
        borderRadius: 4,
        fontSize: 11,
      }}
      title={conf.rationale.join("\n")}
    >
      <div style={{ fontSize: 10, color: conf.color, opacity: 0.9, marginBottom: 3 }}>
        Confidence in proposal: <strong>{directional}</strong>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontWeight: 700, color: conf.color, minWidth: 36 }}>
          {conf.pct}%
        </span>
        <div
          style={{
            flex: 1,
            height: 6,
            background: "white",
            borderRadius: 3,
            overflow: "hidden",
            border: `1px solid ${conf.color}30`,
          }}
        >
          <div
            style={{
              width: `${conf.pct}%`,
              height: "100%",
              background: conf.color,
              transition: "width .3s ease",
            }}
          />
        </div>
        <span style={{ fontWeight: 700, color: conf.color, fontSize: 10, textTransform: "uppercase", letterSpacing: ".04em" }}>
          {conf.label}
        </span>
      </div>
      <div style={{ marginTop: 3, color: conf.color, opacity: 0.85, fontSize: 10 }}>
        {conf.rationale.join(" · ")}
      </div>
      {conf.pct < 50 && (
        <div style={{ marginTop: 3, color: conf.color, fontSize: 10, fontWeight: 600 }}>
          → Strong signal to review/override manually
        </div>
      )}
    </div>
  );
}
