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


def test_prompt_enforces_dual_classify_for_investigations():
    """Follow-ups that investigate uncertainty must also yield an open_question.

    Regression guard: on 2026-04-24 the model conflated all investigative actions
    into follow_up_items and returned open_questions=[] for every topic in the
    "puoihug" project, breaking the questions_list artifact. The prompt must
    explicitly instruct dual-classification.
    """
    p = CALL_TOPICS_DEFAULT_PROMPT
    assert "DUAL-CLASSIFY" in p or "dual-classify" in p.lower(), (
        "Missing dual-classify rule"
    )
    # Rule must mention at least 2 of the investigative verbs and tie to open_questions
    verbs_present = sum(
        1 for v in ("investigate", "determine", "confirm", "validate", "check")
        if v in p.lower()
    )
    assert verbs_present >= 2, f"Dual-classify rule should list investigative verbs (found {verbs_present})"


def test_prompt_has_parked_few_shot_example():
    """A parked-item few-shot must exist so the model sees the expected shape
    (is_parked=true, empty decisions/follow-ups, at least one open_question)."""
    p = CALL_TOPICS_DEFAULT_PROMPT
    assert '"is_parked": true' in p, "Missing parked few-shot with is_parked=true"
    # The parked few-shot must include open_questions as the signal anchor
    parked_block_start = p.find('"is_parked": true')
    # Scan 400 chars around it for an open_questions entry that's non-empty
    window = p[max(0, parked_block_start - 400): parked_block_start + 200]
    assert '"open_questions"' in window, "Parked example must include open_questions"
    # Empty array "[]" adjacent to open_questions would defeat the point
    assert '"open_questions": []' not in window, (
        "Parked example must have a populated open_questions, not an empty array"
    )


def test_old_prompt_string_is_frozen_snapshot():
    """The old default must start with the pre-migration text for migration matching."""
    assert OLD_DEFAULT_PROMPT_STRING.startswith(
        "You are an expert at analysing business call transcripts. Extract every distinct topic discussed"
    )
