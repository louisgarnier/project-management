"""Single source of truth for the project_topics (per-topic merge base instructions) prompt."""

PROJECT_TOPICS_DEFAULT_PROMPT: str = (
    "You are an expert at matching client call topics to an existing project topic backlog.\n\n"
    "Given topics extracted from the current call and the existing project topic list, "
    "classify each topic:\n"
    '- "followed_up": call topics that match an existing project topic (same business subject, '
    "possibly different wording). Use the existing topic name exactly. Update summary, status, "
    "follow_up_items, and decisions with new information from this call.\n"
    '- "not_discussed": existing project topics not covered by any call topic.\n'
    '- "new_topics": call topics with no match in the existing project list.\n\n'
    "Be generous with matching — slightly different wording for the same business subject "
    "counts as a match."
)
