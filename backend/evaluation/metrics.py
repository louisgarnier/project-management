"""Metric implementations for Stage 13 evaluation.

Each function takes pipeline output + a gold entry and returns a numeric score
+ optional details. The 7 metrics match gold_set_v0.1.json::evaluation_criteria.

Topic matching:
- Canonical match (case-insensitive equality)
- Close semantic match (token Jaccard ≥ TOPIC_FUZZY_THRESHOLD)

Task matching:
- All `must_have_keywords` present (case-insensitive substring) in pipeline task text

Citation matching:
- Byte-identical equality between pipeline citation text and resolved
  transcript text for the cited line range.
"""

from __future__ import annotations

import re
from typing import TypedDict

TOPIC_FUZZY_THRESHOLD = 0.4  # Jaccard on tokens; tune against gold set


# ── Helpers ────────────────────────────────────────────────────────────────


_TOKEN_RE = re.compile(r"\b[a-z][a-z0-9_-]+\b")


def _tokens(name: str) -> set[str]:
    return set(_TOKEN_RE.findall((name or "").lower()))


def _topic_match(extracted_name: str, expected_name: str) -> bool:
    """Canonical (case-insensitive exact) OR close semantic (Jaccard)."""
    a = (extracted_name or "").strip().lower()
    b = (expected_name or "").strip().lower()
    if not a or not b:
        return False
    if a == b:
        return True
    ta, tb = _tokens(extracted_name), _tokens(expected_name)
    if not ta or not tb:
        return False
    inter = ta & tb
    union = ta | tb
    jacc = len(inter) / len(union) if union else 0.0
    return jacc >= TOPIC_FUZZY_THRESHOLD


def _task_text(task: dict) -> str:
    return " ".join([
        task.get("task") or "",
        task.get("next_step") or "",
    ]).lower()


def _task_matches_expected(extracted_task: dict, expected_task: dict) -> bool:
    """All must_have_keywords appear (case-insensitive) in the extracted task text."""
    needles = [(k or "").lower() for k in (expected_task.get("must_have_keywords") or [])]
    if not needles:
        return False
    haystack = _task_text(extracted_task)
    return all(needle in haystack for needle in needles)


# ── Per-metric implementations ────────────────────────────────────────────


class MetricResult(TypedDict, total=False):
    score: float
    pass_: bool
    target: str
    details: dict


def topic_recall(pipeline_output: list[dict], expected_topics: list[dict], *, target: float = 0.95) -> MetricResult:
    """Fraction of expected_topics matched by at least one extracted topic."""
    if not expected_topics:
        return {"score": 1.0, "pass_": True, "target": f">= {target}", "details": {"matched": 0, "total": 0}}
    extracted_names = [t.get("topic_name") or t.get("name") or "" for t in (pipeline_output or [])]
    matched = 0
    matched_pairs: list[tuple[str, str]] = []
    for exp in expected_topics:
        for ext_name in extracted_names:
            if _topic_match(ext_name, exp.get("topic_name", "")):
                matched += 1
                matched_pairs.append((exp.get("topic_name", ""), ext_name))
                break
    score = matched / len(expected_topics)
    return {
        "score": score,
        "pass_": score >= target,
        "target": f">= {target}",
        "details": {"matched": matched, "total": len(expected_topics), "matches": matched_pairs},
    }


def topic_precision(pipeline_output: list[dict], expected_topics: list[dict], excluded_topics: list[dict], *, target: float = 0.85) -> MetricResult:
    """Fraction of pipeline-output topics that match an expected_topic.
    Hallucinated topics (matching topics_explicitly_excluded) count as FALSE positives."""
    extracted = [(t.get("topic_name") or t.get("name") or "") for t in (pipeline_output or [])]
    if not extracted:
        return {"score": 1.0, "pass_": True, "target": f">= {target}", "details": {"true_pos": 0, "total": 0}}
    excluded_names = [e.get("topic") or "" for e in (excluded_topics or [])]
    true_pos = 0
    false_pos_hallucinated: list[str] = []
    for ext in extracted:
        # Hallucination check first — explicit exclusion overrides any expected match
        if any(_topic_match(ext, exc) for exc in excluded_names):
            false_pos_hallucinated.append(ext)
            continue
        if any(_topic_match(ext, exp.get("topic_name", "")) for exp in expected_topics):
            true_pos += 1
    score = true_pos / len(extracted)
    return {
        "score": score,
        "pass_": score >= target,
        "target": f">= {target}",
        "details": {
            "true_pos": true_pos,
            "total": len(extracted),
            "hallucinated": false_pos_hallucinated,
        },
    }


