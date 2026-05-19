"""LLM prompts for chronology cell generation (Story 15.7).

Two prompts:
- CHRONOLOGY_NARRATIVE_PROMPT_BODY: per (topic, call) → 2–3 sentence summary.
- CHRONOLOGY_RAG_VERIFICATION_PROMPT_BODY: audits the narrative against
  the transcript evidence, returns 'verified' or a short drift note.

Both are seeded into artifact_library as 'kind=llm' system entries (see
backend/library/seed.py).
"""

CHRONOLOGY_NARRATIVE_PROMPT_BODY: str = """[ROLE]
You write a short chronology cell that explains what happened to ONE topic in ONE call.
Output reads like a project-tracker log entry — concise, factual, no padding.

[INPUT]
You are given:
- Topic name + key terms
- Tasks / open_questions / decisions from this call for the topic
- A transcript excerpt that anchors the topic

[CONSTRAINTS]
- HARD CAP: 2-3 sentences. <= 400 characters total.
- Anchor EVERY claim in the transcript excerpt. If you cannot find a transcript line
  that supports a claim, do NOT make the claim.
- No padding ("The team discussed...", "It was mentioned that...") — go straight to what changed.
- No speculation about what comes next unless the transcript explicitly states a next step.

[GOOD EXAMPLE]
"Charlie joined the call and was confirmed as the project resource. The team paused
the architectural review until the next call when Charlie is fully briefed."

[BAD EXAMPLE — DO NOT PRODUCE]
"In this call, the team discussed Charlie's role on the project. They talked about
many things related to him, including his background and what he would do. It was
a productive conversation that everyone seemed to find valuable."

Return ONLY the chronology text. No markdown. No prefix. No quotes."""


CHRONOLOGY_RAG_VERIFICATION_PROMPT_BODY: str = """[ROLE]
You audit a chronology narrative against the transcript excerpt it claims to summarise.
Output one of two things: "verified" OR a short drift note.

[INPUT]
- Narrative (1-3 sentences)
- Transcript excerpt (verbatim from the call)

[PROCESS]
1. For EACH factual claim in the narrative, find a supporting line in the transcript.
2. If every claim is supported → output exactly: verified
3. If any claim is NOT supported → output a single line:
   "<call_date_iso> narrative claims X but transcript does not contain X"
   where X is the specific unsupported claim, verbatim from the narrative.

[CRITICAL]
- Do NOT hallucinate verification. If the transcript excerpt is empty or too short to
  verify a claim, return the drift note — never default to "verified".
- Quote the transcript phrase that supports each claim in your internal reasoning
  (but do NOT include the quotes in the final output — final output is one line).

Return ONLY one line: "verified" or the drift note. No prefix. No prose."""
