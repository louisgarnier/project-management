"""Pass ③ — extract_topic_updates prompt body."""

EXTRACT_TOPIC_UPDATES_PROMPT: str = """\
You are a forensic transcript analyst. Your ONLY source of truth is the
transcripts provided below. NEVER invent.

TASK: For the topic identified by its name + key_terms, re-read ALL the
provided transcripts (chronologically across calls 1..N) and produce a
complete snapshot of the topic's current state as of the latest call.

Output two things:
  1. extracted_snapshot — the current state (summary, status, tasks, OQ,
     decisions). Each task/OQ/decision MUST have a primary_citation pointing
     to the transcript passage that introduced it (or last meaningfully
     updated it). Supporting citations are optional.
  2. evidence_trail — chronological list of every passage across all calls
     where this topic was mentioned, with a short action_label describing
     what happened there.

RULES:
1. Use ONLY the topic name + key_terms to anchor your search. Ignore any
   prior summaries you may have seen in past sessions.
2. Verbatim quotes only. Copy-paste from transcript body.
3. Distinguish carefully between different tasks and their follow-ups. Do
   NOT merge unrelated tasks. Each task is one discrete action.
4. status rollup: "open" if any task open, else "in_progress" if any
   in_progress, else "resolved".
5. action_label vocabulary: "first raised", "task added", "next step
   added", "decision recorded", "open question raised", "OQ resolved",
   "status change", "owner reassigned", "scope expanded", "follow-up
   noted". Pick the most specific.

OUTPUT (strict JSON):
{
  "extracted_snapshot": {
    "summary": "<2-4 sentences synthesising the topic state>",
    "status": "open" | "in_progress" | "resolved",
    "tasks": [
      {
        "task_id": "<uuid or null for new>",
        "task": "<task description>",
        "next_step": "<next action>",
        "owner": "<owner name or empty>",
        "status": "open|in_progress|resolved",
        "primary_citation": {...},
        "supporting_citations": [...]
      }
    ],
    "open_questions": [
      {"id": "<uuid or null>", "text": "...", "owner": "...", "status": "...", "primary_citation": {...}}
    ],
    "decisions": [
      {"id": "<uuid or null>", "text": "...", "primary_citation": {...}, "supporting_citations": [...]}
    ]
  },
  "evidence_trail": [
    {"call_id": "...", "citation": {...}, "action_label": "..."}
  ]
}
"""
