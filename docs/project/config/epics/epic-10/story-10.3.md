# Story 10.3 — Topic Evidence API

**Epic:** EPIC-10 — Topic Lineage + Prompt Traceability
**Status:** `pending`
**Spec:** `docs/project/config/2026-04-20-epic-10-topic-lineage-and-prompt-traceability-design.md` §4.2, §6 Phase 3
**Depends on:** 10.1

---

## Goal
Expose a single HTTP endpoint that returns a topic's complete per-call evidence trail, ancestor-aware, ordered chronologically. This API powers the frontend evidence panel in Story 10.4.

## Endpoint
`GET /api/topics/{topic_id}/evidence` → `200 TopicEvidenceResponse`

## Response shape
```python
class LineageNode(BaseModel):
    topic_id: str
    name: str
    archived: bool
    merged_into_topic_id: str | None

class EvidenceRawExtract(BaseModel):
    summary: str
    follow_up_items: list[str]
    decisions: list[str]

class EvidenceMatchGroup(BaseModel):
    project_topic_ids: list[str]
    call_topic_names: list[str]

class EvidenceVerification(BaseModel):
    discussed: bool
    transcript_excerpt: str | None
    reasoning: str

class EvidenceCall(BaseModel):
    call_id: str
    call_title: str
    call_date: str                      # ISO date
    source_topic_id: str
    source_topic_name: str
    transcript_excerpt: str | None
    merged_summary: str
    follow_up_items: list[str]
    decisions: list[str]
    status: str                          # open | in_progress | resolved
    raw_extract: EvidenceRawExtract | None
    match_group: EvidenceMatchGroup | None
    not_discussed_verification: EvidenceVerification | None
    is_not_discussed: bool

class TopicEvidenceResponse(BaseModel):
    topic_id: str
    topic_name: str
    lineage: list[LineageNode]
    calls: list[EvidenceCall]
```

## Assembly rules
- `lineage` uses `get_topic_lineage(topic_id)` from Story 10.1
- `calls[]` uses `get_lineage_topic_updates(topic_id)` — one entry per `topic_updates` row, enriched with call metadata (title, date), `source_topic_id`, `source_topic_name`
- `raw_extract` is looked up in `calls.pending_topics` for that call and that source_topic's name (or closest name match). `null` if absent or not found.
- `match_group` is looked up in `topic_match_groups` for that call — the row whose `project_topic_ids` contains the `source_topic_id`. `null` if absent.
- `not_discussed_verification` is looked up in `calls.verification_cache` — the entry keyed by `source_topic_id`. `null` if absent.
- `is_not_discussed` is `true` when the evidence row came from a not-discussed-verification result (no `topic_updates` row exists, only verification result)
- Results ordered by `call_date` ascending

## Acceptance Criteria
- [ ] `GET /api/topics/{topic_id}/evidence` returns 200 with complete payload for any existing topic
- [ ] Returns 404 if topic does not exist
- [ ] For a topic with no lineage (never merged), `lineage` contains exactly one node (the topic itself)
- [ ] For an M:N-merged topic, `lineage` contains the merged topic plus every archived source, ordered current → sources
- [ ] `calls[]` contains one entry per ancestor-inclusive `topic_updates` row, chronological
- [ ] `calls[].source_topic_name` reflects the archived source topic's name when the evidence came from a pre-merge ancestor
- [ ] Endpoint is documented in the OpenAPI schema (automatic via Pydantic)
- [ ] Performance: returns in <500ms for a topic with 20 ancestor calls (measured on a seeded test project)

## Tasks
- [ ] Add `TopicEvidenceResponse` + sub-models to `backend/routers/topics.py`
- [ ] Implement `GET /topics/{topic_id}/evidence` handler using Story 10.1 helpers
- [ ] Add `raw_extract` lookup helper (matches pending_topics by source_topic_name)
- [ ] Add `match_group` lookup helper
- [ ] Add `not_discussed_verification` lookup helper
- [ ] Integration test in `backend/tests/test_topic_evidence.py` covering:
  - No-lineage topic returns single-node lineage and correct calls
  - M:N-merged topic returns correct lineage and interleaved ancestor calls
  - 404 on missing topic
  - Raw extract attached when pending_topics retains the raw entry
  - Match group attached correctly
  - Not-discussed verification attached correctly
- [ ] Add a performance test that seeds 20 calls + 5 M:N merges and asserts response time < 500ms
- [ ] Expose the endpoint path via OpenAPI (automatic) and verify via `/docs`

## Dev Tests
- Create a fixture with 3 calls + 1 M:N merge, call the endpoint, assert lineage contains 3 nodes (merged + 2 sources), calls contains 3 entries (Call 1 on Source A, Call 2 on merged, Call 3 on merged).
- Visit `/docs` and verify the endpoint and response schema appear correctly.

## Out of Scope
- Frontend consumption (Story 10.4)
- Client-side caching of evidence responses
- Streaming / pagination (single-response endpoint; topics with 20+ calls are the envisioned upper bound)
