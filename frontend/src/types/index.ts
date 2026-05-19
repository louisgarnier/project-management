// Call Tracker — TypeScript types
// Mirrors the Supabase schema defined in backend/database/migrations/001_initial_schema.sql

export type LLMProvider = "groq" | "deepseek" | "claude" | "openai" | "openrouter";

export interface Project {
  id: string;
  name: string;
  description: string | null;
  default_llm: LLMProvider | null;
  default_model: string | null;
  context: string | null;
  created_at: string;
}

export type KanbanStage = "transcript" | "call_topics" | "project_matching" | "project_updates" | "artifacts" | "done";

export type MatchGroup = {
  project_topic_ids: string[];        // empty = new project topic, 1+ = linked/merge
  call_topic_names: string[];         // names from pending call topics
};

export interface Call {
  id: string;
  project_id: string;
  title: string;
  transcript: string | null;
  transcript_source: string | null;
  kanban_stage: KanbanStage;
  is_locked: boolean;
  topics_stale: boolean;
  extraction_cache: TopicData[] | null;
  extraction_status: "idle" | "processing" | "done" | "failed";
  pending_topics: TopicData[] | null;
  merge_cache: TopicData[] | null;
  merge_status: "idle" | "processing" | "done" | "failed";
  verification_cache: Record<string, { discussed: boolean | null; transcript_excerpt: string | null; reasoning: string; error: string | null }> | null;
  verification_status: "idle" | "processing" | "done" | "failed";
  call_topics_prompt_id: string | null;
  created_at: string;
}

export type ArtifactMode = LLMProvider | "manual";
export type ArtifactStatus = "pending" | "generating" | "done" | "error" | "stale";

export type ArtifactCategory = "artifacts" | "topics" | "call_topics" | "project_topics" | "merge_verification" | "not_discussed_check";

export type ContextScope =
  | "this_call_transcript"
  | "all_call_transcripts"
  | "this_call_topics"
  | "all_project_topics";

export type ArtifactKind = "llm" | "template" | "hybrid";

export interface LibraryEntry {
  id: string;
  name: string;
  description: string;
  kind: ArtifactKind;
  prompt: string | null;
  template_id: string | null;
  llm: LLMProvider | null;
  model: string | null;
  context_scope: ContextScope;
  /** 'artifacts' for Tier-2 entries; 'call_topics' | 'project_topics' |
   * 'merge_verification' | 'not_discussed_check' for Tier-1 workflow prompts. */
  category: ArtifactCategory;
  is_system: boolean;
  seeded_by_default: boolean;
  created_at: string;
}

export interface ArtifactType {
  id: string;
  project_id: string;
  name: string;
  prompt: string;
  is_default: boolean;
  category: ArtifactCategory;
  llm: LLMProvider | null;
  model: string | null;
  context_scope: ContextScope;
  kind: ArtifactKind;
  template_id: string | null;
  library_ref_id: string | null;
  created_at: string;
}

export interface Artifact {
  id: string;
  call_id: string;
  artifact_type_id: string;
  mode: ArtifactMode;
  status: ArtifactStatus;
  content: string | null;
  prompt_used: string;
  error_message: string | null;
  created_at: string;
}

// ── Topics ──────────────────────────────────────────────────────────────────

export type TopicStatus    = "open" | "in_progress" | "resolved";
export type TopicOwner     = "Us" | "Client" | "Both";
export type TopicSentiment = "positive" | "neutral" | "concern";
export type TopicDisposition = "keep_as_is" | "archive" | null;

export interface EvidenceRef {
  speaker: string;
  quote: string;
  citation: string;
}

export interface OpenQuestionData {
  id: string;
  text: string;
  owner: string;                      // empty string allowed
  status: TopicStatus;
  added_in_call_id?: string | null;
  closed_in_call_id?: string | null;  // Story 15.7 — pre-installed, nullable until then
}

export interface DecisionData {
  id: string;
  text: string;
  added_in_call_id?: string | null;
}

export interface TaskData {
  task_id: string;
  task: string;
  next_step: string;
  status: TopicStatus;                // "open" | "in_progress" | "resolved"
  owner: string;                      // empty string allowed
  added_in_call_id?: string | null;   // Story 15.5
  closed_in_call_id?: string | null;  // Story 15.7 (pre-installed; nullable until then)
}

/** One topic as returned by extract or dashboard endpoints */
export interface TopicData {
  topic_id?: string | null;          // null/absent = new topic not yet linked
  id?: string | null;                // topic_updates row id from /api/topics
  name: string;
  importance?: "high" | "medium" | "low";
  key_terms?: string[];
  evidence?: EvidenceRef[];
  tasks?: TaskData[];

