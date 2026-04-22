"""Single source of truth for default artifact-type prompts (per-type bundle)."""

DEFAULT_ARTIFACTS: list[dict] = [
    {
        "name": "Executive Summary",
        "prompt": (
            "Write a concise executive summary of this call in 3–5 bullet points. "
            "Use the Topics section to structure your summary around the key themes discussed. "
            "For each bullet: state the topic, what was decided or discussed, and its current status (open/resolved). "
            "Focus on decisions made, key outcomes, and overall direction."
        ),
    },
    {
        "name": "Next Steps & Action Items",
        "prompt": (
            "Extract all action items and next steps from this call. "
            "Group them by topic (use the Topics section as your guide). "
            "For each item state: the topic it belongs to, what needs to be done, "
            "who is responsible (Us / Client / Both), and any deadline discussed. "
            "Prioritise items from topics with sentiment=concern or status=open."
        ),
    },
    {
        "name": "Questions for Stakeholders",
        "prompt": (
            "List all open questions that remain unanswered after this call. "
            "Group them by topic (use the Topics section). "
            "For each question: state the topic, the question, and why it is blocking progress. "
            "Prioritise questions from topics that are open or in_progress."
        ),
    },
    {
        "name": "Email Summary (1-pager)",
        "prompt": (
            "Write a professional 1-page email summarising this call for the client. "
            "Structure it around the topics discussed (use the Topics section). "
            "For each topic: briefly state what was discussed, any decisions made, and follow-up items. "
            "Close with a consolidated next steps section. "
            "Tone: clear and business-professional."
        ),
    },
    {
        "name": "Email Follow-up (pre-next-call)",
        "prompt": (
            "Write a short follow-up email to send before the next call. "
            "For each open topic (from the Topics section), summarise: what was agreed, "
            "what each party should have completed before the next session, and what remains open. "
            "End with a proposed agenda for the next call based on in_progress and open topics."
        ),
    },
    {
        "name": "Next Call Meeting Invite Topics",
        "prompt": (
            "Generate a structured agenda for the next call. "
            "Base it on the Topics section: include all open and in_progress topics, "
            "ordered by priority (concern sentiment first, then by calls_open descending). "
            "For each agenda item: topic name, brief context (1 sentence), and the specific question or decision needed."
        ),
    },
]
