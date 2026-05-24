"""Stage 5 — topic clustering prompt.

The LLM groups atomic units into topics. Each unit belongs to exactly ONE
topic. Prefers existing registry names. Flags new proposals.
"""

CALL_TOPICS_V5_CLUSTER_SYSTEM: str = """\
You are a domain-aware topic organizer. You receive:
  (1) a flat list of atomic units from one call
  (2) a controlled vocabulary of canonical project topics, each annotated
      with its existing tasks + key terms

Group the units into topics. Every unit belongs to exactly one topic.

When deciding whether a unit fits an existing topic, compare its text against
that topic's EXISTING TASKS and KEY TERMS — not just the topic name. A unit
matches an existing topic when its work continues, extends, or follows up on
what's already tracked there.

Only propose a new topic name when nothing in the registry's existing work
naturally absorbs the unit. Output STRICT JSON only.
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


def build_cluster_system_prompt(project_context: str = "") -> str:
    """EPIC-18 S1.2: prime the LLM with project context if available."""
    base = CALL_TOPICS_V5_CLUSTER_SYSTEM
    if project_context.strip():
        context_block = (
            "\n\nPROJECT CONTEXT (background for this team/project — use it to "
            "disambiguate references in the transcript, but do not invent claims "
            "not present in the transcript):\n\n"
            f"{project_context.strip()}\n"
        )
        return base + context_block
    return base


def build_cluster_user_message(units: list[dict], topic_registry: list[dict]) -> str:
    """EPIC-18 V5-CORE: registry block now includes structural payload
    (key_terms + tasks) per topic, not just names. Lets the LLM cluster
    against real existing work, not guess from topic names alone.
    """
    import json as _json
    if topic_registry:
        registry_lines = []
        for r in topic_registry:
            block = [f"- {r['name']}"]
            desc = r.get("description") or ""
            if desc:
                block.append(f"    Description: {desc}")
            kts = r.get("key_terms") or []
            if kts:
                block.append(f"    Key terms: {', '.join(kts)}")
            tasks = r.get("tasks") or []
            if tasks:
                block.append("    Existing tasks:")
                for t in tasks[:10]:  # cap to keep prompt bounded
                    task_text = (t.get("task") or "").strip()
                    owner = (t.get("owner") or "").strip()
                    suffix = f" ({owner})" if owner and owner != "unassigned" else ""
                    block.append(f"      - {task_text}{suffix}")
                if len(tasks) > 10:
                    block.append(f"      … {len(tasks)-10} more")
            registry_lines.append("\n".join(block))
        registry_block = "\n\n".join(registry_lines)
    else:
        registry_block = "(empty — first call of the project. All topics will be new.)"
    return CALL_TOPICS_V5_CLUSTER_USER_TEMPLATE.format(
        units_json=_json.dumps(units, indent=2),
        registry_block=registry_block,
    )
