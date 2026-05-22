"""EPIC-17 Stage 13 — evaluation harness for call_topics v5 pipeline.

Runs the pipeline against the gold set (docs/project/config/gold set/) and
computes the 7 metrics defined in gold_set_v0.1.json::evaluation_criteria.

Usage:
    python -m backend.evaluation.evaluate --gold-set v0.1 --output report.json
"""
