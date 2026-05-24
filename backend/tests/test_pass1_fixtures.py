"""EPIC-18 STREAM 3 — Pass 1 fixture-driven tests (mocked LLM)."""
import json
from pathlib import Path

from backend.services.call_topics_v5.stage_0_ingest import ingest_transcript
from backend.services.topic_verification import run_verify_new, run_verify_canonical_match

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "pass1"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


def _ingest_fixture_transcripts(past_transcripts: dict) -> dict:
    """Ingest raw fixture transcripts. Production code consumes the canonical
    ingest_transcript output shape directly (after the line 495/733 fix)."""
    return {cid: ingest_transcript(body) for cid, body in past_transcripts.items()}


def _mock_verify_new_response(
    verdict: str,
    matched_topic_id: str | None,
    transcript_call_id: str = "call-a-uuid-0001",
):
    """Build a canned Pass 1 LLM response for `run_verify_new`."""
    async def fake(*args, **kwargs):
        return {
            "verdict": verdict,
            "final_verdict": verdict,
            "matched_topic_id": matched_topic_id,
            "matched_topic_name": None,
            "evaluations": [],
            "citations": (
                [
                    {"call_id": transcript_call_id, "evidence_lines": [1, 2], "for": "verdict"},
                    {"call_id": transcript_call_id, "evidence_lines": [1, 2], "for": "verdict"},
                ]
                if verdict == "should_be_merged_with"
                else []
            ),
            "merge_reasoning": "fixture-driven canned response",
        }
    return fake


def _mock_canonical_match_response(
    verdict: str,
    alternative_topic_id: str | None,
    transcript_call_id: str = "call-a-uuid-0001",
):
    """Build a canned LLM response for `run_verify_canonical_match`."""
    async def fake(*args, **kwargs):
        return {
            "verdict": verdict,
            "reasoning": "fixture-driven canned response",
            "alternative_topic_id": alternative_topic_id,
            "citations": [
                {"call_id": transcript_call_id, "evidence_lines": [1, 2], "for": "verdict"},
                {"call_id": transcript_call_id, "evidence_lines": [1, 2], "for": "verdict"},
            ],
        }
    return fake


def test_all_fixtures_load_and_have_required_keys():
    """Foundation test: every fixture has the schema STREAM 2 will assume."""
    required = {"scenario", "candidate", "project_topics", "past_transcripts", "expected_verdict"}
    fixture_files = list(FIXTURE_DIR.glob("*.json"))
    assert len(fixture_files) >= 5, f"Expected at least 5 fixtures, found {len(fixture_files)}"
    for path in fixture_files:
        fix = json.loads(path.read_text())
        missing = required - set(fix.keys())
        assert not missing, f"{path.name} missing keys: {missing}"
        assert "verdict" in fix["expected_verdict"], f"{path.name}: expected_verdict missing 'verdict' field"
        assert "min_confidence" in fix["expected_verdict"], f"{path.name}: expected_verdict missing 'min_confidence' field"
        assert isinstance(fix["expected_verdict"]["min_confidence"], int)
        assert 0 <= fix["expected_verdict"]["min_confidence"] <= 100


async def test_fixture_same_transcript_dup(monkeypatch):
    """Same transcript → candidate should reconcile as merge with proj-arm."""
    fix = load_fixture("same_transcript_dup")
    expected = fix["expected_verdict"]
    transcripts = _ingest_fixture_transcripts(fix["past_transcripts"])
    transcript_call_id = next(iter(fix["past_transcripts"].keys()))
    monkeypatch.setattr(
        "backend.services.topic_verification._call_llm",
        _mock_verify_new_response(expected["verdict"], expected["matched_topic_id"], transcript_call_id),
    )
    out = await run_verify_new(
        candidate=fix["candidate"],
        project_topics=fix["project_topics"],
        transcripts=transcripts,
        llm="x",
        model="y",
    )
    assert out["verdict"] == expected["verdict"]
    assert out["matched_topic_id"] == expected["matched_topic_id"]
    assert out["confidence"]["pct"] >= expected["min_confidence"]


