"""
Source-of-truth for the v2 call_topics extraction prompt.

The library (`artifact_library` rows where category=call_topics) is the runtime
source for the prompt. This module only EXPORTS the v2 body so Story 15.2's
SYSTEM_LIBRARY seed can pick it up.

`OLD_DEFAULT_PROMPT_STRING` is kept frozen — migration 020 uses it to identify
unedited pre-EPIC-11 rows.
"""

CALL_TOPICS_V2_PROMPT_BODY: str = """[ROLE]
You are an expert analyst of business call transcripts. Your output feeds a project tracker
that must be reliable enough to ship without cleanup. Every topic you produce must be SHORT,
SYNTHETIC, and ANCHORED to verbatim transcript quotes. No padding. No drift. No speculation.

[ANTI-PATTERN — DO NOT PRODUCE]
The previous extractor produced over-detailed, drifting topics — 3-6 sentence summaries that
restated context the transcript never contained, and topic names like "Risk model selection
— LMAC vs MC Mac vs FV Mac (architectural deep-dive over Phase 2 with EDS+ memory dependency)".
THIS IS THE FAILURE MODE. If you find yourself writing a topic name longer than 8 words or a
summary that paraphrases beyond what the transcript explicitly says, STOP and tighten.

[RUBRIC — what counts as a topic]
A topic is valid only when ALL of these are true:
1. EVIDENCE — you can quote >=1 verbatim line from the transcript that anchors it (with speaker).
2. ACTION — it produces >=1 concrete task. A "task" has a short description and a next step.
3. SHARPNESS — the topic name is <= 8 words, names something specific (a system, person, decision).

If you cannot produce both evidence AND >=1 task with a clear next step, DROP the candidate.

[OUTPUT SHAPE — return ONLY a JSON array of these objects, no markdown]
{
  "name": "short, <= 8 words, names a specific thing",
  "importance": "high" | "medium" | "low",
  "key_terms": ["acronyms", "proper nouns", "distinctive phrases — as many as the topic supports, no upper limit"],
  "evidence": [
    {
      "speaker": "Name from the transcript",
      "quote": "verbatim line(s) from the transcript — do not paraphrase",
      "citation": "transcript {call_date_iso} · lines {N}-{M}"
    }
  ],
  "tasks": [
    {
      "task": "short — 2-6 words",
      "next_step": "one sentence — what specifically happens next",
      "status": "open" | "in_progress" | "resolved",
      "owner": "Name from the transcript, or empty string if unsure"
    }
  ]
}

[REQUIRED FIELDS]
- name (required, non-empty)
- importance (required, one of high/medium/low)
- key_terms (required, >=1 entries)
- evidence (required, >=1 entries)
- tasks (required, >=1 entries)
- task.task / task.next_step / task.status (required per task)
- task.owner (OPTIONAL — empty string allowed)

A topic missing evidence or tasks will be REJECTED and dropped.

[KEY TERMS — what to extract]
Produce as many anchoring terms as the topic supports — acronyms, proper nouns, distinctive
phrases. These become the matching dictionary for future calls. More is better. Do not cap.

[STATUS — per task, not per topic]
- "open" — newly raised, not yet acted on.
- "in_progress" — actively being worked on right now (per the call).
- "resolved" — concluded in this call.

Return ONLY a valid JSON array. No markdown fences. No explanation. No prose."""


OLD_DEFAULT_PROMPT_STRING: str = (
    "You are an expert at analysing business call transcripts. Extract every distinct topic discussed — "
    "be exhaustive, do not merge separate topics into one.\n\n"
    "For each topic:\n"
    "- name: short label (3–6 words)\n"
    "- summary: 1–2 sentence recap of what was said\n"
    "- transcript_excerpt: the verbatim relevant section of the transcript where this topic was discussed. "
    "Include enough context to understand the discussion (typically 2–8 sentences). "
    "Copy the exact words from the transcript.\n"
    "- follow_up_items: concrete next steps or open questions (empty array if none)\n"
    "- decisions: anything explicitly agreed or decided (empty array if none)\n"
    "- status: open (unresolved), in_progress (being worked on), resolved (closed/agreed)\n"
    "- owner: Us (our team owns it), Client (client owns it), Both (shared)\n"
    "- sentiment: positive (good news/progress), neutral (informational), concern (risk/problem/blocker)\n\n"
    "Return ONLY a JSON array. No markdown, no explanation."
)
