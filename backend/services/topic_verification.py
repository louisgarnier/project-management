"""EPIC-16 — Orchestration for the 3 RAG verification passes."""

import json
import logging

from backend.prompts.verify_new_topic import VERIFY_NEW_TOPIC_PROMPT
from backend.services.citation_verify import verify_citations, find_quote_lines

logger = logging.getLogger("calltracker.topic_verification")


# Thin shim around the project's LLM dispatcher — kept here so tests can monkeypatch it.
async def _call_llm(prompt: str, llm: str, *, model: str | None) -> dict:
    from backend.services.topics_service import _call_llm as _ts_call_llm
    return await _ts_call_llm(prompt, llm, model=model)


def _build_verify_new_prompt(
    candidate: dict, project_topics: list[dict], transcripts: dict[str, str]
) -> str:
    transcripts_block = "\n\n".join(
        f"--- CALL {cid} ---\n{body}" for cid, body in transcripts.items()
    )
    project_topics_block = json.dumps(
        [{"topic_id": t.get("topic_id"), "name": t.get("name"), "key_terms": t.get("key_terms", [])}
         for t in project_topics],
        indent=2,
    )
    candidate_block = json.dumps({
        "name": candidate.get("name"),
        "key_terms": candidate.get("key_terms", []),
        "tasks": candidate.get("tasks", []),
        "open_questions": candidate.get("open_questions", []),
        "decisions": candidate.get("decisions", []),
    }, indent=2)
    return (
        f"{VERIFY_NEW_TOPIC_PROMPT}\n\n"
        f"CANDIDATE NEW TOPIC:\n{candidate_block}\n\n"
        f"EXISTING PROJECT TOPICS (anchor only, names + key_terms):\n{project_topics_block}\n\n"
        f"TRANSCRIPTS:\n{transcripts_block}"
    )


async def run_verify_new(
    candidate: dict,
    project_topics: list[dict],
    transcripts: dict[str, str],
    *,
    llm: str,
    model: str | None,
) -> dict:
    """Run Pass ① for one candidate new topic.

    Returns the LLM verdict augmented with a `needs_manual_review` flag set to True
    if citation verification failed both on the first attempt and on one retry.
    """
    prompt = _build_verify_new_prompt(candidate, project_topics, transcripts)
    result: dict = {}
    failures: list[str] = []

    for attempt in (1, 2):
        result = await _call_llm(prompt, llm, model=model)
        if not isinstance(result, dict):
            logger.warning("⚠️ [verify_new] LLM returned non-dict on attempt %d", attempt)
            failures = ["LLM returned non-dict"]
            continue
        cits = result.get("citations") or []
        for c in cits:
            if not c.get("lines"):
                body = transcripts.get(c.get("call_id"), "")
                computed = find_quote_lines(c.get("quote", ""), body)
                if computed:
                    c["lines"] = computed
        ok, failures = verify_citations(cits, transcripts)
        if ok:
            return {**result, "needs_manual_review": False}
        logger.warning("⚠️ [verify_new] citation verify failed on attempt %d: %s", attempt, failures)
        prompt = (
            f"{prompt}\n\nPREVIOUS ATTEMPT FAILED citation verification with these errors:\n"
            f"{json.dumps(failures, indent=2)}\nRedo with verbatim quotes copy-pasted from transcripts."
        )

    return {
        **result,
        "needs_manual_review": True,
        "failed_citations": failures,
    }
