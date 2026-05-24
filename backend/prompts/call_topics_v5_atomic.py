"""Stage 2 — atomic unit extraction prompt (v5 pipeline).

The LLM's ONLY job at this stage: extract every meaningful atomic unit from
the transcript. No grouping, no summarization, no deduplication, no topic
assignment. Optimize for RECALL.

Each unit is anchored to a transcript line range. Code (Stage 4) resolves
the line range to verbatim citation text — the LLM never generates citations.
"""

CALL_TOPICS_V5_ATOMIC_SYSTEM: str = """\
You are a meticulous transcript analyst. Your job is to extract every meaningful
atomic unit from a numbered call transcript. You do NOT group, summarize, or
organize. You only extract. Optimize for RECALL: missing units is worse than
producing borderline-relevant ones.

Each line of the transcript is prefixed with [NNNN] — that's the line's
permanent identifier. You will reference line ranges using these identifiers.

Output STRICT JSON only. No markdown, no commentary, no surrounding prose.
"""

CALL_TOPICS_V5_ATOMIC_USER_TEMPLATE: str = """\
TRANSCRIPT (each line prefixed with [NNNN]):

{numbered_transcript}

{context_block}

TASK:
Extract every meaningful atomic unit from the transcript above. Each unit is
ONE of these types:

  - "task"      — a concrete action to be done (commitment to act)
  - "decision"  — an explicit agreement or decision made in the call
  - "question"  — an open question raised (uncertainty to resolve)
  - "blocker"   — an impediment identified
  - "statement" — a notable statement worth tracking that doesn't fit above

REQUIREMENTS:
1. RECALL FIRST. Capture every meaningful unit. Do NOT skip "small" items.
2. Each unit is anchored to a transcript line range via [start_line, end_line]
   integers (NOT strings, NOT with brackets). The range must contain the
   verbatim text supporting the unit.
3. Do NOT group units. Do NOT assign topics. Do NOT deduplicate.
4. Use the speaker's name as `owner` when the unit is clearly assigned to or
   raised by a specific person, else "unassigned".
5. `text` is a SHORT (≤ 20 words) paraphrased description of the unit. Not a
   quote. The verbatim quote comes from the line range.
6. Unit IDs are sequential strings: "u_0001", "u_0002", ... starting from u_0001.

OUTPUT FORMAT (strict JSON array, top-level array — NOT wrapped in any object):

[
  {{
    "unit_id": "u_0001",
    "type": "task",
    "text": "Send hierarchy file to FactSet",
    "owner": "Mark",
    "evidence_lines": [12, 18]
  }},
  {{
    "unit_id": "u_0002",
    "type": "decision",
    "text": "Weekly call moved to Monday 11am",
    "owner": "Nick",
    "evidence_lines": [55, 57]
  }},
  ...
]

Return ONLY the JSON array. No surrounding text.
"""


def build_atomic_system_prompt(project_context: str = "") -> str:
    """EPIC-18 S1.2: prime the LLM with project context if available.

    `project_context` comes from projects.context column — free-form notes
    the user provides about the project (e.g., "Portfolio risk analytics
    team using FactSet, Snowflake, Monte Carlo models").
    """
    base = CALL_TOPICS_V5_ATOMIC_SYSTEM
    if project_context.strip():
        context_block = (
            "\n\nPROJECT CONTEXT (background for this team/project — use it to "
            "disambiguate references in the transcript, but do not invent claims "
            "not present in the transcript):\n\n"
            f"{project_context.strip()}\n"
        )
        return base + context_block
    return base


def build_atomic_user_message(numbered_transcript: str, project_context: str = "") -> str:
    """Render the user message with the transcript + optional project context."""
    context_block = ""
    if project_context.strip():
        context_block = f"PROJECT CONTEXT (background, do not extract as units):\n{project_context.strip()}\n"
    return CALL_TOPICS_V5_ATOMIC_USER_TEMPLATE.format(
        numbered_transcript=numbered_transcript,
        context_block=context_block,
    )
