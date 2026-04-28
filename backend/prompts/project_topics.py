"""Single source of truth for the project_topics prompt.

Despite the file/category name (legacy from before the merge step existed), this
prompt drives the LLM merge at the **Project Updates** stage — it tells the
model how to combine an existing project topic (history from prior calls) with
one or more new call topics that just discussed it, producing one updated
topic that reflects the CURRENT state of the world.

Consumed in two places — both reference the same constant:
1. Seed for new projects — DEFAULT_PROJECT_TOPICS_PROMPT in routers/artifact_types.py
2. Merge instructions in run_merge_preview — services/topics_service.py

Library system entry "Project Topics Merge (base instructions)" is also seeded
from this constant via backend/library/seed.py.

OLD_DEFAULT_PROMPT_STRING is a frozen snapshot of the pre-rewrite prompt;
used for migration matching to identify unedited rows.
"""

PROJECT_TOPICS_DEFAULT_PROMPT: str = """[ROLE]
You maintain a living project topic record across multiple client calls. Your job is to merge a single existing project topic (which carries history from prior calls) with one or more new call topics that just discussed it, producing an updated topic that reflects the CURRENT state of the world. Future readers must trust this record without re-listening to calls — completeness, accurate status, and zero double-counting all matter.

The matching has already happened — the items you receive ARE about the same business subject. Your job is synthesis, not classification.

[RUBRIC]
A good merge satisfies all four criteria:

1. COMPLETENESS — every concrete detail (numbers, names, dates, frequencies, commitments, system names, metrics) from BOTH the existing topic and the new call survives in either the summary or the anchors. If you cannot justify dropping a piece of information, keep it.

2. CURRENCY — status, sentiment, and owner reflect the situation AFTER this call. The existing values are starting points, not anchors.

3. NO DOUBLE-COUNTING — the same action / decision / question with refined wording must be ONE entry, not two. The newer phrasing usually wins.

4. LIFECYCLE — items resolved/completed/answered in this call MUST be removed from their live anchor list and reflected as decisions or in the summary. A topic with no remaining follow-ups and no remaining open questions belongs at status="resolved", not "open".

[ANCHORS] — per-field merge rules

decisions[] — UNION existing + new, then DEDUPE + SUPERSEDE:
- Identical or near-identical decisions: keep one (newer wording wins).
- A new decision SUPERSEDES an old one (e.g. "Phase 2 gated on benchmark" → later "Phase 2 starts April 28 — benchmark passed"): drop the old, keep the new.
- A new decision REFINES an old one (adds owner, deadline, scope): replace the old with the refined version.
- All other prior decisions stay verbatim.

follow_up_items[] — UNION existing + new, then DEDUPE + CLOSE:
- Same action with refined wording (e.g. "Nick: run benchmark" → "Nick: run LMAC benchmark by Friday"): keep one (newer).
- Action COMPLETED in this call: REMOVE from follow_up_items[]. Capture the outcome as a decision (e.g. follow-up "Nick: confirm Charlie's availability" + new note "Charlie confirmed Mon 11am" → drop the follow-up, add decision "Charlie confirmed Mon 11am as standing cadence").
- Action no longer relevant or deferred indefinitely: drop from follow_up_items[] and note in the summary why.
- Otherwise: keep the existing follow-up verbatim.

open_questions[] — UNION existing + new, then DEDUPE + RESOLVE:
- Question ANSWERED in this call: REMOVE from open_questions[]. Capture the answer as a decision.
- Question rephrased: keep the newer wording.
- A new follow-up that investigates an open question: keep BOTH the question (still open) AND the investigation follow-up — they are paired, not redundant.
- Otherwise: keep the existing question verbatim.

status — RECOMPUTE from the post-merge state, do not just copy the old value:
- "resolved" if no remaining follow_up_items[] AND no remaining open_questions[]. The topic is closed out.
- "in_progress" if there is at least one follow-up with a named owner actively working.
- "open" if there are open questions OR follow-ups without owners (still being defined).

sentiment — re-evaluate from THIS call's discussion:
- "positive" — progress made, blockers cleared, decisions firmed up
- "neutral" — informational update, no material change
- "concern" — risks raised, blockers identified, plans slipping

owner — Us / Client / Both — reflect who is actively driving the work post-call, not history.

summary — 4 to 8 sentences. MUST cover BOTH prior history AND this call's update. Order: history first (prior decisions + state), then this call's update (what changed, what was decided, what was completed, what remains open). Do not compress. If the discussion touched on specific numbers, dates, names, or commitments, include them.

name — use the EXISTING topic's name exactly. Do NOT rename during merge. The user already matched these in the prior stage; keep their alignment.

[FEW-SHOT]

INPUT — existing project topic (history from prior calls):
{
  "name": "Charlie Onboarding — Resource Assignment, First Call Scheduling, and Architecture Walkthrough",
  "status": "open",
  "summary": "Nick proposed assigning Charlie from FactSet PS to the implementation. Architecture walkthrough scheduled for kickoff but Charlie's first availability is April 13. Weekly cadence proposed but unconfirmed.",
  "decisions": ["Charlie (FactSet PS) assigned to the implementation."],
  "follow_up_items": [
    "Nick: confirm with Charlie whether Monday 11am Central works for weekly calls",
    "Nick: brief Charlie on all topics discussed in this call before April 13th"
  ],
  "open_questions": ["Will Charlie's schedule allow Monday 11am Central?"],
  "sentiment": "neutral",
  "owner": "Us"
}

INPUT — new call topic (this call):
{
  "name": "Charlie Onboarding follow-up",
  "summary": "Charlie joined briefly. Confirmed Monday 11am Central works as the standing cadence. Nick walked Charlie through the 4 topics from the prior call. Charlie will review the architecture deck before the April 13 walkthrough.",
  "decisions": ["Charlie confirmed Monday 11am Central as the standing weekly cadence."],
  "follow_up_items": ["Charlie: review architecture deck before April 13 walkthrough"],
  "open_questions": []
}

OUTPUT — merged topic (shape and discipline to mirror):
{
  "name": "Charlie Onboarding — Resource Assignment, First Call Scheduling, and Architecture Walkthrough",
  "summary": "Nick proposed assigning Charlie from FactSet PS to the implementation, with the architecture walkthrough scheduled for the April 13 kickoff. In this call Charlie joined briefly and confirmed Monday 11am Central as the standing weekly cadence; Nick has already briefed him on the 4 topics from the prior call. Remaining work is Charlie's pre-read of the architecture deck before April 13.",
  "decisions": [
    "Charlie (FactSet PS) assigned to the implementation.",
    "Charlie confirmed Monday 11am Central as the standing weekly cadence."
  ],
  "follow_up_items": [
    "Charlie: review architecture deck before April 13 walkthrough"
  ],
  "open_questions": [],
  "status": "in_progress",
  "sentiment": "positive",
  "owner": "Both",
  "is_parked": false,
  "importance": "medium",
  "rationale": "1 named owner (Charlie) actively working on a concrete pre-read; no open questions remaining."
}

LIFECYCLE TRACE — what changed and why (do NOT include this section in your output, it is for your reasoning only):
- Open question "Will Charlie's schedule allow Monday 11am?" → ANSWERED → REMOVED from open_questions, captured as decision "Charlie confirmed Monday 11am Central…"
- Follow-up "Nick: confirm with Charlie whether Monday 11am Central works" → COMPLETED → REMOVED from follow_up_items (the answer is now a decision)
- Follow-up "Nick: brief Charlie on all topics" → COMPLETED → REMOVED from follow_up_items, reflected in summary "Nick has already briefed him"
- New follow-up "Charlie: review architecture deck" → ADDED to follow_up_items
- status: open → in_progress (one named owner actively working, no open questions)
- sentiment: neutral → positive (progress made — cadence locked, briefing done)
- owner: Us → Both (Charlie now has an action of his own)

[PROCESS]
Work in 5 internal steps. Do NOT expose the steps. Return ONLY the merged topic JSON.

Step 1 — Read both inputs end to end. List every distinct decision, follow-up, and open question across both. Flag duplicates by SUBJECT (not exact string match).

Step 2 — LIFECYCLE pass:
  - For each existing follow-up: was it completed/answered/superseded by anything in the new call? If yes, mark for REMOVAL and capture the outcome as a decision.
  - For each existing open question: was it answered in the new call? If yes, mark for REMOVAL and capture the answer as a decision.
  - For each new decision: does it supersede or refine an existing decision? If yes, mark the existing decision for removal.

Step 3 — DEDUPE pass on what remains. Same subject = one entry. Newer wording usually wins.

Step 4 — RECOMPUTE status using the rule (resolved → in_progress → open). RECOMPUTE sentiment from the new call's tone. UPDATE owner to reflect who is actively driving post-call.

Step 5 — WRITE a 4-8 sentence summary in chronological order: history first, then this call's update. Include every concrete detail (numbers, names, dates, commitments). Use the EXISTING topic's `name` exactly — do NOT rename. Set is_parked, importance, rationale based on the post-merge state.

Return ONLY a valid JSON object (single topic) matching the schema. No markdown, no explanation."""


OLD_DEFAULT_PROMPT_STRING: str = (
    "You are an expert at matching client call topics to an existing project topic backlog.\n\n"
    "Given topics extracted from the current call and the existing project topic list, "
    "classify each topic:\n"
    '- "followed_up": call topics that match an existing project topic (same business subject, '
    "possibly different wording). Use the existing topic name exactly. Update summary, status, "
    "follow_up_items, and decisions with new information from this call.\n"
    '- "not_discussed": existing project topics not covered by any call topic.\n'
    '- "new_topics": call topics with no match in the existing project list.\n\n'
    "Be generous with matching — slightly different wording for the same business subject "
    "counts as a match."
)
