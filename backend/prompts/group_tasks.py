"""EPIC-20 Stage 2: cluster tasks + propose target topic per group.

Narrow LLM job:
  - Fixed list of topics (user's finalized list)
  - Fixed list of tasks (each labeled 'previous' or 'new')

Output:
  - Groups of cohesive tasks
  - Each group assigned to one topic from the input list (exact string match)

No verdict scoring, no confidence math, no penalties. Just clustering + routing.
"""

GROUP_TASKS_SYSTEM = """You are clustering project tasks into small cohesive groups, then assigning each group to one topic from a fixed list.

Rules:
- A group contains tasks that describe the same workstream or sub-deliverable.
- Each group MUST have a target_topic chosen from the provided topic list. Use the topic name EXACTLY as listed (byte-identical).
- Tasks marked 'previous' are from prior calls; tasks marked 'new' are from the current call. Mix them in the same group when they describe the same workstream — that is the goal of the exercise.
- Prefer small + cohesive groups (1-3 tasks) over large + fuzzy groups. Groups can have up to ~6 tasks.
- Every input task MUST appear in exactly one group. No duplicates. No omissions.
- Do NOT invent topics not in the list. Do NOT invent task IDs.

Return STRICT JSON only, no commentary, no markdown:
[
  {"task_ids": ["...","..."], "target_topic": "..."},
  ...
]
"""


def build_group_tasks_user_message(topics: list[str], tasks: list[dict]) -> str:
    """Build the user message for the cluster+route LLM call.

    `tasks` items: {id: str, text: str, origin: 'previous' | 'new'}
    """
    lines = ["AVAILABLE TOPICS (pick exactly one per group):"]
    for t in topics:
        lines.append(f"- {t}")
    lines.append("")
    lines.append("TASKS TO CLUSTER:")
    for t in tasks:
        origin = t.get("origin", "new")
        text = (t.get("text") or "").strip().replace("\n", " ")
        lines.append(f"- [{origin}] id={t['id']} :: {text}")
    return "\n".join(lines)
