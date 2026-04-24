"""Render all decisions[] across topics, grouped by topic.

Every topic gets a section. Topics without decisions render a placeholder
so the reader sees full coverage.
"""


def render(topics: list[dict], *, scope: str = "call") -> str:
    if not topics:
        return "_No decisions captured._"

    lines: list[str] = ["# Decisions Digest", ""]
    if scope != "call":
        lines.append(f"_Scope: {scope}_")
        lines.append("")
    for t in topics:
        lines.append(f"## {t['name']}")
        decisions = t.get("decisions") or []
        if not decisions:
            lines.append("_No decisions recorded._")
        else:
            for d in decisions:
                lines.append(f"- {d}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
