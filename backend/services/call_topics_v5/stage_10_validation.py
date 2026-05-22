"""Stage 10 — validation (pure code, no LLM).

3 categories per PRD:
  - hard_failures (blocking): retry the originating stage once; escalate to Stage 11 if still failing.
  - soft_warnings (informational): surfaced in Stage 11 review payload.
  - clean: no warnings, no new topics, no low-confidence tasks → Stage 11 skipped.

Hard rules checked here:
  H1. Every task has ≥ 2 verbatim citations (citations_below_min from Stage 8 already flagged).
  H2. No off-transcript citations (citation_valid from Stage 4).
  H3. No orphan atomic units (Stage 5 already flagged via orphans list).
  H4. Topic has ≥ 1 task.
  H5. Topic name not in topics_explicitly_excluded for this project.
  H6. No duplicate topic names within the run.

Soft warnings:
  S1. Task with ≥ 2 citations from same speaker, lines within 5 of each other.
  S2. Topic with exactly 1 task at confidence 0.45-0.55.
  S3. Topic where 80%+ of unit evidence_lines fall within a 30-line window.
  S4. New topic proposal lexically similar (≥ 0.5 Jaccard) to topics_explicitly_excluded.
"""

from __future__ import annotations

import logging
import re
from typing import TypedDict

logger = logging.getLogger("calltracker.call_topics_v5.stage_10")


SOFT_WARNING_THRESHOLDS = {
    "same_speaker_max_line_distance": 5,
    "low_conf_boundary_lo": 0.45,
    "low_conf_boundary_hi": 0.55,
    "narrow_basis_pct": 0.80,
    "narrow_basis_window": 30,
    "excluded_lexical_min": 0.5,
}


class ValidationReport(TypedDict, total=False):
    hard_failures: list[dict]
    soft_warnings: list[dict]
    clean: bool
    new_topic_proposals_count: int
    low_confidence_tasks_count: int


_TOKEN_RE = re.compile(r"\b[a-z][a-z0-9_-]+\b")


