"""Stage 13 evaluation harness — runs the v5 pipeline against the gold set
and reports the 7 metrics defined in gold_set_v0.1.json::evaluation_criteria.

Phase 1 status: the pipeline stages 2-12 are not yet built. This harness runs
Stage 0 (ingestion) successfully and reports the metrics it CAN compute with
that data (citation_validity = trivial 1.0 with empty output, no_hallucination
= trivial 1.0). Subsequent phases will plug into the pipeline_runner callable.

Usage:
    python -m backend.evaluation.evaluate                # all entries, default gold set
    python -m backend.evaluation.evaluate --output report.json
    python -m backend.evaluation.evaluate --transcript-id arm_kickoff_05112026
"""

from __future__ import annotations

import argparse
import json
import sys
from functools import partial
from pathlib import Path

from backend.evaluation import metrics as M
from backend.evaluation.gold_set_loader import load_gold_set
from backend.services.call_topics_v5.stage_0_ingest import ingest_transcript, resolve_lines


def run_placeholder_pipeline(raw_transcript: str) -> list[dict]:
    """Phase 1 placeholder: returns an empty topic list.

    Will be replaced by the real orchestrator once Stages 2-12 are built.
    Returning [] lets us validate the harness wiring (loading + metric
    computation) without LLM dependencies.
    """
    return []


def evaluate_entry(entry, *, n_stability_runs: int = 1) -> dict:
    """Evaluate one gold set entry and return a per-metric report."""
    ingest = ingest_transcript(entry["raw_text"])
    lookup = partial(resolve_lines, ingest)

    # Run the (placeholder) pipeline once for the per-run metrics
    pipeline_output = run_placeholder_pipeline(entry["raw_text"])

    expected = entry["expected_topics"]
    excluded = entry["topics_explicitly_excluded"]

    # Naming stability — run N times, see if results are identical
    stability_runs = [pipeline_output for _ in range(n_stability_runs)]

    report = {
        "transcript_id": entry["transcript_id"],
        "line_count": ingest["line_count"],
        "expected_topics_count": len(expected),
        "extracted_topics_count": len(pipeline_output),
        "pipeline": "placeholder (Phase 1)",
        "metrics": {
            "topic_recall": M.topic_recall(pipeline_output, expected),
            "topic_precision": M.topic_precision(pipeline_output, expected, excluded),
            "task_recall": M.task_recall(pipeline_output, expected),
            "citation_validity": M.citation_validity(pipeline_output, lookup),
            "citation_coverage": M.citation_coverage(pipeline_output, expected),
            "naming_stability": M.naming_stability(stability_runs),
            "no_hallucination": M.no_hallucination(pipeline_output, excluded),
        },
    }
    return report


def aggregate_must_pass(reports: list[dict]) -> bool:
    """All must-pass metrics across all transcripts pass?"""
    must_pass_metrics = ("citation_validity", "naming_stability", "no_hallucination")
    for r in reports:
        for m in must_pass_metrics:
            if not r["metrics"][m]["pass_"]:
                return False
    return True


def render_pretty(reports: list[dict]) -> str:
    """Compact textual report. ANSI colors when stdout is a TTY."""
    is_tty = sys.stdout.isatty()
    def c(code, s):
        return f"\033[{code}m{s}\033[0m" if is_tty else s

    out = []
    for r in reports:
        out.append("")
        out.append(c("1;36", f"━━ {r['transcript_id']} ({r['line_count']} lines, {r['pipeline']}) ━━"))
        out.append(f"  expected topics: {r['expected_topics_count']} · extracted: {r['extracted_topics_count']}")
        out.append("")
        for name, m in r["metrics"].items():
            ok = m.get("pass_", False)
            mark = c("32", "✓") if ok else c("31", "✗")
            target = m.get("target", "")
            score = m.get("score", 0.0)
            line = f"  {mark} {name:<22} score={score:.3f}  target {target}"
            out.append(line)
    out.append("")
    overall = aggregate_must_pass(reports)
    summary = (c("32", "ALL MUST-PASS METRICS GREEN") if overall else c("31", "MUST-PASS FAILURE"))
    out.append(summary)
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 13 evaluation harness")
    parser.add_argument("--gold-set", default="v0.1", help="gold set version (default v0.1)")
    parser.add_argument("--transcript-id", default=None, help="filter to a single transcript_id")
    parser.add_argument("--output", default=None, help="write JSON report to this path")
    parser.add_argument("--stability-runs", type=int, default=1, help="how many runs for naming_stability (default 1)")
    args = parser.parse_args()

    gs = load_gold_set(args.gold_set)
    entries = gs["entries"]
    if args.transcript_id:
        entries = [e for e in entries if e["transcript_id"] == args.transcript_id]
        if not entries:
            print(f"no transcript matching {args.transcript_id!r}", file=sys.stderr)
            return 2

    reports = [evaluate_entry(e, n_stability_runs=args.stability_runs) for e in entries]

    print(render_pretty(reports))

    if args.output:
        Path(args.output).write_text(json.dumps({
            "gold_set_version": gs["version"],
            "reports": reports,
            "must_pass_passing": aggregate_must_pass(reports),
        }, indent=2), encoding="utf-8")
        print(f"\nJSON report → {args.output}")

    return 0 if aggregate_must_pass(reports) else 1


if __name__ == "__main__":
    sys.exit(main())
