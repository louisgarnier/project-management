"""Loads the gold set v0.1 (3 SWIB transcripts + structured ground truth)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

GOLD_SET_DIR = Path(__file__).resolve().parents[2] / "docs" / "project" / "config" / "gold set"


class ExpectedTask(TypedDict, total=False):
    task_summary: str
    must_have_keywords: list[str]
    owner_hint: str
    status_hint: str
    note: str


class ExpectedTopic(TypedDict, total=False):
    topic_name: str
    importance: str
    evidence_line_ranges: list[list[int]]
    expected_tasks: list[ExpectedTask]
    minimum_task_count: int
    minimum_citation_count: int
    note: str


class GoldEntry(TypedDict, total=False):
    transcript_id: str
    transcript_file: str
    raw_text: str
    project: str
    call_type: str
    dimensions: dict
    expected_topics: list[ExpectedTopic]
    topics_explicitly_excluded: list[dict]


class GoldSet(TypedDict):
    version: str
    purpose: str
    annotation_notes: list[str]
    entries: list[GoldEntry]
    evaluation_criteria: dict
    growth_plan: dict


def load_gold_set(version: str = "v0.1", gold_set_dir: Path | None = None) -> GoldSet:
    """Load the gold set JSON + raw transcript files.

    Each entry includes the raw transcript text inline so consumers don't need
    to re-read files.
    """
    base = gold_set_dir or GOLD_SET_DIR
    spec_path = base / f"gold_set_{version}.json"
    if not spec_path.exists():
        raise FileNotFoundError(f"gold set spec not found: {spec_path}")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    entries: list[GoldEntry] = []
    for t in spec.get("transcripts", []):
        transcript_path = base / t["transcript_file"]
        raw_text = transcript_path.read_text(encoding="utf-8") if transcript_path.exists() else ""
        entry: GoldEntry = {
            "transcript_id": t["transcript_id"],
            "transcript_file": t["transcript_file"],
            "raw_text": raw_text,
            "project": t.get("project") or "",
            "call_type": t.get("call_type") or "",
            "dimensions": t.get("dimensions") or {},
            "expected_topics": t.get("expected_topics") or [],
            "topics_explicitly_excluded": t.get("topics_explicitly_excluded") or [],
        }
        entries.append(entry)

    return {
        "version": spec.get("gold_set_version") or version,
        "purpose": spec.get("purpose") or "",
        "annotation_notes": spec.get("annotation_notes") or [],
        "entries": entries,
        "evaluation_criteria": spec.get("evaluation_criteria") or {},
        "growth_plan": spec.get("growth_plan") or {},
    }
