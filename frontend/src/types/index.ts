// Call Tracker — TypeScript types
// Mirrors the Supabase schema defined in backend/database/migrations/001_initial_schema.sql

export type LLMProvider = "groq" | "deepseek" | "claude" | "openai";

export interface Project {
  id: string;
  name: string;
  description: string | null;
  default_llm: LLMProvider;
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
  verification_cache: Record<string, { discussed: boolean; transcript_excerpt: string | null; reasoning: string }> | null;
  verification_status: "idle" | "processing" | "done" | "failed";
  created_at: string;
}

export type ArtifactMode = LLMProvider | "manual";
export type ArtifactStatus = "pending" | "generating" | "done" | "error" | "stale";

export type ArtifactCategory = "artifacts" | "topics" | "call_topics" | "project_topics";

export type ContextScope = "call" | "project";

export interface ArtifactType {
  id: string;
  project_id: string;
  name: string;
  prompt: string;
  is_default: boolean;
  category: ArtifactCategory;
  llm: LLMProvider | null;
  context_scope: ContextScope;
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

/** One topic as returned by extract or dashboard endpoints */
export interface TopicData {
  topic_id?: string | null;  // null / absent = brand new (not yet in DB)
  name: string;
  summary: string;
  follow_up_items: string[];
  decisions: string[];
  status: TopicStatus;
  owner: TopicOwner;
  sentiment: TopicSentiment;
  calls_open?: number;
  not_discussed?: boolean;
  pending_merge?: boolean;
  verification_status?: "pending" | "confirmed" | "flagged";
  _source_topic_ids?: string[];
  transcript_excerpt?: string | null;  // verbatim transcript chunk captured at extraction (EPIC-9)
  // From list_topics_prior_to_call: topic was active at this call's matching
  // time but has since been merged away in a later call. UI shows a badge.
  archived_later?: boolean;
  merged_into_name?: string | null;
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
  decisions?: string[];
  status?: string;
  owner?: string;
  sentiment?: string;
  merged_into_name?: string;
  merged_into_topic_id?: string;
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
  discussed: boolean;
  transcript_excerpt: string | null;
  reasoning: string;
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
