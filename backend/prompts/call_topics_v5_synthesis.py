"""Stage 7 — per-topic task synthesis prompt.

For each topic, the LLM synthesizes the atomic units assigned to it into
structured tasks. Each task references back to atomic units via evidence_unit_ids.
Narrow context: only the topic's units are sent, not the full transcript.
"""

CALL_TOPICS_V5_SYNTHESIS_SYSTEM: str = """\
You are a structured task synthesizer. You receive a list of atomic units that
all belong to ONE topic. Your job: synthesize them into clear, structured task
objects. Each task references the atomic units it was synthesized from via
evidence_unit_ids.

Be faithful: do NOT invent content beyond what the atomic units say.
Output STRICT JSON only. Temperature is 0 — your output must be deterministic.
"""

CALL_TOPICS_V5_SYNTHESIS_USER_TEMPLATE: str = """\
TOPIC: {topic_name}
IMPORTANCE: {importance}

ATOMIC UNITS FOR THIS TOPIC (each with citation = verbatim transcript text):

{units_json}

TASK:
Synthesize these atomic units into structured tasks. Group related units into
a single task when they describe the same commitment. Split a unit into multiple
tasks if it actually contains multiple commitments.

EACH TASK MUST INCLUDE:
- `task`: short imperative description (2-6 words)
- `next_step`: one sentence on the next concrete action (empty string OK for tracking tasks)
- `owner`: person responsible, or "unassigned"
- `status`: "open" | "in_progress" | "resolved"
- `key_terms`: 2-5 anchoring terms specific to THIS task (acronyms, proper nouns, distinctive phrases)
- `open_questions`: array of {{text, owner, status}} for uncertainties UNDER this task (may be empty)
- `decisions`: array of {{text}} for explicit decisions UNDER this task (may be empty)
- `evidence_unit_ids`: REQUIRED — array of atomic unit_ids that this task was synthesized from. Must have ≥ 2 entries unless only 1 unit exists in this topic.

RULES:
1. Every atomic unit_id from the input must be referenced by AT LEAST ONE task's evidence_unit_ids.
2. A single unit MAY be referenced by multiple tasks if it contributes to multiple.
3. Do NOT generate citation strings yourself — citations are attached deterministically from evidence_unit_ids in Stage 8.

OUTPUT FORMAT (strict JSON array — top-level, NOT wrapped):

[
  {{
    "task": "Send hierarchy file",
    "next_step": "Mark to email by Friday",
    "owner": "Mark",
    "status": "open",
    "key_terms": ["hierarchy", "FactSet"],
    "open_questions": [],
    "decisions": [],
    "evidence_unit_ids": ["u_0001", "u_0007"]
  }},
  ...
]

Return ONLY the JSON array.
"""


def build_synthesis_user_message(
    topic_name: str,
    importance: str,
    units: list[dict],
) -> str:
    import json as _json
    return CALL_TOPICS_V5_SYNTHESIS_USER_TEMPLATE.format(
        topic_name=topic_name,
        importance=importance,
        units_json=_json.dumps(units, indent=2),
    )
