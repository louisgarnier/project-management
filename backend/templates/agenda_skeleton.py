"""Render open/in_progress topics as agenda bullets; hybrid artifacts wrap this
with LLM-generated intro + closing prose."""

_SENTIMENT_RANK = {"concern": 0, "neutral": 1, "positive": 2}


def render(topics: list[dict], *, scope: str = "call") -> str:
    eligible = [t for t in topics if t.get("status") in ("open", "in_progress")]
    eligible.sort(
        key=lambda t: (
            _SENTIMENT_RANK.get(t.get("sentiment", "neutral"), 1),
            -(t.get("calls_open") or 0),
        )
    )

    if not eligible:
        return "_No open topics to discuss._"

    lines: list[str] = ["# Agenda for Next Meeting", ""]
    for i, t in enumerate(eligible, 1):
        status = (t.get("status") or "").replace("_", " ")
        sentiment = t.get("sentiment") or ""
        lines.append(f"{i}. **{t['name']}** · {status} · {sentiment}")
        summary = t.get("summary") or ""
        if summary:
            first_sentence = summary.split(". ")[0].rstrip(".")
            lines.append(f"   Context: {first_sentence}.")
        first_question = (t.get("open_questions") or [None])[0]
        if first_question:
            lines.append(f"   Open question: {first_question}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
