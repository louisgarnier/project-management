from unittest.mock import MagicMock
from backend.services.llm_resolver import resolve_effective_llm_model


def test_type_args_are_ignored_project_wins():
    """Post-EPIC-16: type_llm + type_model are accepted for signature compat but ignored.
    The resolver always returns project_llm/project_model when set."""
    llm, model = resolve_effective_llm_model(
        type_llm="claude",
        type_model="claude-sonnet-4-6",
        project_llm="openrouter",
        project_model="deepseek/deepseek-v3.2",
    )
    assert llm == "openrouter"
    assert model == "deepseek/deepseek-v3.2"


def test_project_fills_when_type_null():
    llm, model = resolve_effective_llm_model(
        type_llm=None,
        type_model=None,
        project_llm="openrouter",
        project_model="deepseek/deepseek-v3.2",
    )
    assert llm == "openrouter"
    assert model == "deepseek/deepseek-v3.2"


def test_system_fills_when_both_null():
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"default_llm": "openrouter", "default_model": "deepseek/deepseek-v3.2"}
    ]
    llm, model = resolve_effective_llm_model(None, None, None, None, db=db)
    assert llm == "openrouter"
    assert model == "deepseek/deepseek-v3.2"
