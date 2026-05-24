"""Tests for topic_verification — EPIC-16 RAG passes orchestration."""

import asyncio
from unittest.mock import AsyncMock

from backend.services import topic_verification as tv


def _llm_returns(payload):
    """Build an AsyncMock returning a fixed JSON-serializable payload."""
    return AsyncMock(return_value=payload)


def _ingested(text: str) -> dict:
    """Build a minimal ingested dict from a raw string (matches Stage 0 output shape)."""
    lines = text.split("\n") if text else []
    return {
        "line_count": len(lines),
        "lines": {str(i + 1).zfill(4): line for i, line in enumerate(lines)},
    }


def test_run_verify_new_truly_new(monkeypatch):
    """Happy path: LLM returns truly_new with one verified citation (EPIC-18: ingested transcripts)."""
    # EPIC-18: transcripts are now ingested dicts
    transcripts = {"call-1": _ingested("We talked about onboarding redesign.")}
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
        "citations": [
            {"call_id": "call-1", "evidence_lines": [1, 1], "for": "extraction"}
        ],
    }
    monkeypatch.setattr(tv, "_call_llm", _llm_returns(llm_result))

    out = asyncio.run(tv.run_verify_new(candidate, project_topics, transcripts, llm="claude", model=None))
    assert out["verdict"] == "truly_new"
    assert out["needs_manual_review"] is False
    assert len(out["citations"]) == 1


def test_run_verify_new_retries_then_flags_manual_review(monkeypatch):
    """When LLM citations fail post-verify twice, return needs_manual_review=True (EPIC-18)."""
    # EPIC-18: transcripts are now ingested dicts; evidence_lines out of range → fail
    transcripts = {"call-1": _ingested("real body text.")}
    candidate = {"name": "Foo", "key_terms": ["foo"]}
    llm_result_bad = {
        "verdict": "truly_new",
        "matched_topic_id": None,
        "matched_topic_name": None,
        "citations": [{"call_id": "call-1", "evidence_lines": [999, 999], "for": "extraction"}],
    }
    mock_llm = AsyncMock(side_effect=[llm_result_bad, llm_result_bad])
    monkeypatch.setattr(tv, "_call_llm", mock_llm)

    out = asyncio.run(tv.run_verify_new(candidate, [], transcripts, llm="claude", model=None))
    assert out["needs_manual_review"] is True
    assert mock_llm.call_count == 2  # 1 initial + 1 retry


def test_idf_weighted_jaccard_downweights_common_terms():
    """A term shared across most project topics has low IDF; rare shared terms dominate."""
    from backend.services.topic_verification import compute_idf, weighted_jaccard
    project_topics = [
        {"key_terms": ["snowflake", "schema"]},
        {"key_terms": ["snowflake", "auth"]},
        {"key_terms": ["snowflake", "ARM"]},
        {"key_terms": ["snowflake", "fons-alpha"]},
        {"key_terms": ["snowflake"]},
    ]
    idf = compute_idf(project_topics)
    # "snowflake" appears in all 5 → low IDF; "ARM" appears in 1 → high IDF
    assert idf["snowflake"] < idf["arm"]
    # Two topics sharing ONLY "snowflake" → weighted Jaccard should be modest, not 1.0
    score = weighted_jaccard(["snowflake", "environments"], ["snowflake", "ARM", "schema"], idf)
    assert 0 < score < 0.5


def test_lexical_precheck_returns_mechanical_verdict_when_zero_qualify():
    """If no existing topic scores above threshold, verdict_hint='mechanical_truly_new'
    and qualified_topic_ids is empty (LLM should be skipped). EPIC-18: accepts ingested dicts."""
    from backend.services.topic_verification import lexical_precheck
    candidate = {"name": "Brand new thing", "key_terms": ["fresh", "unique"], "tasks": []}
    project_topics = [
        {"topic_id": "t1", "name": "Old topic", "key_terms": ["unrelated"], "tasks": []},
    ]
    # EPIC-18: ingested dict format
    transcripts = {"call-1": _ingested("talking about completely unrelated stuff")}
    out = lexical_precheck(candidate, project_topics, transcripts)
    assert out["qualified_topic_ids"] == []
    assert out["verdict_hint"] == "mechanical_truly_new"


def test_check_citation_rarity_rejects_generic_only_quotes():
    """A citation that only quotes a generic platform term (high-df, low-IDF) should fail rarity."""
    from backend.services.topic_verification import check_citation_rarity
    idf = {"snowflake": 0.2, "environments": 2.0, "fons-alpha": 2.5}
    candidate = {"name": "Snowflake setup", "key_terms": ["snowflake", "environments"]}
    # Citation only quotes the generic word "snowflake" — no rare term → fail
    cits = [{"call_id": "c1", "quote": "we use snowflake", "for": "verdict"}]
    fails = check_citation_rarity(cits, candidate, idf)
    assert len(fails) == 1
    # Citation quoting a rare term passes
    cits2 = [{"call_id": "c1", "quote": "set up environments for staging", "for": "verdict"}]
    fails2 = check_citation_rarity(cits2, candidate, idf)
    assert fails2 == []


