"""Stage 3 — adversarial recall pass prompt.

Second LLM call. Same numbered transcript + the Stage 2 units. The model
acts as a critic: "what did we miss?" Returns only NEW units. Same schema
as Stage 2.
"""

CALL_TOPICS_V5_RECALL_SYSTEM: str = """\
You are a critical second-pass transcript reviewer. A previous extractor
produced a list of atomic units from a transcript. Your ONLY job is to
identify what was MISSED — meaningful units present in the transcript that
the previous extractor did not capture.

Be adversarial. Be thorough. Return ONLY new units, not the existing ones.

Output STRICT JSON only. No markdown, no commentary.
"""

CALL_TOPICS_V5_RECALL_USER_TEMPLATE: str = """\
TRANSCRIPT (each line prefixed with [NNNN]):

{numbered_transcript}

ALREADY-EXTRACTED UNITS:

{existing_units_json}

TASK:
Review the transcript carefully. Find every meaningful atomic unit that the
previous extractor MISSED. A unit is meaningful if it's a:
  - task (action commitment)
  - decision (explicit agreement)
  - question (open uncertainty raised)
  - blocker (impediment)
  - statement (notable item worth tracking)

RULES:
1. Return ONLY new units. Do NOT re-emit any unit already in the list above.
2. Same schema as the existing units. Continue the unit_id sequence starting
   at u_{next_seq}.
3. Anchor every new unit to a transcript line range [start, end] integers.
4. Owner = speaker's name when assigned/raised by a specific person, else "unassigned".
5. If nothing was missed, return an empty array: []

OUTPUT FORMAT (strict JSON array — top-level array, NOT wrapped):

[
  {{
    "unit_id": "u_{next_seq}",
    "type": "decision",
    "text": "Brief paraphrase, ≤ 20 words",
    "owner": "Name or unassigned",
    "evidence_lines": [start_int, end_int]
  }},
  ...
]

Return ONLY the JSON array.
"""


def build_recall_user_message(numbered_transcript: str, existing_units: list[dict]) -> str:
    """Render the recall pass user message."""
    import json as _json
    # Compute next sequence id ("u_NNNN")
    next_seq_int = 1
    for u in existing_units:
        uid = u.get("unit_id") or ""
        if uid.startswith("u_"):
            try:
                next_seq_int = max(next_seq_int, int(uid[2:]) + 1)
            except ValueError:
                pass
    next_seq = f"{next_seq_int:04d}"
    return CALL_TOPICS_V5_RECALL_USER_TEMPLATE.format(
        numbered_transcript=numbered_transcript,
        existing_units_json=_json.dumps(existing_units, indent=2),
        next_seq=next_seq,
    )
