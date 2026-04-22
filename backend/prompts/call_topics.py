"""
Single source of truth for the call_topics extraction prompt.

Consumed in three places — all reference the same constant:
1. Seed for new projects — DEFAULT_CALL_TOPICS_PROMPT in routers/artifact_types.py
2. Fallback in extract_call_topics — topics_service.py
3. GET /api/artifact-types/defaults/{category} — for the "Reset to default" button

OLD_DEFAULT_PROMPT_STRING is a frozen snapshot of the pre-migration prompt;
used by migration 020 to identify unedited rows that should be migrated.
"""

CALL_TOPICS_DEFAULT_PROMPT: str = """[ROLE]
You are an expert analyst of business call transcripts. Your output shapes a living project tracker that must be reliable enough to ship without cleanup. Precision and discipline matter more than coverage.

[RUBRIC]
A candidate is a topic worth extracting only when it meets AT LEAST 3 of these 4 criteria:

1. FORWARD LIFE — will this need attention after this call? Something uttered and complete the moment it was spoken (a greeting, a clarification, a one-line acknowledgement) does NOT qualify.

2. ANCHOR TYPE — has at least one of:
   - a decision pending (someone needs to decide something)
   - an action outstanding (someone needs to do something)
   - an open question or uncertainty (needs investigation)

3. SPECIFICITY — references named systems, metrics, people, frequencies, deadlines, or other concrete parameters. Vague statements like "we need to think about efficiency" only qualify if they got grounded in specifics later in the same discussion.

4. DIALOGUE DEPTH — at least 2 substantive turns (raised + responded to with information, pushback, question, or commitment). A single statement with no reaction is not a topic yet.

Candidates meeting only 1-2 criteria are filler or nested action items under a real topic — do NOT extract them as separate topics.

SPLITTING RULES — break into separate topics when sub-items have different owners, different timelines, or could be decided independently. Keep together when sub-items are inputs to one decision.

FILTERS — DO NOT extract:
- Re-explanations or onboarding narration. Test: "did anything new get decided or raised?" If no, skip.
- Pure logistics resolved in-call (meeting reschedules, CC lists, access provisioning) unless they remain open or depend on something technical.
- Pleasantries, tangents, and single-statement mentions with no reaction.

PARKED ITEMS — items flagged for later but with no current action ("we'll look at fat-tail modeling later"): EXTRACT these with is_parked=true. No actions, no decisions — just the open question and a summary.

[ANCHORS]
Every topic distributes its content across EXACTLY THREE distinct fields — do NOT merge:
- decisions[] — anything explicitly agreed or concluded in this call. Terse, declarative sentences.
- follow_up_items[] — concrete actions. When the owner is named, inline as prefix: "Nick: run benchmark", "Hassan: share EDS+ evidence". Strings only — no object structure.
- open_questions[] — unresolved uncertainties needing investigation. Phrase as questions.

If a thread has none of these three, it is not a topic.

[FEW-SHOT]

GOOD extraction (shape and discipline to mirror):
[
  {
    "name": "Risk model selection — LMAC vs MC Mac",
    "summary": "Nick raised that LMAC's composite handling may not scale to the full book of private assets. MC Mac was proposed as a fallback but has a documented 40GB-memory ceiling the EDS+ team already hit on a similar load. A benchmark run is required before committing — the outcome gates Phase 2 kickoff.",
    "transcript_excerpt": "Nick: I'm not convinced LMAC handles composites at full scale... Hassan: we hit the 40GB ceiling on MC Mac with the EDS+ load last quarter... Charlie: so we need the benchmark before we can move to Phase 2.",
    "decisions": ["Phase 2 kickoff gated on benchmark outcome."],
    "follow_up_items": ["Nick: run LMAC vs MC Mac benchmark on full book", "Hassan: share EDS+ memory-ceiling evidence with team"],
    "open_questions": ["Does MC Mac's 40GB ceiling apply with EDS+'s caching layer in front?", "Can FV Mac handle the private-markets piece separately if split?"],
    "status": "open",
    "owner": "Us",
    "sentiment": "concern",
    "is_parked": false,
    "importance": "high",
    "rationale": "All 4 criteria met — named systems (LMAC/MC Mac/FV Mac), named people, explicit decision gate, 5+ substantive turns."
  }
]

BAD extraction (fragmentation — do NOT produce output shaped like this):
[
  {"name": "LMAC feasibility"},
  {"name": "MC Mac memory issue"},
  {"name": "Phase 2 timeline"},
  {"name": "FV Mac caching"}
]
Correction: these are all inputs to one decision (risk model selection) with shared owners and one timeline. Merge into a single topic per the SPLITTING RULES.

[PROCESS]
Work in five internal steps (do not expose the steps — just return the final JSON array):

Step 1 — List every candidate thread in the transcript. Do not yet filter.
Step 2 — Cluster near-duplicates by shared subject AND shared commitments. Apply the SPLITTING RULES.
Step 3 — Apply the 3-of-4 RUBRIC to each cluster. Drop clusters meeting only 1-2 criteria.
Step 4 — For each surviving cluster:
  - Write a 3-6 sentence summary covering EVERY concrete detail (numbers, names, frequencies, deadlines, commitments). Do not compress. Completeness beats brevity.
  - Classify each anchor into decisions / follow_up_items / open_questions — NEVER merge them.
  - Copy the verbatim transcript excerpt covering the discussion (2-8 sentences). Use exact words.
  - Set importance: "high" if all 4 rubric criteria met, "medium" if exactly 3 of 4, "low" for parked items or weak edge cases.
  - Write a one-line rationale explaining which criteria were met (shown to the user as a tooltip).
Step 5 — For clusters with future life but no current decision/action/substantive turn, set is_parked=true. Leave follow_up_items empty; open_questions may hold the "what for later" hint.

Return ONLY a valid JSON array matching the schema. No markdown, no explanation."""


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