def test_effective_token_set_aggregates_per_task_key_terms():
    """v4: per-task key_terms feed the parent topic's effective token bag."""
    from backend.services.topic_verification import effective_token_set
    # Topic with NO topic-level key_terms but tasks carry them (v4 model)
    topic = {
        "name": "Snowflake setup",
        "key_terms": [],
        "tasks": [
            {"task": "access provisioning", "key_terms": ["access", "vpn"]},
            {"task": "schema migration", "key_terms": ["schema", "migration"]},
        ],
    }
    tokens = effective_token_set(topic)
    # Tokens should contain name + per-task aggregations
    assert "snowflake" in tokens
    assert "access" in tokens
    assert "vpn" in tokens
    assert "schema" in tokens
    assert "migration" in tokens


def test_effective_token_set_catches_paraphrase():
    """The paraphrase 'stress testing' (key_term) vs 'stress test' (different key_term)
    should now share the token 'stress' via tokenisation. Name tokens are also pooled."""
    from backend.services.topic_verification import (
        effective_token_set, compute_idf, weighted_jaccard_tokens
    )
    candidate = {"name": "Stress Testing Framework", "key_terms": ["stress testing", "scenario analysis"]}
    existing = {"name": "Stress testing PA readiness", "key_terms": ["stress test", "PA readiness"]}
    cand_tokens = effective_token_set(candidate)
    exist_tokens = effective_token_set(existing)
    # Both should contain "stress" and "testing" at minimum (from names)
    assert "stress" in cand_tokens and "stress" in exist_tokens
    assert "testing" in cand_tokens and "testing" in exist_tokens
    # Score should be > 0 even though the original key_term strings don't match exactly
    idf = compute_idf([candidate, existing, {"key_terms": ["unrelated"]}])
    score = weighted_jaccard_tokens(cand_tokens, exist_tokens, idf)
    assert score > 0.2  # decent signal after tokenisation


def test_check_reasoning_references_tasks_flags_vague_reasoning():
    """merge_reasoning must reference specific task content from both sides."""
    from backend.services.topic_verification import check_reasoning_references_tasks
    cand = [{"task": "schedule architect meeting", "next_step": ""}]
    target = [{"task": "design aggregation schema", "next_step": ""}]
    # Vague reasoning — references neither task
    vague = "Both topics are related to Snowflake work."
    fails = check_reasoning_references_tasks(vague, cand, target)
    assert len(fails) >= 1
    # Concrete reasoning — references both
    concrete = "candidate's 'schedule architect meeting' fits the target's 'design aggregation schema' work stream"
    fails2 = check_reasoning_references_tasks(concrete, cand, target)
    assert fails2 == []


def test_resolve_workflow_llm_uses_project_default():
    """Post-EPIC-16: resolver reads ONLY projects.default_llm/default_model.
    artifact_types overrides are intentionally ignored — project is the single source of truth."""
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
            if self._t == "projects":
                r.data = [{"default_llm": "openrouter", "default_model": "anthropic/claude-sonnet-4-6"}]
            elif self._t == "artifact_types":
                # Even if artifact_types has an override, it must be ignored.
                r.data = [{"llm": "claude", "model": "claude-sonnet-4-6"}]
            else:
                r.data = []
            return r

    llm, model = _resolve_workflow_llm_for_category("proj-1", "verify_new_topic", _FakeDB())
    assert llm == "openrouter"
    assert model == "anthropic/claude-sonnet-4-6"


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


# ── EPIC-18: New prompt builder tests ───────────────────────────────────────


def test_prompt_includes_line_numbered_transcripts():
    """EPIC-18: _build_verify_new_prompt formats ingested transcripts with line numbers."""
    from backend.services.topic_verification import _build_verify_new_prompt
    candidate = {"topic_id": "c-1", "name": "X", "tasks": []}
    transcripts = {
        "call-a": {
            "line_count": 2,
            "lines": {"0001": "Hello world", "0002": "Second line"},
        }
    }
    msg = _build_verify_new_prompt(candidate, [], transcripts)
    assert "--- CALL call-a (2 lines) ---" in msg
    assert "0001  Hello world" in msg
    assert "0002  Second line" in msg


def test_prompt_handles_empty_project_topics():
    """EPIC-18: _build_verify_new_prompt works with no existing project topics."""
    from backend.services.topic_verification import _build_verify_new_prompt
    candidate = {"topic_id": "c-1", "name": "Test", "tasks": [{"task": "do x"}]}
    transcripts = {"call-a": {"line_count": 1, "lines": {"0001": "x"}}}
    msg = _build_verify_new_prompt(candidate, [], transcripts)
    assert "EXISTING PROJECT TOPICS:" in msg
    assert "CANDIDATE NEW TOPIC:" in msg
    assert "do x" in msg


# ── EPIC-18 S2.2: canonical match verification ───────────────────────────────


import pytest


