"""EPIC-18 / S1.3 — Measure v5 pipeline drift on identical input.

Runs gold-set transcripts N times through Stages 2, 5, and 7 with the same
inputs each time. Reports drift metrics:

  - Stage 2: |unit_set_run_a ⊖ unit_set_run_b| / |unit_set_union|
  - Stage 5: % of units that ended up in a different cluster across runs
  - Stage 7: # of tasks per topic that differ in core fields (task text, owner)

Baseline measurement for STREAM 1 work — re-run after S1.1 (V5-CORE) ships
to validate delta.

Usage:
  python3 -m backend.scripts.measure_v5_drift --runs 3 \\
    --transcript "docs/project/config/gold set/arm_kickoff_05112026_numbered.txt"
"""

from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path

from backend.services.call_topics_v5.stage_0_ingest import ingest_transcript
from backend.services.call_topics_v5.stage_2_atomic import extract_atomic_units
from backend.services.call_topics_v5.stage_5_cluster import cluster_topics
from backend.services.call_topics_v5.stage_7_synthesis import synthesize_all_topics


async def run_pipeline_once(transcript: str, *, llm: str, model: str | None) -> dict:
    ingested = ingest_transcript(transcript)
    units = await extract_atomic_units(ingested, llm=llm, model=model)
    clusters_out = await cluster_topics(units.get("units", []), topic_registry=[], llm=llm, model=model)
    clusters = clusters_out.get("clusters", [])
    syn = await synthesize_all_topics(clusters, units.get("units", []), llm=llm, model=model)
    return {"units": units.get("units", []), "clusters": clusters, "synthesized": syn}


def measure_stage_2_drift(runs: list[dict]) -> dict:
    unit_sets = [set(u["unit_id"] for u in r["units"]) for r in runs]
    if len(unit_sets) < 2:
        return {"jaccard_drift_avg": 0.0, "n_units": [len(s) for s in unit_sets]}
    pairs = [(i, j) for i in range(len(unit_sets)) for j in range(i+1, len(unit_sets))]
    drifts = []
    for i, j in pairs:
        a, b = unit_sets[i], unit_sets[j]
        inter, union = a & b, a | b
        drifts.append(1.0 - (len(inter) / len(union) if union else 0.0))
    return {"jaccard_drift_avg": sum(drifts)/len(drifts), "n_units": [len(s) for s in unit_sets]}


def measure_stage_5_drift(runs: list[dict]) -> dict:
    """% of units assigned to a different cluster name across runs."""
    if len(runs) < 2:
        return {"reassignment_rate": 0.0}
    unit_to_clusters: dict[str, list[str]] = {}
    for r in runs:
        for c in r["clusters"]:
            for uid in c["unit_ids"]:
                unit_to_clusters.setdefault(uid, []).append(c["topic_name"])
    n_consistent = sum(1 for assignments in unit_to_clusters.values()
                      if len(set(assignments)) == 1 and len(assignments) == len(runs))
    n_total = len(unit_to_clusters)
    return {
        "reassignment_rate": 1 - (n_consistent / n_total if n_total else 0),
        "n_units_tracked": n_total,
    }


def measure_stage_7_drift(runs: list[dict]) -> dict:
    """How often does each topic synthesize the same task set?"""
    if len(runs) < 2:
        return {"task_set_drift": 0.0}
    by_topic: dict[str, list[set[str]]] = {}
    for r in runs:
        for s in r["synthesized"]:
            tname = s.get("topic_name") or "?"
            task_texts = {t.get("task","").strip().lower() for t in s.get("tasks",[])}
            by_topic.setdefault(tname, []).append(task_texts)
    drift_per_topic = []
    for tname, runs_tasks in by_topic.items():
        if len(runs_tasks) < 2:
            continue
        pairs = [(runs_tasks[i], runs_tasks[j])
                 for i in range(len(runs_tasks))
                 for j in range(i+1, len(runs_tasks))]
        for a, b in pairs:
            union = a | b
            inter = a & b
            drift_per_topic.append(1.0 - (len(inter)/len(union) if union else 0))
    return {"task_set_jaccard_drift_avg": (sum(drift_per_topic)/len(drift_per_topic)) if drift_per_topic else 0.0}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--llm", default="openrouter")
    ap.add_argument("--model", default="deepseek/deepseek-v3.2")
    args = ap.parse_args()

    transcript = Path(args.transcript).read_text()
    print(f"📥 [drift] Running {args.runs} iterations on {args.transcript}", flush=True)
    runs = []
    for i in range(args.runs):
        print(f"  → Run {i+1}/{args.runs}…", flush=True)
        runs.append(await run_pipeline_once(transcript, llm=args.llm, model=args.model))

    print("\n=== DRIFT BASELINE ===", flush=True)
    print(f"Stage 2 (atomic):    {json.dumps(measure_stage_2_drift(runs), indent=2)}")
    print(f"Stage 5 (cluster):   {json.dumps(measure_stage_5_drift(runs), indent=2)}")
    print(f"Stage 7 (synthesis): {json.dumps(measure_stage_7_drift(runs), indent=2)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
