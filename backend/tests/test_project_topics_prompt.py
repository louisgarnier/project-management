"""Structural tests for the rewritten project_topics merge prompt.

Background: until 2026-04-27 this prompt was a thin classification stub
("followed_up / not_discussed / new_topics") that was misused as merge
instructions inside run_merge_preview. It gave the LLM no guidance on
synthesis, dedup, status transitions, or lifecycle — so resolved topics
kept reappearing and follow-ups duplicated across calls.

The rewrite uses the same 5-block structure as call_topics
(ROLE / RUBRIC / ANCHORS / FEW-SHOT / PROCESS) and locks down lifecycle
behavior. These tests are guard rails so future edits can't silently drop
the rules that took an incident to surface.
"""

from backend.prompts.project_topics import (
    PROJECT_TOPICS_DEFAULT_PROMPT,
    OLD_DEFAULT_PROMPT_STRING,
)


def test_prompt_has_all_five_blocks():
    for block in ("[ROLE]", "[RUBRIC]", "[ANCHORS]", "[FEW-SHOT]", "[PROCESS]"):
        assert block in PROJECT_TOPICS_DEFAULT_PROMPT, f"Missing block: {block}"


def test_prompt_encodes_four_rubric_criteria():
    """The four merge criteria must all be named explicitly."""
    p = PROJECT_TOPICS_DEFAULT_PROMPT
    for criterion in ("COMPLETENESS", "CURRENCY", "NO DOUBLE-COUNTING", "LIFECYCLE"):
        assert criterion in p, f"Missing rubric criterion: {criterion}"


def test_prompt_specifies_status_recompute_rule():
    """status must be RECOMPUTED from the post-merge state, not copied
    from the existing topic. Without this, resolved topics keep showing up."""
    p = PROJECT_TOPICS_DEFAULT_PROMPT
    assert "RECOMPUTE" in p, "Missing status recompute instruction"
    assert "resolved" in p
    assert "in_progress" in p
    # The rule that drives close-out: no follow-ups + no open questions = resolved
    assert "no remaining follow_up_items" in p
    assert "no remaining open_questions" in p


def test_prompt_has_close_completed_action_rule():
    """Completed actions in this call must REMOVE from follow_up_items
    AND become decisions — not stay duplicated on both sides."""
    p = PROJECT_TOPICS_DEFAULT_PROMPT
    # The rule must be explicit about removal + decision capture
    assert "COMPLETED" in p
    assert "REMOVE from follow_up_items" in p
    # And similarly for answered open questions
    assert "ANSWERED" in p
    assert "REMOVE from open_questions" in p


def test_prompt_has_supersede_decision_rule():
    """A new decision that supersedes/refines an old one must drop the old."""
    p = PROJECT_TOPICS_DEFAULT_PROMPT
    assert "SUPERSEDES" in p
    assert "REFINES" in p


def test_prompt_preserves_existing_topic_name():
    """The merger must NOT rename — name is locked from the existing topic."""
    p = PROJECT_TOPICS_DEFAULT_PROMPT
    assert "do NOT rename" in p or "do not rename" in p.lower()


def test_prompt_few_shot_example_demonstrates_lifecycle():
    """The few-shot OUTPUT must show an answered question removed AND its
    answer captured as a decision — that's the headline behavior change."""
    p = PROJECT_TOPICS_DEFAULT_PROMPT
    # The example output must show open_questions: [] (closed out)
    assert '"open_questions": []' in p, (
        "Few-shot must demonstrate open_questions getting closed out"
    )
    # The example output must show status updated to in_progress (not stuck on 'open')
    assert '"status": "in_progress"' in p
    # And the LIFECYCLE TRACE must walk through what happened
    assert "LIFECYCLE TRACE" in p


def test_prompt_returns_single_topic_not_buckets():
    """Reinforces the merge_one contract — output is ONE topic dict, not
    the {followed_up, not_discussed, new_topics} bucket shape that the old
    classification prompt implied (and that hallucinations leaked earlier)."""
    p = PROJECT_TOPICS_DEFAULT_PROMPT
    assert "single topic" in p.lower() or "ONE topic" in p or "one topic" in p.lower()
    # The old classification verbs that caused the structural confusion are gone
    assert "classify each topic" not in p
    assert '"followed_up"' not in p


def test_old_prompt_string_frozen_for_migration_matching():
    """The pre-rewrite text must stay frozen so future migrations can detect
    unedited rows (same pattern as call_topics.OLD_DEFAULT_PROMPT_STRING)."""
    assert OLD_DEFAULT_PROMPT_STRING.startswith(
        "You are an expert at matching client call topics to an existing project topic backlog."
    )
    assert '"followed_up"' in OLD_DEFAULT_PROMPT_STRING
    assert '"not_discussed"' in OLD_DEFAULT_PROMPT_STRING
    assert '"new_topics"' in OLD_DEFAULT_PROMPT_STRING
