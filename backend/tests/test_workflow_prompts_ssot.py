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


def test_defaults_include_openrouter_model_where_recommended():
    """Per spec §4.4.4 + §7 Q4 — call_topics + merge_verification default to
    openrouter + anthropic/claude-sonnet-4.6 for new projects.
    not_discussed_check defaults to google/gemini-2.5-pro.
    project_topics stays provider-agnostic (no model required)."""
    assert DEFAULT_CALL_TOPICS_PROMPT["llm"] == "openrouter"
    assert DEFAULT_CALL_TOPICS_PROMPT["model"] == "anthropic/claude-sonnet-4.6"
    assert DEFAULT_MERGE_VERIFICATION_PROMPT["llm"] == "openrouter"
    assert DEFAULT_MERGE_VERIFICATION_PROMPT["model"] == "anthropic/claude-sonnet-4.6"
    assert DEFAULT_NOT_DISCUSSED_CHECK_PROMPT["llm"] == "openrouter"
    assert DEFAULT_NOT_DISCUSSED_CHECK_PROMPT["model"] == "google/gemini-2.5-pro"
