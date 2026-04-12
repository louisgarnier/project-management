// Call Tracker — TypeScript types
// Mirrors the Supabase schema defined in backend/database/migrations/001_initial_schema.sql

export type LLMProvider = "groq" | "claude" | "openai";

export interface Project {
  id: string;
  name: string;
  description: string | null;
  default_llm: LLMProvider;
  created_at: string;
}

export type KanbanStage = "transcript" | "artifacts" | "topics" | "done";

export interface Call {
  id: string;
  project_id: string;
  title: string;
  transcript: string | null;
  transcript_source: string | null;
  kanban_stage: KanbanStage;
  created_at: string;
}

export type ArtifactMode = LLMProvider | "manual";
export type ArtifactStatus = "pending" | "generating" | "done" | "error";

export interface ArtifactType {
  id: string;
  project_id: string;
  name: string;
  prompt: string;
  is_default: boolean;
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

export type TopicStatus = "active" | "decision_made" | "on_hold" | "closed";

export interface Topic {
  id: string;
  project_id: string;
  name: string;
  status: TopicStatus;
  first_raised_call_id: string | null;
  created_at: string;
}

export interface TopicUpdate {
  id: string;
  topic_id: string;
  call_id: string;
  summary: string;
  follow_up_items: string[];
  created_at: string;
}

// Topic with enriched data for the dashboard
export interface TopicWithHistory extends Topic {
  latest_update: TopicUpdate | null;
  history: TopicUpdate[];
  first_raised_call_title?: string;
}

export interface CallFile {
  id: string;
  call_id: string;
  filename: string;
  storage_path: string;
  size_bytes: number | null;
  created_at: string;
}