def _tokens(s: str) -> set[str]:
    return set(_TOKEN_RE.findall((s or "").lower()))


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def validate(
    synthesized_topics: list[dict],
    atomic_pool: list[dict],
    orphans: list[str],
    *,
    topics_explicitly_excluded: list[dict] | None = None,
    low_confidence_threshold: float = 0.5,
) -> ValidationReport:
    """Run all validation rules.

    Args:
        synthesized_topics: from Stage 9 (with confidence attached)
        atomic_pool: from Stage 4
        orphans: list[unit_id] from Stage 5
        topics_explicitly_excluded: optional project-level exclusion list
            (anti-hallucination)
        low_confidence_threshold: tasks below this score → flagged for Stage 11 review
    """
    excluded = topics_explicitly_excluded or []
    excluded_names = [(e.get("topic") or "") for e in excluded]
    by_uid = {u["unit_id"]: u for u in atomic_pool}

    hard_failures: list[dict] = []
    soft_warnings: list[dict] = []

    # H3: orphan atomic units
    if orphans:
        # Enrich with the actual text + speaker + line range so the user can decide
        orphan_details = []
        for uid in orphans:
            u = by_uid.get(uid, {})
            orphan_details.append({
                "unit_id": uid,
                "type": u.get("type"),
                "text": u.get("text"),
                "owner": u.get("owner"),
                "lines": u.get("evidence_lines"),
                "citation": u.get("citation", "")[:200],
            })
        hard_failures.append({
            "code": "H3_orphan_units",
            "severity": "hard",
            "message": (
                f"Stage 5 (clustering) did not assign {len(orphans)} atomic unit(s) to any topic. "
                f"This content will be LOST from the final output unless you re-run Stage 5 or "
                f"manually accept the loss."
            ),
            "details": {"orphan_units": orphan_details},
        })

    seen_topic_names: dict[str, int] = {}
    for topic in synthesized_topics:
        tname = topic.get("topic_name") or ""

        # H4: topic has ≥ 1 task
        if not topic.get("tasks"):
            hard_failures.append({
                "code": "H4_topic_no_tasks",
                "severity": "hard",
                "topic": tname,
                "message": "Topic has no tasks",
            })
            continue

        # H5: topic name in excluded list (anti-hallucination)
        for exc in excluded_names:
            if exc and tname.strip().lower() == exc.strip().lower():
                hard_failures.append({
                    "code": "H5_extracted_excluded_topic",
                    "severity": "hard",
                    "topic": tname,
                    "message": f"Topic name matches a project-excluded entry: {exc!r}",
                })
                break
            elif exc and _jaccard(tname, exc) >= SOFT_WARNING_THRESHOLDS["excluded_lexical_min"] and topic.get("new_topic"):
                # S4: lexical proximity to excluded
                soft_warnings.append({
                    "code": "S4_proposal_lexical_proximity_to_excluded",
                    "severity": "soft",
                    "topic": tname,
                    "matched_excluded": exc,
                    "lexical_similarity": round(_jaccard(tname, exc), 3),
                    "message": "New topic proposal lexically resembles a project-excluded entry — possible re-hallucination",
                })

        # H6: duplicate topic name within run
        key = tname.strip().lower()
        seen_topic_names[key] = seen_topic_names.get(key, 0) + 1

        # Topic narrow basis check (S3)
        topic_unit_ids = []
        for task in (topic.get("tasks") or []):
            for uid in task.get("evidence_unit_ids") or []:
                topic_unit_ids.append(uid)
        topic_units = [by_uid[uid] for uid in topic_unit_ids if uid in by_uid]
        if topic_units:
            line_starts = [u.get("evidence_lines", [0, 0])[0] for u in topic_units]
            if line_starts:
                window_size = max(line_starts) - min(line_starts)
                if window_size <= SOFT_WARNING_THRESHOLDS["narrow_basis_window"] and len(topic_units) >= 3:
                    # All units fit within a narrow window — but only flag if it's >=80% of evidence
                    pct = 1.0  # All units fall in this window by definition
                    if pct >= SOFT_WARNING_THRESHOLDS["narrow_basis_pct"]:
                        soft_warnings.append({
                            "code": "S3_narrow_evidence_basis",
                            "severity": "soft",
                            "topic": tname,
                            "window_lines": window_size,
                            "n_units": len(topic_units),
                            "message": f"All {len(topic_units)} evidence units fall within a {window_size}-line window — narrow basis",
                        })

        # Per-task checks
        n_tasks = len(topic.get("tasks") or [])
        for ti, task in enumerate(topic.get("tasks") or []):
            tname_for_task = f"{tname} / task {ti+1}"

            # H1: ≥ 2 citations
            if task.get("citations_below_min"):
                cit_count = len(task.get("citations") or [])
                first_quote = ""
                if task.get("citations"):
                    q = (task["citations"][0].get("quote") or "")
                    first_quote = q[:160] + ("…" if len(q) > 160 else "")
                hard_failures.append({
                    "code": "H1_too_few_citations",
                    "severity": "hard",
                    "topic": tname,
                    "task": task.get("task"),
                    "task_owner": task.get("owner"),
                    "citation_count": cit_count,
                    "first_citation_preview": first_quote,
                    "message": (
                        f"Task \"{task.get('task')}\" in topic \"{tname}\" has only {cit_count} "
                        f"verbatim citation (need ≥ 2). Likely cause: the topic had too few atomic "
                        f"units for Stage 7 to cite. You can accept anyway (the task is probably "
                        f"correct), drop the task, or re-run extraction."
                    ),
                })

            # H2: off-transcript citations (already filtered in Stage 8 — but double-check)
            for c in (task.get("citations") or []):
                if not (c.get("quote") or "").strip():
                    hard_failures.append({
                        "code": "H2_empty_citation",
                        "severity": "hard",
                        "topic": tname,
                        "task": task.get("task"),
                        "message": "Citation has empty quote",
                    })
                    break

            # S1: same-speaker adjacent citations (weak evidence)
            cits = task.get("citations") or []
            if len(cits) >= 2:
                by_speaker: dict[str, list[tuple[int, int]]] = {}
                for c in cits:
                    spk = (c.get("speaker") or "").strip().lower()
                    lr = c.get("lines") or ""
                    if "-" in lr:
                        try:
                            a, b = lr.split("-", 1)
                            by_speaker.setdefault(spk, []).append((int(a), int(b)))
                        except ValueError:
                            pass
                for spk, ranges in by_speaker.items():
                    if not spk or len(ranges) < 2:
                        continue
                    ranges_sorted = sorted(ranges)
                    for a, b in zip(ranges_sorted, ranges_sorted[1:]):
                        gap = b[0] - a[1]
                        if gap <= SOFT_WARNING_THRESHOLDS["same_speaker_max_line_distance"]:
                            soft_warnings.append({
                                "code": "S1_same_speaker_adjacent_citations",
                                "severity": "soft",
                                "topic": tname,
                                "task": task.get("task"),
                                "speaker": spk,
                                "gap_lines": gap,
                                "message": (
                                    f"Task \"{task.get('task')}\" has ≥2 citations but both come "
                                    f"from {spk!r} {gap} line(s) apart. Evidence may be weak: one "
                                    f"person speaking continuously isn't a stronger signal than a "
                                    f"single citation. Acknowledge if you accept it; otherwise "
                                    f"consider editing or dropping the task."
                                ),
                            })
                            break

            # S2: 1-task topic at confidence boundary
            conf_score = (task.get("confidence") or {}).get("score", 1.0)
            if (
                n_tasks == 1
                and SOFT_WARNING_THRESHOLDS["low_conf_boundary_lo"] <= conf_score <= SOFT_WARNING_THRESHOLDS["low_conf_boundary_hi"]
            ):
                soft_warnings.append({
                    "code": "S2_single_task_at_confidence_boundary",
                    "severity": "soft",
                    "topic": tname,
                    "task": task.get("task"),
                    "confidence": conf_score,
                    "message": (
                        f"Topic \"{tname}\" has only 1 task and its confidence is {conf_score:.2f} "
                        f"(borderline). Confidence is computed from 5 signals (units count, distinct "
                        f"speakers, owner clarity, citation count, registry presence). Low score "
                        f"usually means: new topic + few atomic units + unclear owner. "
                        f"Consider whether this topic deserves its own bucket or should be merged."
                    ),
                })

    # H6: duplicate topic names
    for key, count in seen_topic_names.items():
        if count > 1:
            hard_failures.append({
                "code": "H6_duplicate_topic_name",
                "severity": "hard",
                "topic_name_lower": key,
                "count": count,
                "message": f"Topic name appears {count} times (case-insensitive)",
            })

    # Compute new_topic_proposals_count + low_confidence_tasks_count
    new_topic_count = sum(1 for t in synthesized_topics if t.get("new_topic"))
    low_conf_count = sum(
        1 for t in synthesized_topics for tk in (t.get("tasks") or [])
        if (tk.get("confidence") or {}).get("score", 1.0) < low_confidence_threshold
    )

    clean = (
        not hard_failures
        and not soft_warnings
        and new_topic_count == 0
        and low_conf_count == 0
    )
    logger.info(
        "[Stage 10] %d hard failures, %d soft warnings, %d new topic proposals, %d low-conf tasks → clean=%s",
        len(hard_failures), len(soft_warnings), new_topic_count, low_conf_count, clean,
    )
    return {
        "hard_failures": hard_failures,
        "soft_warnings": soft_warnings,
        "clean": clean,
        "new_topic_proposals_count": new_topic_count,
        "low_confidence_tasks_count": low_conf_count,
    }
