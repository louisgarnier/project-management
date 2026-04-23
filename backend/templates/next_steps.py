"""Render action items (follow_up_items) grouped by topic, with owner bolded."""

import re

_OWNER_PATTERN = re.compile(r"^([A-Z][a-z]+(?:\s[A-Z][a-z]+)?):\s*(.*)$")


def render(topics: list[dict], *, scope: str = "call") -> str:
    """Render markdown list of follow_up_items across topics, grouped by topic.

    Owners inlined as prefix ("Nick: foo") are rendered as "- **Nick:** foo".
    Topics with no actions are skipped. Empty input returns a placeholder.
    """
    if not topics:
        return "_No action items captured._"

    lines: list[str] = ["# Next Steps & Action Items", ""]
    emitted = False
    for t in topics:
        actions = t.get("follow_up_items") or []
        if not actions:
            continue
        emitted = True
        lines.append(f"## {t['name']}")
        for a in actions:
            m = _OWNER_PATTERN.match(a)
            if m:
                lines.append(f"- **{m.group(1)}:** {m.group(2)}")
            else:
                lines.append(f"- {a}")
        lines.append("")

    if not emitted:
        return "_No action items captured._"
    return "\n".join(lines).rstrip() + "\n"
