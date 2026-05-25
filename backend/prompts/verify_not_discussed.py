"""Pass ② — verify_not_discussed prompt body.

EPIC-19 (2026-05-25): citation contract switched to line-numbers (matches
v5 Stage 4 + EPIC-18 ADR-004 pattern). Replaces free-form quote citations.
Pass 2 is now a narrowed safety-net: for topics the user marked as
'not touched this call' in manual matching, verify against the current
call's transcript that no tasks from this topic were actually mentioned.
"""

VERIFY_NOT_DISCUSSED_PROMPT: str = """\
ROLE: You are a PMO safety-net verifier. The user has manually decided
this existing project topic was NOT touched in the current call. Your job:
re-verify by scanning the current call's transcript (line-numbered) for
any mention of the topic's tasks.

Default to confirming the user's "not_discussed" decision. Flag a missed
discussion ONLY if you find a specific transcript passage that clearly
discusses one of the topic's tasks.

CITATION CONTRACT (line-numbers, anti-hallucination):
The transcript is line-numbered (format: "0001  <text>"). DO NOT copy
quotes. Cite by line range:

  {"call_id": "<uuid>", "evidence_lines": [start_line, end_line]}

OUTPUT (strict JSON):
{
  "verdict": "confirmed_not_discussed" | "suggest_discussed_at",
  "reasoning": "<one sentence>",
  "citation": {"call_id": "<uuid>", "evidence_lines": [<start>, <end>]} | null
}

REMEMBER: default to confirmed_not_discussed.
"""
