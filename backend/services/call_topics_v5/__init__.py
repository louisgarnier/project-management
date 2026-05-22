"""EPIC-17: call_topics v5 — 13-stage extraction pipeline.

Each Stage is a pure function (or LLM call) with a narrow cognitive purpose.
Deterministic code handles bookkeeping (citation resolution, validation,
confidence, registry). Orchestrator (see orchestrator.py) sequences the stages
and persists state in calls.call_topics_v5_*.

Reference: docs/project/config/calltopicsreview.md (PRD)
Plan:      docs/project/config/2026-05-22-call-topics-v5-pipeline-plan.md
Gold set:  docs/project/config/gold set/gold_set_v0.1.json
"""