  // Legacy / matching-stage-only fields kept temporarily for compile compatibility.
  // Story 15.4 may revisit these. The Call Topics stage no longer renders them.
  summary?: string;
  // status + sentiment are required so Record<string,...> index lookups in
  // ProjectTopicsStage / ProjectUpdatesStage / CallTopicsHistoricalView compile.
  // New Call Topics stage ignores these; they default to "open" / "neutral" at extraction.
  status: TopicStatus;
  sentiment: TopicSentiment;
  transcript_excerpt?: string | null;
  calls_open?: number;
  not_discussed?: boolean;
  pending_merge?: boolean;
  verification_status?: "pending" | "confirmed" | "flagged";
  _source_topic_ids?: string[];
  archived_later?: boolean;
  merged_into_name?: string | null;
  // Story 15.5: open_questions and decisions are now structured arrays.
  // The legacy fields keep their name but the value type widens — readers that
  // still expect string[] must extract `.text` (typeof d === "string" ? d : d.text).
  // follow_up_items stays string[] (pre-15.3 legacy, never populated by v3 extraction).
  follow_up_items: string[];
  decisions: (string | DecisionData)[];           // union for back-compat with old DB rows
  open_questions: (string | OpenQuestionData)[];  // union for back-compat with old DB rows

  // Story 15.7 chronology + RAG verification (frozen at project_updates commit)
  chronology_narrative?: string | null;
  rag_verification_note?: string | null;

  owner?: TopicOwner | string;
  is_parked?: boolean;
  rationale?: string;
}

/** Response from POST /extract */
export interface ExtractionResult {
  call_number: number;
  followed_up: TopicData[];
  not_discussed: TopicData[];
  new_topics: TopicData[];
}

/** Response from POST /calls/{id}/topics/aggregate */
export interface AggregateResult {
  auto_advanced?: boolean;   // true = Call 1, stage already advanced to artifacts
  call_number: number;
  followed_up?: TopicData[];
  not_discussed?: TopicData[];
  new_topics?: TopicData[];
}

/** One item in the brief panel */
export interface BriefItem {
  topic_id: string;
  name: string;
  calls_open: number;
  sentiment: TopicSentiment;
  last_summary: string;
  last_follow_up_items: string[];
}

/** Response from GET /brief */
export interface CallBrief {
  priority_topics: BriefItem[];
  decisions_to_confirm: { text: string; topic_name: string }[];
  watch_list: BriefItem[];
}

/** What we send to POST /topics (save) */
export interface TopicSavePayload extends TopicData {
  topic_id: string | null;
  disposition: TopicDisposition;
}

export interface CallFile {
  id: string;
  call_id: string;
  filename: string;
  storage_path: string;
  size_bytes: number | null;
  created_at: string;
}

// ── EPIC-8: Topics Timeline ───────────────────────────────────────────────

export interface TimelineCell {
  type: "new" | "followed_up" | "not_discussed" | "pending" | "merged";
  summary?: string;
  follow_up_items?: string[];
  decisions?: (string | DecisionData)[];           // widened for v3 shape from backend
  open_questions?: (string | OpenQuestionData)[];  // added for v3 shape
  status?: string;
  owner?: string;
  sentiment?: string;
  merged_into_name?: string;
  merged_into_topic_id?: string;
  // EPIC-15 fields
  key_terms?: string[];
  evidence?: EvidenceRef[];
  tasks?: TaskData[];
}

export interface TimelineTopic {
  topic_id: string;
  name: string;
  status: TopicStatus;
  owner: string;
  sentiment: TopicSentiment;
  first_raised_call_id: string | null;
  archived?: boolean;
  merged_into_topic_id?: string | null;
  merged_into_name?: string | null;
  has_sources?: boolean;
  source_names?: string[];
  ancestor_topic_ids?: string[];
  merge_call_id?: string | null;
  call_updates: Record<string, TimelineCell>;
}

export interface TopicsTimelineData {
  calls: Array<{ id: string; title: string; call_number: number; kanban_stage: string }>;
  topics: TimelineTopic[];
}

// ── EPIC-10: Topic Evidence (lineage view) ────────────────────────────────

export type EvidenceLineageNode = {
  topic_id: string;
  name: string;
  archived: boolean;
  merged_into_topic_id: string | null;
};

export type EvidenceRawExtract = {
  summary: string;
  follow_up_items: string[];
  decisions: string[];
};

export type EvidenceMatchGroup = {
  project_topic_ids: string[];
  call_topic_names: string[];
};

export type EvidenceVerification = {
  discussed: boolean | null;
  transcript_excerpt: string | null;
  reasoning: string;
  error?: string | null;
};

export type EvidenceCall = {
  call_id: string;
  call_title: string;
  call_date: string | null;
  source_topic_id: string;
  source_topic_name: string;
  transcript_excerpt: string | null;
  merged_summary: string;
  follow_up_items: string[];
  decisions: string[];
  open_questions?: string[];
  status: string;
  raw_extract: EvidenceRawExtract | null;
  match_group: EvidenceMatchGroup | null;
  not_discussed_verification: EvidenceVerification | null;
  is_not_discussed: boolean;
};

export type TopicEvidence = {
  topic_id: string;
  topic_name: string;
  lineage: EvidenceLineageNode[];
  calls: EvidenceCall[];
};

export interface SystemSettings {
  default_llm: LLMProvider | null;
  default_model: string | null;
}
