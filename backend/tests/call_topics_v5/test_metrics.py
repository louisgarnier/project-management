"""Tests for backend/evaluation/metrics.py (Stage 13 metric helpers)."""

import pytest

from backend.evaluation import metrics as M


# ── topic_recall ───────────────────────────────────────────────────────────


def test_topic_recall_full_match():
    pipeline = [{"topic_name": "Stress Testing"}, {"topic_name": "ARM"}]
    expected = [{"topic_name": "Stress Testing"}, {"topic_name": "ARM"}]
    out = M.topic_recall(pipeline, expected)
    assert out["score"] == 1.0
    assert out["pass_"] is True


def test_topic_recall_partial_match():
    pipeline = [{"topic_name": "Stress Testing"}]
    expected = [{"topic_name": "Stress Testing"}, {"topic_name": "ARM"}]
    out = M.topic_recall(pipeline, expected)
    assert out["score"] == 0.5
    assert out["pass_"] is False


def test_topic_recall_close_semantic_match():
    """Fuzzy match: 'Stress Test PA Readiness' matches expected 'Stress Testing PA' via token Jaccard."""
    pipeline = [{"topic_name": "Stress Test PA Readiness"}]
    expected = [{"topic_name": "Stress Testing PA"}]
    out = M.topic_recall(pipeline, expected)
    assert out["score"] == 1.0


def test_topic_recall_empty_expected():
    """No expected topics → trivially passes."""
    out = M.topic_recall([], [])
    assert out["score"] == 1.0


# ── topic_precision ────────────────────────────────────────────────────────


def test_topic_precision_clean():
    pipeline = [{"topic_name": "Stress Testing"}]
    expected = [{"topic_name": "Stress Testing"}]
    excluded = []
    out = M.topic_precision(pipeline, expected, excluded)
    assert out["score"] == 1.0


def test_topic_precision_hallucinated_counted_as_false_positive():
    pipeline = [{"topic_name": "Confirm FactSet region strategy"}, {"topic_name": "Stress Testing"}]
    expected = [{"topic_name": "Stress Testing"}]
    excluded = [{"topic": "Confirm FactSet region strategy"}]
    out = M.topic_precision(pipeline, expected, excluded)
    assert out["score"] == 0.5  # 1 valid out of 2 extracted
    assert "Confirm FactSet region strategy" in out["details"]["hallucinated"]


# ── task_recall ────────────────────────────────────────────────────────────


def test_task_recall_keyword_match():
    pipeline = [{
        "topic_name": "ARM",
        "tasks": [
            {"task": "Send current account hierarchy for FactSet to load", "next_step": ""},
        ],
    }]
    expected = [{
        "topic_name": "ARM",
        "expected_tasks": [
            {"must_have_keywords": ["hierarchy", "FactSet"]},
        ],
    }]
    out = M.task_recall(pipeline, expected)
    assert out["score"] == 1.0


def test_task_recall_missing_keyword():
    pipeline = [{
        "topic_name": "ARM",
        "tasks": [{"task": "Send something else", "next_step": ""}],
    }]
    expected = [{
        "topic_name": "ARM",
        "expected_tasks": [{"must_have_keywords": ["hierarchy", "FactSet"]}],
    }]
    out = M.task_recall(pipeline, expected)
    assert out["score"] == 0.0


# ── no_hallucination ───────────────────────────────────────────────────────


def test_no_hallucination_clean():
    pipeline = [{"topic_name": "Stress Testing"}]
    excluded = [{"topic": "Some other unrelated topic"}]
    out = M.no_hallucination(pipeline, excluded)
    assert out["pass_"] is True


def test_no_hallucination_fails_on_excluded_match():
    pipeline = [{"topic_name": "Monte Carlo Mac memory failure"}]
    excluded = [{"topic": "Monte Carlo Mac memory failure (Closed)"}]
    out = M.no_hallucination(pipeline, excluded)
    assert out["pass_"] is False
    assert "Monte Carlo Mac memory failure" in out["details"]["hallucinated"]


# ── citation_validity ─────────────────────────────────────────────────────


def test_citation_validity_byte_identical():
    pipeline = [{
        "topic_name": "X",
        "tasks": [{
            "task": "y",
            "citations": [{"quote": "Hello world", "lines": "0001-0001"}],
        }],
    }]
    def lookup(a, b):
        assert a == "0001" and b == "0001"
        return "Hello world"
    out = M.citation_validity(pipeline, lookup)
    assert out["score"] == 1.0
    assert out["pass_"] is True


def test_citation_validity_byte_mismatch():
    pipeline = [{
        "topic_name": "X",
        "tasks": [{"task": "y", "citations": [{"quote": "Paraphrase", "lines": "0001-0001"}]}],
    }]
    def lookup(a, b):
        return "Hello world"
    out = M.citation_validity(pipeline, lookup)
    assert out["score"] == 0.0
    assert out["pass_"] is False


# ── citation_coverage ─────────────────────────────────────────────────────


def test_citation_coverage_overlap_counts():
    pipeline = [{
        "topic_name": "ARM",
        "tasks": [{"task": "x", "citations": [{"quote": "...", "lines": "0050-0060"}]}],
    }]
    expected = [{
        "topic_name": "ARM",
        "evidence_line_ranges": [[40, 70]],
    }]
    out = M.citation_coverage(pipeline, expected)
    assert out["score"] == 1.0


def test_citation_coverage_no_overlap():
    pipeline = [{
        "topic_name": "ARM",
        "tasks": [{"task": "x", "citations": [{"quote": "...", "lines": "0500-0510"}]}],
    }]
    expected = [{
        "topic_name": "ARM",
        "evidence_line_ranges": [[40, 70]],
    }]
    out = M.citation_coverage(pipeline, expected)
    assert out["score"] == 0.0


# ── naming_stability ──────────────────────────────────────────────────────


def test_naming_stability_all_identical():
    run = [{"topic_name": "ARM"}, {"topic_name": "Stress Testing"}]
    out = M.naming_stability([run, run, run])
    assert out["score"] == 1.0
    assert out["pass_"] is True


def test_naming_stability_one_differs():
    a = [{"topic_name": "ARM"}, {"topic_name": "Stress Testing"}]
    b = [{"topic_name": "ARM"}, {"topic_name": "Stress Test Framework"}]  # name drifted
    out = M.naming_stability([a, b])
    assert out["pass_"] is False