async def test_fixture_true_new(monkeypatch):
    """Truly new candidate → no merge."""
    fix = load_fixture("true_new")
    expected = fix["expected_verdict"]
    transcripts = _ingest_fixture_transcripts(fix["past_transcripts"])
    transcript_call_id = next(iter(fix["past_transcripts"].keys()))
    monkeypatch.setattr(
        "backend.services.topic_verification._call_llm",
        _mock_verify_new_response(expected["verdict"], expected["matched_topic_id"], transcript_call_id),
    )
    out = await run_verify_new(
        candidate=fix["candidate"],
        project_topics=fix["project_topics"],
        transcripts=transcripts,
        llm="x",
        model="y",
    )
    assert out["verdict"] == "truly_new"
    assert out["matched_topic_id"] is None
    assert out["confidence"]["pct"] >= expected["min_confidence"]


async def test_fixture_mega_topic(monkeypatch):
    """Mega-topic spanning multiple existing — picks best single match (proj-arch)."""
    fix = load_fixture("mega_topic")
    expected = fix["expected_verdict"]
    transcripts = _ingest_fixture_transcripts(fix["past_transcripts"])
    transcript_call_id = next(iter(fix["past_transcripts"].keys()))
    monkeypatch.setattr(
        "backend.services.topic_verification._call_llm",
        _mock_verify_new_response(expected["verdict"], expected["matched_topic_id"], transcript_call_id),
    )
    out = await run_verify_new(
        candidate=fix["candidate"],
        project_topics=fix["project_topics"],
        transcripts=transcripts,
        llm="x",
        model="y",
    )
    assert out["verdict"] == expected["verdict"]
    assert out["matched_topic_id"] == expected["matched_topic_id"]
    assert out["confidence"]["pct"] >= expected["min_confidence"]


async def test_fixture_wrong_canonical(monkeypatch):
    """v5 canonical match was wrong → wrong_canonical_belongs_elsewhere."""
    fix = load_fixture("wrong_canonical")
    expected = fix["expected_verdict"]
    transcripts = _ingest_fixture_transcripts(fix["past_transcripts"])
    transcript_call_id = next(iter(fix["past_transcripts"].keys()))
    monkeypatch.setattr(
        "backend.services.topic_verification._call_llm",
        _mock_canonical_match_response(
            expected["verdict"], expected["matched_topic_id"], transcript_call_id
        ),
    )
    # matched_topic is the topic v5 claimed — candidate.name == "ARM" → proj-arm
    matched_topic = next(
        (p for p in fix["project_topics"] if p["name"] == fix["candidate"]["name"]),
        fix["project_topics"][0],
    )
    out = await run_verify_canonical_match(
        candidate=fix["candidate"],
        matched_topic=matched_topic,
        all_project_topics=fix["project_topics"],
        transcripts=transcripts,
        llm="x",
        model="y",
    )
    assert out["verdict"] == expected["verdict"]
    assert out["alternative_topic_id"] == expected["matched_topic_id"]
    assert out["needs_manual_review"] is False


async def test_fixture_naming_drift(monkeypatch):
    """Candidate has drifted name but semantically matches existing topic."""
    fix = load_fixture("naming_drift")
    expected = fix["expected_verdict"]
    transcripts = _ingest_fixture_transcripts(fix["past_transcripts"])
    transcript_call_id = next(iter(fix["past_transcripts"].keys()))
    monkeypatch.setattr(
        "backend.services.topic_verification._call_llm",
        _mock_verify_new_response(expected["verdict"], expected["matched_topic_id"], transcript_call_id),
    )
    out = await run_verify_new(
        candidate=fix["candidate"],
        project_topics=fix["project_topics"],
        transcripts=transcripts,
        llm="x",
        model="y",
    )
    assert out["verdict"] == expected["verdict"]
    assert out["matched_topic_id"] == expected["matched_topic_id"]
    assert out["confidence"]["pct"] >= expected["min_confidence"]
