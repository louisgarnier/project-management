from backend.prompts.call_topics import CALL_TOPICS_DEFAULT_PROMPT
from backend.prompts.merge_verification import MERGE_VERIFICATION_DEFAULT_PROMPT
from backend.prompts.not_discussed_check import NOT_DISCUSSED_DEFAULT_PROMPT
from backend.prompts.project_topics import PROJECT_TOPICS_DEFAULT_PROMPT
from backend.routers.artifact_types import (
    DEFAULT_CALL_TOPICS_PROMPT,
    DEFAULT_MERGE_VERIFICATION_PROMPT,
    DEFAULT_NOT_DISCUSSED_CHECK_PROMPT,
    DEFAULT_PROJECT_TOPICS_PROMPT,
)


def test_seeds_reference_constants():
    assert DEFAULT_CALL_TOPICS_PROMPT["prompt"] == CALL_TOPICS_DEFAULT_PROMPT
    assert DEFAULT_PROJECT_TOPICS_PROMPT["prompt"] == PROJECT_TOPICS_DEFAULT_PROMPT
    assert (
        DEFAULT_MERGE_VERIFICATION_PROMPT["prompt"] == MERGE_VERIFICATION_DEFAULT_PROMPT
    )
    assert DEFAULT_NOT_DISCUSSED_CHECK_PROMPT["prompt"] == NOT_DISCUSSED_DEFAULT_PROMPT


def test_defaults_inherit_system_settings():
    """EPIC-12: all four Tier-1 workflow prompts now seed with llm=None/model=None
    so they inherit from the three-tier cascade (project default → system default).
    project_topics was already None/None; the others were flipped in this story."""
    assert DEFAULT_CALL_TOPICS_PROMPT["llm"] is None
    assert DEFAULT_CALL_TOPICS_PROMPT["model"] is None
    assert DEFAULT_MERGE_VERIFICATION_PROMPT["llm"] is None
    assert DEFAULT_MERGE_VERIFICATION_PROMPT["model"] is None
    assert DEFAULT_NOT_DISCUSSED_CHECK_PROMPT["llm"] is None
    assert DEFAULT_NOT_DISCUSSED_CHECK_PROMPT["model"] is None
    assert DEFAULT_PROJECT_TOPICS_PROMPT["llm"] is None
    assert DEFAULT_PROJECT_TOPICS_PROMPT["model"] is None