def task_recall(pipeline_output: list[dict], expected_topics: list[dict], *, target: float = 0.80) -> MetricResult:
    """For each correctly-matched topic, fraction of expected_tasks present in output."""
    total_expected = 0
    total_matched = 0
    breakdown: list[dict] = []
    for exp_topic in expected_topics:
        expected_tasks = exp_topic.get("expected_tasks") or []
        if not expected_tasks:
            continue
        # Find the matching extracted topic
        match_topic: dict | None = None
        for t in (pipeline_output or []):
            if _topic_match(t.get("topic_name") or t.get("name") or "", exp_topic.get("topic_name", "")):
                match_topic = t
                break
        extracted_tasks = (match_topic.get("tasks") or []) if match_topic else []
        topic_matched = 0
        for exp_task in expected_tasks:
            if any(_task_matches_expected(et, exp_task) for et in extracted_tasks):
                topic_matched += 1
        total_expected += len(expected_tasks)
        total_matched += topic_matched
        breakdown.append({
            "topic": exp_topic.get("topic_name", ""),
            "matched": topic_matched,
            "expected": len(expected_tasks),
        })
    score = (total_matched / total_expected) if total_expected else 1.0
    return {
        "score": score,
        "pass_": score >= target,
        "target": f">= {target}",
        "details": {"matched": total_matched, "expected": total_expected, "per_topic": breakdown},
    }


def citation_validity(pipeline_output: list[dict], by_idx_lookup) -> MetricResult:
    """Fraction of pipeline-output citations that match transcript byte-for-byte.

    `by_idx_lookup(start_idx, end_idx) -> str`: callable that resolves a line
    range to verbatim transcript text. Typically `partial(resolve_lines, ingest_result)`.
    Target: 1.00 (must-pass).
    """
    citations_seen = 0
    citations_valid = 0
    failures: list[dict] = []
    for topic in (pipeline_output or []):
        for task in (topic.get("tasks") or []):
            for c in (task.get("citations") or []):
                citations_seen += 1
                # Accept several citation shapes — be tolerant.
                if isinstance(c, str):
                    quote = c
                    line_range = None
                elif isinstance(c, dict):
                    quote = c.get("quote") or c.get("text") or ""
                    lines_str = c.get("lines") or ""  # e.g. "0001-0002"
                    if "-" in lines_str:
                        a, b = lines_str.split("-", 1)
                        line_range = (a.strip(), b.strip())
                    elif lines_str:
                        line_range = (lines_str.strip(), lines_str.strip())
                    else:
                        line_range = None
                else:
                    quote, line_range = "", None
                if not quote:
                    failures.append({"reason": "empty quote", "citation": c})
                    continue
                if line_range is None:
                    # No line range to resolve — substring search in any text won't fly here.
                    # We can't verify without a line range. Count as failure.
                    failures.append({"reason": "no line_range", "citation": c})
                    continue
                try:
                    resolved = by_idx_lookup(line_range[0], line_range[1])
                except Exception as e:  # noqa: BLE001
                    failures.append({"reason": f"resolve error: {e}", "citation": c})
                    continue
                if resolved == quote:
                    citations_valid += 1
                else:
                    failures.append({"reason": "byte mismatch", "expected": resolved, "got": quote})
    score = (citations_valid / citations_seen) if citations_seen else 1.0
    return {
        "score": score,
        "pass_": score >= 1.0,
        "target": "= 1.00",
        "details": {"valid": citations_valid, "total": citations_seen, "failures": failures[:10]},
    }


