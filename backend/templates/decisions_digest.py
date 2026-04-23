"""Render all decisions[] across topics, grouped by topic."""


def render(topics: list[dict], *, scope: str = "call") -> str:
    emitted_any = False
    lines: list[str] = ["# Decisions Digest", ""]
    if scope != "call":
        lines.append(f"_Scope: {scope}_")
        lines.append("")
    for t in topics:
        decisions = t.get("decisions") or []
        if not decisions:
            continue
        emitted_any = True
        lines.append(f"## {t['name']}")
        for d in decisions:
            lines.append(f"- {d}")
        lines.append("")

    if not emitted_any:
        return "_No decisions captured._"
    return "\n".join(lines).rstrip() + "\n"
