"""Render action items (follow_up_items) grouped by topic, with owner bolded."""

import re

_OWNER_PATTERN = re.compile(r"^([A-Z][a-z]+(?:\s[A-Z][a-z]+)?):\s*(.*)$")


def render(topics: list[dict], *, scope: str = "call") -> str:
    """Render markdown list of follow_up_items across topics, grouped by topic.

    Every topic gets a section so the reader sees full coverage of the call's
    topics. Topics without actions render "_No action expected._" as a placeholder.
    Owners inlined as prefix ("Nick: foo") are rendered as "- **Nick:** foo".
    """
    if not topics:
        return "_No action items captured._"

    lines: list[str] = ["# Next Steps & Action Items", ""]
    for t in topics:
        lines.append(f"## {t['name']}")
        actions = t.get("follow_up_items") or []
        if not actions:
            lines.append("_No action expected._")
        else:
            for a in actions:
                m = _OWNER_PATTERN.match(a)
                if m:
                    lines.append(f"- **{m.group(1)}:** {m.group(2)}")
                else:
                    lines.append(f"- {a}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
