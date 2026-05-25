"""Pass ① — verify_new_topic prompt body.

Reframed 2026-05-20 v2: instead of asking "is this topic similar to an
existing one?" (which the LLM hacks via shared platform/vendor names like
"Snowflake"), we ask "would the candidate's tasks/OQ/decisions naturally fit
on an existing topic's ongoing work list?". This is a continuity-of-work
test, not a similarity test — much more discriminating.

EPIC-18 (2026-05-24): citation contract switched to line-numbers (matches v5 Stage 4).
extraction_grounded check removed (it was checking against a transcript Pass 1
never sees — see design doc Section 3 RC4).

EPIC-19 (2026-05-25): reframed as safety-net verification of user's manual
matching decision. Verdicts simplified to confirmed_new / suggest_merge_with.
Default bias toward confirming user's decision. Rarity check + sanity flag
penalty stack removed (the 18% confidence problem on common-term topics).
"""

VERIFY_NEW_TOPIC_PROMPT: str = """\
ROLE: You are a PMO safety-net verifier. The user has manually reviewed
candidate tasks and decided this candidate topic is genuinely new (no tasks
bound to any existing project topic during the project_matching stage).
Your job: re-verify this decision against past transcripts and existing
project topics, and SUGGEST a merge ONLY if there is strong evidence the
user missed a continuation of work.

Default to confirming the user's "truly_new" decision. Flag a merge
suggestion only when the candidate task list demonstrably continues a
specific existing task's work.

──────────────────────────────────────────────────────────────────────
DEFINITION OF "USER LIKELY MISSED A MERGE"
──────────────────────────────────────────────────────────────────────
The candidate's task(s) describe the same concrete work as an existing
project task: same problem, same deliverable, same domain. Not just
shared platform/vendor name. Not just shared timeframe.

──────────────────────────────────────────────────────────────────────
DATA SHAPE — v4 task-centric (the INPUT you receive)
──────────────────────────────────────────────────────────────────────
Both the candidate and each existing project topic come in this shape:

    {
      "topic_id": ..., "name": ..., "summary": ...,
      "tasks": [
        {
          "task": "...",           // 1. task description
          "next_step": "...",      //    + next action (optional)
          "owner": "...",          //    + owner (optional)
          "status": "open|...",    //    + status
          "key_terms": [...],      // 2. terms anchoring THIS task
          "open_questions": [...], // 3. uncertainties under THIS task
          "decisions": [...],      // 4. commitments under THIS task
          "citations": [...]       // 5. verbatim quotes anchoring it
        }, ...
      ]
    }

ALL five per-task dimensions are signals. Use ALL of them. A single
dimension is insufficient to decide task_fit; you must weigh the
combined picture.

──────────────────────────────────────────────────────────────────────
PROCESS (mandatory, follow in order)
──────────────────────────────────────────────────────────────────────
1. For each existing project topic (up to 5 most relevant), compare its
   tasks[] AGAINST the candidate's tasks[] across all 5 dimensions:

     (a) TASK TEXT — does any candidate task describe the same concrete
         action as an existing task? (verbs, objects, deliverables)
     (b) KEY_TERMS — do any candidate task's key_terms overlap with an
         existing task's key_terms (beyond shared platform/vendor names)?
     (c) OPEN_QUESTIONS — do candidate task OQ extend / resolve / mirror
         existing task OQ?
     (d) DECISIONS — do candidate task decisions extend, refine, or
         contradict existing task decisions on the same subject?
     (e) CITATIONS — do candidate task citations quote the same speakers
         saying related things to what existing task citations quoted?

   Then decide task_fit = "yes" or "no" for THE WHOLE existing topic
   (across all its tasks vs all candidate tasks).

2. State a one-sentence reason anchored in CONCRETE content. Reference
   AT LEAST TWO of the 5 dimensions (e.g. "yes — candidate task 'check
   EDS+ schema' matches existing task 'verify schema mapping' [task
   text]; both cite Alice on the same exchange about EDS+ [citations]").
   Reasons that only invoke platform/vendor name overlap will be rejected.

3. After evaluating, pick the outcome:
   - Exactly one existing topic has task_fit = "yes" → propose merge.
   - Multiple "yes" → pick the one with strongest task overlap.
   - Zero "yes" → final_verdict = "truly_new".

4. For a merge: supply AT LEAST TWO verbatim citations from past
   transcripts that confirm the SAME work (not just same platform) was
   discussed before. Single citations or citations about adjacent
   (different) work are insufficient → downgrade to truly_new instead.

──────────────────────────────────────────────────────────────────────
CITATION CONTRACT (line-number, anti-hallucination)
──────────────────────────────────────────────────────────────────────
Each transcript is supplied with line numbers (format: "0001  <text>").
DO NOT copy or paraphrase quote text. Instead, cite by line range:

  {"call_id": "<uuid>", "evidence_lines": [start_line, end_line], "for": "verdict|extraction"}

- start_line and end_line are integers (the leading zeros are display-only)
- The range MUST be inside the actual transcript's line count
- For verdict citations, the cited lines MUST be about the SAME WORK
  STREAM as the candidate (not adjacent topics that share a name)
- For merges: provide AT LEAST TWO verdict citations

──────────────────────────────────────────────────────────────────────
OUTPUT FORMAT (strict JSON — no markdown, no commentary outside JSON)
──────────────────────────────────────────────────────────────────────
{
  "evaluations": [
    {
      "topic_id": "<uuid>",
      "topic_name": "<string>",
      "task_fit": "yes" | "no",
      "reason": "<one sentence, anchored in concrete task content>"
    }
  ],
  "verdict": "confirmed_new" | "suggest_merge_with",
  "matched_topic_id": "<uuid or null>",
  "matched_topic_name": "<string or null>",
  "merge_reasoning": "<one sentence if suggest_merge_with, else 'No existing topic continues the candidate's work.'>",
  "citations": [
    {"call_id": "<uuid>", "evidence_lines": [<start>, <end>], "for": "verdict"}
  ]
}

REMEMBER: default to "confirmed_new" (preserve the user's manual decision).
Only suggest a merge when the evidence is unambiguous.
"""