@pytest.mark.asyncio
async def test_run_verify_canonical_match_confirmed(monkeypatch):
    from backend.services.topic_verification import run_verify_canonical_match
    async def fake_llm(*a, **kw):
        return {
            "verdict": "confirmed_match",
            "reasoning": "Candidate task 'X' matches existing task 'X'.",
            "alternative_topic_id": None,
            "citations": [{"call_id": "c1", "evidence_lines": [1, 2], "for": "verdict"}],
        }
    monkeypatch.setattr("backend.services.topic_verification._call_llm", fake_llm)
    out = await run_verify_canonical_match(
        candidate={"name": "C", "tasks": [{"task": "X"}]},
        matched_topic={"topic_id": "t1", "name": "ARM", "tasks": [{"task": "X"}]},
        all_project_topics=[],
        transcripts={"c1": {"line_count": 5, "lines": {"0001": "x", "0002": "y", "0003": "z", "0004": "a", "0005": "b"}}},
        llm="openrouter", model="x",
    )
    assert out["verdict"] == "confirmed_match"
    assert out["needs_manual_review"] is False


@pytest.mark.asyncio
async def test_run_verify_canonical_match_wrong_canonical(monkeypatch):
    from backend.services.topic_verification import run_verify_canonical_match
    async def fake_llm(*a, **kw):
        return {
            "verdict": "wrong_canonical_belongs_elsewhere",
            "reasoning": "Tasks are about stress testing, not ARM.",
            "alternative_topic_id": "t2",
            "citations": [
                {"call_id": "c1", "evidence_lines": [1, 2], "for": "verdict"},
                {"call_id": "c1", "evidence_lines": [3, 4], "for": "verdict"},
            ],
        }
    monkeypatch.setattr("backend.services.topic_verification._call_llm", fake_llm)
    out = await run_verify_canonical_match(
        candidate={"name": "C", "tasks": [{"task": "stress test setup"}]},
        matched_topic={"topic_id": "t1", "name": "ARM", "tasks": [{"task": "LMAC test"}]},
        all_project_topics=[{"topic_id": "t1", "name": "ARM"}, {"topic_id": "t2", "name": "Stress Test"}],
        transcripts={"c1": {"line_count": 5, "lines": {"0001": "x", "0002": "y", "0003": "z", "0004": "a", "0005": "b"}}},
        llm="openrouter", model="x",
    )
    assert out["verdict"] == "wrong_canonical_belongs_elsewhere"
    assert out["alternative_topic_id"] == "t2"
    assert out["needs_manual_review"] is False


@pytest.mark.asyncio
async def test_run_verify_canonical_match_failed_citations(monkeypatch):
    from backend.services.topic_verification import run_verify_canonical_match
    async def fake_llm(*a, **kw):
        return {
            "verdict": "confirmed_match",
            "reasoning": "yes",
            "alternative_topic_id": None,
            "citations": [{"call_id": "c1", "evidence_lines": [100, 200], "for": "verdict"}],  # out of bounds
        }
    monkeypatch.setattr("backend.services.topic_verification._call_llm", fake_llm)
    out = await run_verify_canonical_match(
        candidate={"name": "C", "tasks": []},
        matched_topic={"topic_id": "t1", "name": "ARM", "tasks": []},
        all_project_topics=[],
        transcripts={"c1": {"line_count": 5, "lines": {"0001": "x", "0002": "y", "0003": "z", "0004": "a", "0005": "b"}}},
        llm="openrouter", model="x",
    )
    assert out["needs_manual_review"] is True
    assert "failed_citations" in out


@pytest.mark.asyncio
async def test_run_verify_new_recovers_wrapped_response(monkeypatch):
    """EPIC-18 S2.3: Pass 1 unwraps common LLM wrapper patterns."""
    from backend.services.topic_verification import run_verify_new
    async def fake_llm(*a, **kw):
        return {"result": {
            "verdict": "truly_new",
            "final_verdict": "truly_new",
            "matched_topic_id": None,
            "matched_topic_name": None,
            "evaluations": [],
            "citations": [],
            "merge_reasoning": "No fit.",
        }}
    monkeypatch.setattr("backend.services.topic_verification._call_llm", fake_llm)
    out = await run_verify_new(
        candidate={"name": "C", "tasks": []},
        project_topics=[],
        transcripts={},
        llm="x", model="y",
    )
    assert out["verdict"] == "truly_new"
    assert out["needs_manual_review"] is False


@pytest.mark.asyncio
async def test_run_verify_new_recovers_response_under_data_key(monkeypatch):
    """Alternate wrapper key — 'data' instead of 'result'."""
    from backend.services.topic_verification import run_verify_new
    async def fake_llm(*a, **kw):
        return {"data": {
            "verdict": "truly_new",
            "final_verdict": "truly_new",
            "matched_topic_id": None,
            "evaluations": [],
            "citations": [],
            "merge_reasoning": "No fit.",
        }}
    monkeypatch.setattr("backend.services.topic_verification._call_llm", fake_llm)
    out = await run_verify_new(
        candidate={"name": "C", "tasks": []},
        project_topics=[],
        transcripts={},
        llm="x", model="y",
    )
    assert out["verdict"] == "truly_new"
