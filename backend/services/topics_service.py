from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel


class TopicIn(BaseModel):
    """One topic as submitted by the frontend (save endpoint)."""
    name: str
    summary: str
    follow_up_items: list[str]
    decisions: list[str]
    status: Literal["open", "in_progress", "resolved"]
    owner: Literal["Us", "Client", "Both"]
    sentiment: Literal["positive", "neutral", "concern"]


class TopicUpdate(TopicIn):
    """TopicIn extended with DB identity + disposition for not-discussed topics."""
    topic_id: Optional[str] = None          # None → brand new topic
    disposition: Optional[Literal["keep_as_is", "archive"]] = None


class TopicOut(BaseModel):
    """One topic row as returned from DB queries."""
    id: str
    project_id: str
    name: str
    first_raised_call_id: Optional[str]
    calls_open: int
    archived: bool
    created_at: str
    # Latest update fields (populated from most recent topic_update row)
    summary: Optional[str] = None
    follow_up_items: list[str] = []
    decisions: list[str] = []
    status: Optional[str] = None
    owner: Optional[str] = None
    sentiment: Optional[str] = None


class BriefItem(BaseModel):
    topic_id: str
    name: str
    calls_open: int
    sentiment: str
    last_summary: str
    last_follow_up_items: list[str]


class BriefOut(BaseModel):
    priority_topics: list[BriefItem]
    decisions_to_confirm: list[dict]
    watch_list: list[BriefItem]
