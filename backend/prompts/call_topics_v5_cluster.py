"""Stage 5 — topic clustering prompt.

The LLM groups atomic units into topics. Each unit belongs to exactly ONE
topic. Prefers existing registry names. Flags new proposals.
"""

CALL_TOPICS_V5_CLUSTER_SYSTEM: str = """\
You are a domain-aware topic organizer. You receive a flat list of atomic
units and a controlled vocabulary of canonical topic names. You group the
units into topics. Every unit belongs to exactly one topic.

Prefer canonical names from the registry. Only propose a new topic name when
nothing in the registry fits. Output STRICT JSON only.
"""

CALL_TOPICS_V5_CLUSTER_USER_TEMPLATE: str = """\
ATOMIC UNITS (flat list, each with unit_id + type + text + owner + evidence_lines):

{units_json}

PROJECT TOPIC REGISTRY (canonical names — prefer these):

{registry_block}

TASK:
Group the atomic units into topics. Each unit MUST appear in exactly one topic.
Every unit_id from the input MUST appear somewhere in the output (no orphans).

RULES:
1. Use registry names verbatim when a registry topic fits the cluster.
2. Only propose a new topic name when nothing in the registry matches the
   cluster. Flag those with "new_topic": true.
3. Importance: "low" | "medium" | "high" — your subjective ranking based on
   how central the topic is to the call.

OUTPUT FORMAT (strict JSON array — top-level, NOT wrapped):

[
  {{
    "topic_name": "ARM",
    "unit_ids": ["u_0001", "u_0007", "u_0012"],
    "new_topic": false,
    "importance": "high"
  }},
  {{
    "topic_name": "Stress test framework",
    "unit_ids": ["u_0003", "u_0005"],
    "new_topic": true,
    "importance": "medium"
  }},
  ...
]

Return ONLY the JSON array.
"""


def build_cluster_user_message(units: list[dict], topic_registry: list[dict]) -> str:
    import json as _json
    if topic_registry:
        registry_lines = []
        for r in topic_registry:
            desc = r.get("description") or ""
            registry_lines.append(f"- {r['name']}" + (f" — {desc}" if desc else ""))
        registry_block = "\n".join(registry_lines)
    else:
        registry_block = "(empty — first call of the project. All topics will be new.)"
    return CALL_TOPICS_V5_CLUSTER_USER_TEMPLATE.format(
        units_json=_json.dumps(units, indent=2),
        registry_block=registry_block,
    )
