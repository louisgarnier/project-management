"""Verbatim-quote post-verifier for RAG citations."""


def verify_citations(citations: list[dict], transcripts_by_call: dict[str, str]) -> tuple[bool, list[str]]:
    """For each citation, check the quote appears verbatim in the cited call's transcript.

    Args:
        citations: list of {"call_id": str, "quote": str, ...} dicts.
        transcripts_by_call: {call_id: transcript_body} map.

    Returns:
        (all_ok, list_of_failure_messages). Empty failures => all_ok=True.
    """
    failed: list[str] = []
    for i, c in enumerate(citations):
        call_id = c.get("call_id")
        quote = c.get("quote", "")
        if not call_id:
            failed.append(f"citation #{i}: missing call_id")
            continue
        body = transcripts_by_call.get(call_id)
        if body is None:
            failed.append(f"citation #{i}: call_id {call_id!r} not in supplied transcripts")
            continue
        if not quote:
            failed.append(f"citation #{i}: empty quote")
            continue
        if quote not in body:
            failed.append(
                f"citation #{i}: quote not found verbatim in call {call_id} transcript"
            )
    return (len(failed) == 0, failed)


def find_quote_lines(quote: str, transcript_body: str) -> str | None:
    """Find a verbatim quote in transcript_body and return the line range as 'X-Y'.

    Lines are 1-indexed. Returns None if the quote is not found.
    """
    idx = transcript_body.find(quote)
    if idx == -1:
        return None
    before = transcript_body[:idx]
    start_line = before.count("\n") + 1
    end_line = start_line + quote.count("\n")
    return f"{start_line}-{end_line}"