def citation_coverage(pipeline_output: list[dict], expected_topics: list[dict], *, target: float = 0.90) -> MetricResult:
    """For each correctly-matched topic, do the citations overlap the expected evidence_line_ranges?
    Any overlap (single line in common) counts."""
    total_topics_with_ranges = 0
    total_topics_covered = 0
    per_topic: list[dict] = []
    for exp_topic in expected_topics:
        ranges = exp_topic.get("evidence_line_ranges") or []
        if not ranges:
            continue
        total_topics_with_ranges += 1
        # Find matching extracted topic
        match_topic: dict | None = None
        for t in (pipeline_output or []):
            if _topic_match(t.get("topic_name") or t.get("name") or "", exp_topic.get("topic_name", "")):
                match_topic = t
                break
        if not match_topic:
            per_topic.append({"topic": exp_topic.get("topic_name", ""), "covered": False, "reason": "topic not matched"})
            continue
        # Collect citation line ranges from this extracted topic
        cit_ranges: list[tuple[int, int]] = []
        for task in (match_topic.get("tasks") or []):
            for c in (task.get("citations") or []):
                if not isinstance(c, dict):
                    continue
                lines_str = c.get("lines") or ""
                if "-" in lines_str:
                    a, b = lines_str.split("-", 1)
                    try:
                        cit_ranges.append((int(a), int(b)))
                    except ValueError:
                        pass
                elif lines_str:
                    try:
                        v = int(lines_str)
                        cit_ranges.append((v, v))
                    except ValueError:
                        pass
        # Overlap check
        covered = False
        for exp_range in ranges:
            for cit_a, cit_b in cit_ranges:
                if not (cit_b < exp_range[0] or cit_a > exp_range[1]):
                    covered = True
                    break
            if covered:
                break
        if covered:
            total_topics_covered += 1
        per_topic.append({"topic": exp_topic.get("topic_name", ""), "covered": covered})
    score = (total_topics_covered / total_topics_with_ranges) if total_topics_with_ranges else 1.0
    return {
        "score": score,
        "pass_": score >= target,
        "target": f">= {target}",
        "details": {"covered": total_topics_covered, "total": total_topics_with_ranges, "per_topic": per_topic},
    }


def naming_stability(pipeline_outputs: list[list[dict]]) -> MetricResult:
    """Across N runs of the same transcript, how many produced identical topic name sets?
    Target: 1.00 (all N runs identical)."""
    if not pipeline_outputs:
        return {"score": 1.0, "pass_": True, "target": "= 1.00", "details": {"n_runs": 0}}
    name_sets = [
        frozenset((t.get("topic_name") or t.get("name") or "").strip().lower() for t in run)
        for run in pipeline_outputs
    ]
    unique = len(set(name_sets))
    score = 1.0 if unique == 1 else 0.0
    return {
        "score": score,
        "pass_": unique == 1,
        "target": "= 1.00 (all runs identical)",
        "details": {"n_runs": len(pipeline_outputs), "unique_name_sets": unique},
    }


def no_hallucination(pipeline_output: list[dict], excluded_topics: list[dict]) -> MetricResult:
    """Topics in topics_explicitly_excluded MUST NOT appear in pipeline output.
    Target: 0 hallucinated topics. Must-pass."""
    extracted = [(t.get("topic_name") or t.get("name") or "") for t in (pipeline_output or [])]
    excluded_names = [e.get("topic") or "" for e in (excluded_topics or [])]
    hallucinated: list[str] = []
    for ext in extracted:
        for exc in excluded_names:
            if _topic_match(ext, exc):
                hallucinated.append(ext)
                break
    return {
        "score": 1.0 if not hallucinated else 0.0,
        "pass_": len(hallucinated) == 0,
        "target": "= 0 hallucinated",
        "details": {"hallucinated": hallucinated, "excluded_count": len(excluded_names)},
    }
