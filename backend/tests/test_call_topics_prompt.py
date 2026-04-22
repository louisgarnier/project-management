from backend.prompts.call_topics import (
    CALL_TOPICS_DEFAULT_PROMPT,
    OLD_DEFAULT_PROMPT_STRING,
)


def test_prompt_has_all_five_blocks():
    """The new prompt must contain the 5 named blocks: ROLE, RUBRIC, ANCHORS, FEW-SHOT, PROCESS."""
    for block in ("[ROLE]", "[RUBRIC]", "[ANCHORS]", "[FEW-SHOT]", "[PROCESS]"):
        assert block in CALL_TOPICS_DEFAULT_PROMPT, f"Missing block: {block}"


def test_prompt_encodes_3_of_4_rubric():
    """The rubric must mention the 3-of-4 threshold and the 4 criteria by name."""
    p = CALL_TOPICS_DEFAULT_PROMPT
    assert "3 of" in p or "at least 3" in p.lower()
    for word in ("FORWARD LIFE", "ANCHOR", "SPECIFICITY", "DIALOGUE DEPTH"):
        assert word in p, f"Missing rubric criterion: {word}"


def test_prompt_encodes_three_anchor_types():
    """The prompt must distinguish decisions, follow_up_items, and open_questions."""
    for field in ("decisions", "follow_up_items", "open_questions"):
        assert field in CALL_TOPICS_DEFAULT_PROMPT, f"Missing anchor field: {field}"


def test_prompt_includes_parked_instruction():
    """Parked-item handling must be documented in the prompt."""
    assert "is_parked" in CALL_TOPICS_DEFAULT_PROMPT


def test_old_prompt_string_is_frozen_snapshot():
    """The old default must start with the pre-migration text for migration matching."""
    assert OLD_DEFAULT_PROMPT_STRING.startswith(
        "You are an expert at analysing business call transcripts. Extract every distinct topic discussed"
    )
