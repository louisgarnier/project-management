"""Render topics with sentiment=concern OR is_parked=true as a risk register."""


def render(topics: list[dict], *, scope: str = "call") -> str:
    flagged = [
        t for t in topics if t.get("sentiment") == "concern" or t.get("is_parked")
    ]
    if not flagged:
        return "_No concerns or parked items captured._"

    lines: list[str] = ["# Risk Register", ""]
    for t in flagged:
        header = f"## {t['name']}"
        if t.get("is_parked"):
            header += " ⏸ PARKED"
        lines.append(header)
        summary = t.get("summary") or ""
        if summary:
            lines.append(summary)
        excerpt = t.get("transcript_excerpt") or ""
        if excerpt:
            lines.append("")
            lines.append(f"> {excerpt}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
