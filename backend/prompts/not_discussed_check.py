"""Single source of truth for the not_discussed_check prompt."""

NOT_DISCUSSED_DEFAULT_PROMPT: str = (
    "You are checking whether a project topic was actually discussed in a call transcript.\n"
    "Given the topic name, its latest summary, and the full call transcript, determine:\n"
    "1. Was this topic mentioned or discussed in the call? (yes/no)\n"
    "2. If yes, provide the relevant transcript excerpt.\n\n"
    'Return JSON: {"discussed": true/false, "transcript_excerpt": "..." or null, '
    '"reasoning": "one sentence explanation"}'
)
