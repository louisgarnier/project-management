"""Render open_questions grouped by topic."""


def render(topics: list[dict], *, scope: str = "call") -> str:
    if not topics:
        return "_No open questions captured._"

    lines: list[str] = ["# Questions for Stakeholders", ""]
    emitted = False
    for t in topics:
        questions = t.get("open_questions") or []
        if not questions:
            continue
        emitted = True
        lines.append(f"## {t['name']}")
        for q in questions:
            lines.append(f"- {q}")
        lines.append("")

    if not emitted:
        return "_No open questions captured._"
    return "\n".join(lines).rstrip() + "\n"
