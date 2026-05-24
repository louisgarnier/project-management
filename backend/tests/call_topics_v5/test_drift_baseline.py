"""EPIC-18 / S1.3 — Tests for drift measurement helpers (no LLM)."""
from backend.scripts.measure_v5_drift import (
    measure_stage_2_drift, measure_stage_5_drift, measure_stage_7_drift,
)


def test_stage_2_drift_zero_when_identical():
    runs = [{"units": [{"unit_id":"u1"}, {"unit_id":"u2"}]} for _ in range(3)]
    out = measure_stage_2_drift(runs)
    assert out["jaccard_drift_avg"] == 0.0


def test_stage_2_drift_full_when_disjoint():
    runs = [
        {"units": [{"unit_id":"u1"}, {"unit_id":"u2"}]},
        {"units": [{"unit_id":"u3"}, {"unit_id":"u4"}]},
    ]
    out = measure_stage_2_drift(runs)
    assert out["jaccard_drift_avg"] == 1.0


def test_stage_5_drift_zero_when_consistent_assignment():
    runs = [
        {"clusters": [{"topic_name": "A", "unit_ids": ["u1","u2"]}]} for _ in range(3)
    ]
    out = measure_stage_5_drift(runs)
    assert out["reassignment_rate"] == 0.0


def test_stage_5_drift_nonzero_when_reassigned():
    runs = [
        {"clusters": [{"topic_name": "A", "unit_ids": ["u1"]}, {"topic_name": "B", "unit_ids": ["u2"]}]},
        {"clusters": [{"topic_name": "A", "unit_ids": ["u1","u2"]}]},
    ]
    out = measure_stage_5_drift(runs)
    assert out["reassignment_rate"] > 0


def test_stage_7_drift_zero_when_tasks_match():
    runs = [
        {"synthesized": [{"topic_name": "A", "tasks": [{"task": "x"}, {"task": "y"}]}]} for _ in range(3)
    ]
    out = measure_stage_7_drift(runs)
    assert out["task_set_jaccard_drift_avg"] == 0.0
