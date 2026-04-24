"""Render open_questions grouped by topic.

Every topic gets a section. Topics without open questions render a
placeholder so the reader sees full coverage of the call's topics.
"""


def render(topics: list[dict], *, scope: str = "call") -> str:
    if not topics:
        return "_No open questions captured._"

    lines: list[str] = ["# Questions for Stakeholders", ""]
    for t in topics:
        lines.append(f"## {t['name']}")
        questions = t.get("open_questions") or []
        if not questions:
            lines.append("_No open questions._")
        else:
            for q in questions:
                lines.append(f"- {q}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
