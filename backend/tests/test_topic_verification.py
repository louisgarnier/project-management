"""Tests for topic_verification — EPIC-16 RAG passes orchestration."""

import asyncio
from unittest.mock import AsyncMock

from backend.services import topic_verification as tv


def _llm_returns(payload):
    """Build an AsyncMock returning a fixed JSON-serializable payload."""
    return AsyncMock(return_value=payload)


def test_run_verify_new_truly_new(monkeypatch):
    """Happy path: LLM returns truly_new with one verified citation."""
    transcripts = {"call-1": "We talked about onboarding redesign."}
    project_topics = []
    candidate = {
        "name": "Customer onboarding redesign",
        "key_terms": ["onboarding"],
        "tasks": [{"task": "Mockup new flow", "next_step": "", "owner": "", "status": "open"}],
        "open_questions": [],
        "decisions": [],
    }
    llm_result = {
        "verdict": "truly_new",
        "matched_topic_id": None,
        "matched_topic_name": None,
        "extraction_grounded": True,
        "ungrounded_items": [],
        "citations": [
            {"call_id": "call-1", "lines": "1-1", "quote": "onboarding redesign", "for": "extraction"}
        ],
    }
    monkeypatch.setattr(tv, "_call_llm", _llm_returns(llm_result))

    out = asyncio.run(tv.run_verify_new(candidate, project_topics, transcripts, llm="claude", model=None))
    assert out["verdict"] == "truly_new"
    assert out["needs_manual_review"] is False
    assert len(out["citations"]) == 1


def test_run_verify_new_retries_then_flags_manual_review(monkeypatch):
    """When LLM citations fail post-verify twice, return needs_manual_review=True."""
    transcripts = {"call-1": "real body text."}
    candidate = {"name": "Foo", "key_terms": ["foo"]}
    llm_result_bad = {
        "verdict": "truly_new",
        "matched_topic_id": None,
        "matched_topic_name": None,
        "extraction_grounded": True,
        "ungrounded_items": [],
        "citations": [{"call_id": "call-1", "lines": "1-1", "quote": "FABRICATED", "for": "extraction"}],
    }
    mock_llm = AsyncMock(side_effect=[llm_result_bad, llm_result_bad])
    monkeypatch.setattr(tv, "_call_llm", mock_llm)

    out = asyncio.run(tv.run_verify_new(candidate, [], transcripts, llm="claude", model=None))
    assert out["needs_manual_review"] is True
    assert mock_llm.call_count == 2  # 1 initial + 1 retry


def test_resolve_workflow_llm_uses_artifact_types_first():
    """Verify resolution: artifact_types → projects → system_settings."""
    from backend.services.topics_service import _resolve_workflow_llm_for_category

    class _FakeDB:
        _t: str
        def table(self, name):
            self._t = name
            return self
        def select(self, *_a, **_kw): return self
        def eq(self, *_a, **_kw): return self
        def limit(self, _): return self
        def execute(self):
            class _R: pass
            r = _R()
            if self._t == "artifact_types":
                r.data = [{"llm": "claude", "model": "claude-sonnet-4-6"}]
            else:
                r.data = []
            return r

    llm, model = _resolve_workflow_llm_for_category("proj-1", "verify_new_topic", _FakeDB())
    assert llm == "claude"
    assert model == "claude-sonnet-4-6"


def test_run_verify_not_discussed_not_found(monkeypatch):
    """Happy path: topic not mentioned, citation=null."""
    transcript = "We only discussed migration timeline today."
    llm_result = {"verdict": "not_discussed", "citation": None}
    monkeypatch.setattr(tv, "_call_llm", _llm_returns(llm_result))
    out = asyncio.run(tv.run_verify_not_discussed(
        {"name": "Performance testing", "key_terms": ["perf"]},
        transcript, call_id="call-3", llm="claude", model=None
    ))
    assert out["verdict"] == "not_discussed"
    assert out["citation"] is None
    assert out["needs_manual_review"] is False


def test_run_verify_not_discussed_found(monkeypatch):
    transcript = "Hassan said the perf test passed."
    llm_result = {"verdict": "actually_discussed",
                  "citation": {"call_id": "call-3", "lines": "1-1", "quote": "the perf test passed"}}
    monkeypatch.setattr(tv, "_call_llm", _llm_returns(llm_result))
    out = asyncio.run(tv.run_verify_not_discussed(
        {"name": "Performance testing", "key_terms": ["perf"]},
        transcript, call_id="call-3", llm="claude", model=None
    ))
    assert out["verdict"] == "actually_discussed"
    assert out["citation"]["quote"] == "the perf test passed"
    assert out["needs_manual_review"] is False


def test_run_extract_topic_updates_returns_snapshot_and_trail(monkeypatch):
    """Pass ③ returns extracted_snapshot + evidence_trail with verified citations."""
    transcripts = {
        "call-1": "Hassan mentioned MC Mac issue first.",
        "call-2": "Test the boost flag next.",
    }
    topic_anchor = {"name": "MC Mac memory issue", "key_terms": ["MC Mac"]}
    llm_result = {
        "extracted_snapshot": {
            "summary": "MC Mac memory issue under investigation.",
            "status": "in_progress",
            "tasks": [
                {"task_id": None, "task": "Test boost flag", "next_step": "",
                 "owner": "", "status": "open",
                 "primary_citation": {"call_id": "call-2", "lines": "1-1",
                                       "quote": "Test the boost flag next"},
                 "supporting_citations": []}
            ],
            "open_questions": [],
            "decisions": [],
        },
        "evidence_trail": [
            {"call_id": "call-1",
             "citation": {"call_id": "call-1", "lines": "1-1",
                          "quote": "MC Mac issue first"},
             "action_label": "first raised"},
            {"call_id": "call-2",
             "citation": {"call_id": "call-2", "lines": "1-1",
                          "quote": "Test the boost flag next"},
             "action_label": "task added"},
        ],
    }
    monkeypatch.setattr(tv, "_call_llm", _llm_returns(llm_result))

    out = asyncio.run(tv.run_extract_topic_updates(topic_anchor, transcripts, llm="claude", model=None))
    assert out["needs_manual_review"] is False
    assert len(out["extracted_snapshot"]["tasks"]) == 1
    assert len(out["evidence_trail"]) == 2
