"""Tests for _apply_lifecycle_on_resolve helper (Story 15.7)."""

from backend.services.topics_service import _apply_lifecycle_on_resolve


CALL_A = "aaaaaaaa-0000-0000-0000-000000000001"
CALL_B = "bbbbbbbb-0000-0000-0000-000000000002"
CALL_C = "cccccccc-0000-0000-0000-000000000003"


def test_open_to_resolved_stamps_closed_in_call_id():
    prev = [{"task_id": "t1", "status": "open"}]
    new = [{"task_id": "t1", "status": "resolved"}]
    out = _apply_lifecycle_on_resolve(prev, new, current_call_id=CALL_B)
    assert out[0]["closed_in_call_id"] == CALL_B


def test_resolved_to_open_clears_closed_in_call_id():
    prev = [{"task_id": "t1", "status": "resolved", "closed_in_call_id": CALL_A}]
    new = [{"task_id": "t1", "status": "open"}]
    out = _apply_lifecycle_on_resolve(prev, new, current_call_id=CALL_B)
    assert out[0]["closed_in_call_id"] is None


def test_re_resolve_overwrites_with_latest_call_id():
    """open → resolved (A) → open → resolved (C) ends with closed_in=C."""
    # First resolve at A:
    prev1 = [{"task_id": "t1", "status": "open"}]
    new1 = [{"task_id": "t1", "status": "resolved"}]
    after_A = _apply_lifecycle_on_resolve(prev1, new1, current_call_id=CALL_A)
    assert after_A[0]["closed_in_call_id"] == CALL_A

    # Reopen at B:
    new2 = [{"task_id": "t1", "status": "open"}]
    after_B = _apply_lifecycle_on_resolve(after_A, new2, current_call_id=CALL_B)
    assert after_B[0]["closed_in_call_id"] is None

    # Re-resolve at C — latest wins:
    new3 = [{"task_id": "t1", "status": "resolved"}]
    after_C = _apply_lifecycle_on_resolve(after_B, new3, current_call_id=CALL_C)
    assert after_C[0]["closed_in_call_id"] == CALL_C


def test_new_item_resolved_immediately_stamps_current_call():
    """Item appears for first time already in 'resolved' status → stamp."""
    prev = []
    new = [{"task_id": "t-new", "status": "resolved"}]
    out = _apply_lifecycle_on_resolve(prev, new, current_call_id=CALL_B)
    assert out[0]["closed_in_call_id"] == CALL_B


def test_open_questions_use_id_key_not_task_id():
    """Helper handles open_questions where the id key is 'id' not 'task_id'."""
    prev = [{"id": "q1", "status": "open"}]
    new = [{"id": "q1", "status": "resolved"}]
    out = _apply_lifecycle_on_resolve(prev, new, current_call_id=CALL_B)
    assert out[0]["closed_in_call_id"] == CALL_B


def test_unchanged_status_preserves_existing_closed_in_call_id():
    """Item with status=resolved in both prev and new keeps its existing closed_in_call_id."""
    prev = [{"task_id": "t1", "status": "resolved", "closed_in_call_id": CALL_A}]
    new = [{"task_id": "t1", "status": "resolved", "closed_in_call_id": CALL_A}]
    out = _apply_lifecycle_on_resolve(prev, new, current_call_id=CALL_B)
    # Should NOT overwrite — prev was already resolved
    assert out[0]["closed_in_call_id"] == CALL_A


def test_does_not_mutate_input():
    """The helper returns a new list of new dicts — does not modify inputs."""
    prev = [{"task_id": "t1", "status": "open"}]
    new = [{"task_id": "t1", "status": "resolved"}]
    prev_snapshot = [dict(p) for p in prev]
    new_snapshot = [dict(n) for n in new]
    _apply_lifecycle_on_resolve(prev, new, current_call_id=CALL_B)
    assert prev == prev_snapshot
    assert new == new_snapshot
