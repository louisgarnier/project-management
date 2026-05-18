from unittest.mock import MagicMock

from backend.prompts.call_topics import (
    CALL_TOPICS_V2_PROMPT_BODY as CALL_TOPICS_DEFAULT_PROMPT,
    OLD_DEFAULT_PROMPT_STRING,
)
from backend.scripts.migrate_call_topics_prompt import migrate_prompts


def test_migrates_only_unedited_rows():
    """Rows whose prompt equals OLD_DEFAULT_PROMPT_STRING should be updated.
    Customized rows should be left alone."""
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": "row1", "prompt": OLD_DEFAULT_PROMPT_STRING, "project_id": "p1"},
        {"id": "row2", "prompt": "my custom edited prompt", "project_id": "p2"},
        {"id": "row3", "prompt": OLD_DEFAULT_PROMPT_STRING, "project_id": "p3"},
    ]

    result = migrate_prompts(db)

    assert result == {"migrated": 2, "preserved": 1}
    # Verify update called twice with the new prompt
    update_calls = db.table.return_value.update.call_args_list
    assert len(update_calls) == 2
    for call in update_calls:
        assert call.args[0] == {"prompt": CALL_TOPICS_DEFAULT_PROMPT}


def test_empty_project_list_returns_zero_counts():
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = (
        []
    )
    result = migrate_prompts(db)
    assert result == {"migrated": 0, "preserved": 0}
