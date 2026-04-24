from backend.templates.agenda_skeleton import render as render_agenda
from backend.templates.decisions_digest import render as render_decisions
from backend.templates.next_steps import render as render_next_steps
from backend.templates.questions_list import render as render_questions
from backend.templates.registry import TEMPLATE_REGISTRY
from backend.templates.risk_register import render as render_risk


def _topic(name, **kwargs):
    return {
        "name": name,
        "summary": kwargs.get("summary", ""),
        "follow_up_items": kwargs.get("follow_up_items", []),
        "decisions": kwargs.get("decisions", []),
        "open_questions": kwargs.get("open_questions", []),
        "status": kwargs.get("status", "open"),
        "owner": kwargs.get("owner", "Us"),
        "sentiment": kwargs.get("sentiment", "neutral"),
        "is_parked": kwargs.get("is_parked", False),
        "importance": kwargs.get("importance", "medium"),
        "rationale": kwargs.get("rationale", ""),
        "transcript_excerpt": kwargs.get("transcript_excerpt"),
    }


def test_next_steps_groups_by_topic_with_owner_bolded():
    topics = [
        _topic(
            "Risk model selection",
            follow_up_items=["Nick: run benchmark", "Hassan: share EDS+ evidence"],
        ),
        _topic("Meeting logistics"),  # no actions — should show placeholder, not skip
    ]
    out = render_next_steps(topics)
    assert "# Next Steps" in out
    assert "## Risk model selection" in out
    assert "- **Nick:** run benchmark" in out
    assert "- **Hassan:** share EDS+ evidence" in out
    assert "## Meeting logistics" in out  # still rendered
    assert "_No action expected._" in out  # placeholder when no actions


def test_next_steps_handles_action_without_owner_prefix():
    topics = [_topic("X", follow_up_items=["Review the contract"])]
    out = render_next_steps(topics)
    assert "- Review the contract" in out  # no bold prefix


def test_next_steps_empty_topics_returns_placeholder():
    assert render_next_steps([]) == "_No action items captured._"


def test_questions_list_groups_by_topic():
    topics = [
        _topic(
            "Model selection",
            open_questions=["Does MC Mac handle caching?", "Can FV Mac split?"],
        ),
        _topic("Budget"),  # no questions — skipped
    ]
    out = render_questions(topics)
    assert "## Model selection" in out
    assert "- Does MC Mac handle caching?" in out
    assert "- Can FV Mac split?" in out
    assert "Budget" not in out


def test_agenda_skeleton_only_open_or_in_progress():
    topics = [
        _topic("A", status="open", sentiment="concern"),
        _topic("B", status="in_progress", sentiment="neutral"),
        _topic("C", status="resolved"),  # excluded
    ]
    out = render_agenda(topics)
    assert "A" in out
    assert "B" in out
    assert "C" not in out


def test_agenda_skeleton_sorts_concern_first():
    topics = [
        _topic("Neutral item", status="open", sentiment="neutral"),
        _topic("Concern item", status="open", sentiment="concern"),
    ]
    out = render_agenda(topics)
    # Concern item should appear before neutral item
    assert out.find("Concern item") < out.find("Neutral item")


def test_risk_register_filters_concern_or_parked():
    topics = [
        _topic("Neutral", sentiment="neutral"),  # excluded
        _topic("Concern item", sentiment="concern", summary="This is a concern."),
        _topic("Parked item", is_parked=True, summary="Parked for later."),
    ]
    out = render_risk(topics)
    assert "Neutral" not in out
    assert "Concern item" in out
    assert "Parked item" in out
    assert "⏸ PARKED" in out  # parked chip in markdown


def test_decisions_digest_flattens_all_decisions():
    topics = [
        _topic("T1", decisions=["Decision 1", "Decision 2"]),
        _topic("T2", decisions=["Decision 3"]),
        _topic("T3"),  # no decisions — skipped
    ]
    out = render_decisions(topics)
    assert "## T1" in out
    assert "- Decision 1" in out
    assert "- Decision 2" in out
    assert "## T2" in out
    assert "- Decision 3" in out
    assert "T3" not in out


def test_registry_maps_all_five_templates():
    assert set(TEMPLATE_REGISTRY.keys()) == {
        "next_steps",
        "questions_list",
        "agenda_skeleton",
        "risk_register",
        "decisions_digest",
    }
    for render_fn in TEMPLATE_REGISTRY.values():
        assert callable(render_fn)
