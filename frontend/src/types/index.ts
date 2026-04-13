// Call Tracker — TypeScript types
// Mirrors the Supabase schema defined in backend/database/migrations/001_initial_schema.sql

export type LLMProvider = "groq" | "deepseek" | "claude" | "openai";

export interface Project {
  id: string;
  name: string;
  description: string | null;
  default_llm: LLMProvider;
  created_at: string;
}

export type KanbanStage = "transcript" | "call_topics" | "project_topics" | "artifacts" | "done";

export interface Call {
  id: string;
  project_id: string;
  title: string;
  transcript: string | null;
  transcript_source: string | null;
  kanban_stage: KanbanStage;
  is_locked: boolean;
  topics_stale: boolean;
  created_at: string;
}

export type ArtifactMode = LLMProvider | "manual";
export type ArtifactStatus = "pending" | "generating" | "done" | "error" | "stale";

export type ArtifactCategory = "artifacts" | "topics";

export interface ArtifactType {
  id: string;
  project_id: string;
  name: string;
  prompt: string;
  is_default: boolean;
  category: ArtifactCategory;
  llm: LLMProvider | null;
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
