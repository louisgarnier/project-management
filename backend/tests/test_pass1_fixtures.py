"""EPIC-18 STREAM 3 — Pass 1 fixture-driven tests (mocked LLM)."""
import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "pass1"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


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
