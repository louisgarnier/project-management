// All API calls route through the Next.js proxy at /api/proxy/
// This keeps secrets server-side and avoids CORS issues.
// SSE connections (artifact streaming) connect directly to the backend URL.

import type { Project, Call, CallFile, ArtifactType, Artifact, LLMProvider, ArtifactMode, ContextScope, TopicsTimelineData, ArtifactCategory, LibraryEntry, SystemSettings, EvidenceRef, TaskData, TopicData, OpenQuestionData, DecisionData, Citation, VerifyNewResult, VerifyNotDiscussedResult, ExtractedUpdateResult, TaskMatchGroup } from "@/types";

const PROXY_BASE = "/api/proxy";

function parseApiError(error: unknown, status: number): string {
  if (!error || typeof error !== "object") return `HTTP ${status}`;
  const e = error as Record<string, unknown>;
  const detail = e.detail;
  if (Array.isArray(detail)) {
    // Pydantic v2 validation error array: [{loc, msg, type}, ...]
    return detail.map((d) => (typeof d === "object" && d !== null && "msg" in d ? (d as {msg: string}).msg : JSON.stringify(d))).join("; ");
  }
  if (detail && typeof detail === "object") {
    // Structured error e.g. {error: "unacknowledged_topics", ids: [...]}
    const de = detail as Record<string, unknown>;
    return typeof de.error === "string" ? de.error : JSON.stringify(detail);
  }
  return typeof detail === "string" ? detail : `HTTP ${status}`;
}

async function proxyFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${PROXY_BASE}${path}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    const method = options?.method ?? "GET";
    throw new Error(`${method} ${path} → ${response.status}: ${parseApiError(error, response.status)}`);
  }

  if (response.status === 204) return {} as T;
  return response.json();
}

export const healthAPI = {
  check: () => proxyFetch<{ status: string; db: string }>("/health"),
};

export const projectsAPI = {
  list: () => proxyFetch<Project[]>("/api/projects"),
  get: (id: string) => proxyFetch<Project>(`/api/projects/${id}`),
  create: (data: { name: string; description: string }) =>
    proxyFetch<Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: { default_llm?: LLMProvider | null; default_model?: string | null; context?: string }) =>
    proxyFetch<Project>(`/api/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  updateDefaultLlm: async (projectId: string, llm: LLMProvider | null, model: string | null = null): Promise<Project> => {
    const res = await fetch(`/api/proxy/api/projects/${projectId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ default_llm: llm, default_model: model }),
    });
    if (!res.ok) throw new Error("Failed to update project default LLM");
    return res.json();
  },
  delete: (id: string) => proxyFetch<void>(`/api/projects/${id}`, { method: "DELETE" }),
};

export const callsAPI = {
  list: (projectId: string) => proxyFetch<Call[]>(`/api/projects/${projectId}/calls`),
  create: (projectId: string, data: { title: string }) =>
    proxyFetch<Call>(`/api/projects/${projectId}/calls`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getCall: (callId: string) => proxyFetch<Call>(`/api/calls/${callId}`),
  // EPIC-17 v5 pipeline endpoints
  v5Run: (callId: string) =>
    proxyFetch<{ state: string; call_id: string }>(`/api/calls/${callId}/call-topics-v5/run`, { method: "POST" }),
  v5State: (callId: string) =>
    proxyFetch<{ state: string; payload: import("@/types").CallTopicsV5Payload | null }>(
      `/api/calls/${callId}/call-topics-v5/state`,
    ),
  v5ResolveReview: (callId: string, decisions: object) =>
    proxyFetch<{ state: string; v4_output_topic_count: number }>(
      `/api/calls/${callId}/call-topics-v5/resolve-review`,
      { method: "POST", body: JSON.stringify(decisions) },
    ),
  patchExtractionCache: (callId: string, topics: TopicData[]) =>
    proxyFetch<{ updated: boolean; count: number }>(
      `/api/calls/${callId}/extraction-cache`,
      {
        method: "PATCH",
        body: JSON.stringify({ topics }),
      },
    ),
  submitTranscript: (callId: string, transcript: string, sourceFilename?: string) =>
    proxyFetch<Call>(`/api/calls/${callId}/transcript`, {
      method: "POST",
      body: JSON.stringify({
        transcript,
        ...(sourceFilename ? { source_filename: sourceFilename } : {}),
      }),
    }),
  updateTranscript: (callId: string, transcript: string) =>
    proxyFetch<Call>(`/api/calls/${callId}/transcript`, {
      method: "PATCH",
      body: JSON.stringify({ transcript }),
    }),
  resetTranscript: (callId: string) =>
    proxyFetch<Call>(`/api/calls/${callId}/transcript`, { method: "DELETE" }),
  advanceStage: (callId: string) =>
    proxyFetch<Call>(`/api/calls/${callId}/stage`, {
      method: "PATCH",
      body: JSON.stringify({}),
    }),
  lock: (callId: string) =>
    proxyFetch<Call>(`/api/calls/${callId}/lock`, { method: "POST" }),
  unlock: (callId: string) =>
    proxyFetch<Call>(`/api/calls/${callId}/unlock`, { method: "POST" }),
  clearTopicsStale: (callId: string) =>
    proxyFetch<Call>(`/api/calls/${callId}/clear_stale`, { method: "POST" }),
  delete: (callId: string) => proxyFetch<void>(`/api/calls/${callId}`, { method: "DELETE" }),
  rollback: (callId: string, targetStage: string) =>
    proxyFetch<{ rolled_back_to: string }>(`/api/calls/${callId}/rollback`, {
      method: "POST",
      body: JSON.stringify({ target_stage: targetStage }),
    }),
  patchPromptSelection: (callId: string, call_topics_prompt_id: string | null): Promise<Call> =>
    proxyFetch<Call>(`/api/calls/${callId}/prompt-selection`, {
      method: "PATCH",
      body: JSON.stringify({ call_topics_prompt_id }),
    }),
};

async function proxyFetchForm<T>(path: string, formData: FormData): Promise<T> {
  const url = `${PROXY_BASE}${path}`;
  // No Content-Type header — browser sets it automatically with the correct boundary
  const response = await fetch(url, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(`POST ${path} → ${response.status}: ${parseApiError(error, response.status)}`);
  }
  return response.json();
}

// transcriptionAPI — calls the local server directly from the browser (not via proxy)
export const transcriptionAPI = {
  health: async (): Promise<boolean> => {
    try {
      const r = await fetch("http://localhost:8001/health", {
        signal: AbortSignal.timeout(2000),
      });
      return r.ok;
    } catch {
      return false;
    }
  },
  transcribe: async (file: File): Promise<string> => {
    const form = new FormData();
    form.append("audio", file);
    const r = await fetch("http://localhost:8001/transcribe", {
      method: "POST",
      body: form,
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(err.detail || `Transcription failed: ${r.status}`);
    }
    const data = await r.json();
    return data.transcript as string;
  },
};

// localServerAPI — calls Next.js local routes (not proxied, not Railway)
// These run on the local Node.js server and manage the transcription process.
export const localServerAPI = {
  status: async (): Promise<{ running: boolean; starting: boolean }> => {
    try {
      const r = await fetch("/api/local/status");
      if (!r.ok) return { running: false, starting: false };
      return r.json();
    } catch {
      return { running: false, starting: false };
    }
  },
  start: async (): Promise<void> => {
    const r = await fetch("/api/local/start", { method: "POST" });
    if (!r.ok) throw new Error("Failed to start server");
  },
  stop: async (): Promise<void> => {
    const r = await fetch("/api/local/stop", { method: "POST" });
    if (!r.ok) throw new Error("Failed to stop server");
  },
};

export const filesAPI = {
  upload: (callId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return proxyFetchForm<CallFile>(`/api/calls/${callId}/files`, form);
  },
  list: (callId: string) => proxyFetch<CallFile[]>(`/api/calls/${callId}/files`),
  delete: (callId: string, fileId: string) =>
    proxyFetch<void>(`/api/calls/${callId}/files/${fileId}`, { method: "DELETE" }),
  downloadUrl: (callId: string, fileId: string) =>
    proxyFetch<{ url: string }>(`/api/calls/${callId}/files/${fileId}/download`),
};

export const artifactTypesAPI = {
  list: (projectId: string) =>
    proxyFetch<ArtifactType[]>(`/api/projects/${projectId}/artifact-types`),
  create: (projectId: string, data: { name: string; prompt: string; model?: string | null }) =>
    proxyFetch<ArtifactType>(`/api/projects/${projectId}/artifact-types`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (
    projectId: string,
    typeId: string,
    data: { name?: string; prompt?: string; llm?: LLMProvider | null; model?: string | null; context_scope?: ContextScope; is_default?: boolean }
  ) =>
    proxyFetch<ArtifactType>(`/api/projects/${projectId}/artifact-types/${typeId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  getDefaults: async (category: ArtifactCategory): Promise<{ name: string; prompt: string; llm: LLMProvider | null; model: string | null; category: ArtifactCategory }> => {
    return proxyFetch(`/api/artifact-types/defaults/${category}`);
  },
  delete: (projectId: string, typeId: string) =>
    proxyFetch<void>(`/api/projects/${projectId}/artifact-types/${typeId}`, {
      method: "DELETE",
    }),
  import: (projectId: string, typeIds: string[]) =>
    proxyFetch<ArtifactType[]>(`/api/projects/${projectId}/artifact-types/import`, {
      method: "POST",
      body: JSON.stringify({ type_ids: typeIds }),
    }),

  preview: async (typeId: string, callId: string): Promise<{ content: string }> => {
    const res = await fetch(`${PROXY_BASE}/api/artifact-types/${typeId}/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ call_id: callId }),
    });
    if (!res.ok) throw new Error(`Preview failed: ${res.status}`);
    return res.json();
  },

  getLibrarySource: async (typeId: string): Promise<LibraryEntry | null> => {
    const res = await fetch(`${PROXY_BASE}/api/artifact-types/${typeId}/library-source`);
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`Failed to fetch library source`);
    return res.json();
  },

  fromLibrary: async (projectId: string, libraryId: string): Promise<ArtifactType> => {
    const res = await fetch(`${PROXY_BASE}/api/projects/${projectId}/artifact-types/from-library`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ library_id: libraryId }),
    });
    if (!res.ok) throw new Error("Failed to add from library");
    return res.json();
  },

  publishToLibrary: async (typeId: string, data: { name: string; description: string }): Promise<LibraryEntry> => {
    const res = await fetch(`${PROXY_BASE}/api/artifact-types/${typeId}/publish-to-library`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: "Unknown error" }));
      throw new Error(parseApiError(body, res.status));
    }
    return res.json();
  },
};

export const settingsAPI = {
  get: async (): Promise<SystemSettings> => {
    const res = await fetch(`${PROXY_BASE}/api/settings`);
    if (!res.ok) throw new Error("Failed to fetch system settings");
    return res.json();
  },
  update: async (patch: Partial<SystemSettings>): Promise<SystemSettings> => {
    const res = await fetch(`${PROXY_BASE}/api/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error("Failed to update system settings");
    return res.json();
  },
};

export const libraryAPI = {
  list: (): Promise<LibraryEntry[]> =>
    proxyFetch<LibraryEntry[]>("/api/library"),
  listByCategory: (category: string): Promise<LibraryEntry[]> =>
    proxyFetch<LibraryEntry[]>(`/api/library?category=${encodeURIComponent(category)}`),
  create: (entry: Partial<LibraryEntry>): Promise<LibraryEntry> =>
    proxyFetch<LibraryEntry>("/api/library", {
      method: "POST",
      body: JSON.stringify(entry),
    }),
  update: (id: string, patch: Partial<LibraryEntry>): Promise<LibraryEntry> =>
    proxyFetch<LibraryEntry>(`/api/library/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  delete: (id: string): Promise<void> =>
    proxyFetch<void>(`/api/library/${id}`, { method: "DELETE" }),
  resetSystem: (): Promise<{ updated: number }> =>
    proxyFetch<{ updated: number }>("/api/library/reset-system", { method: "POST" }),
};

export const artifactsAPI = {
  createSelections: (
    callId: string,
    selections: { artifact_type_id: string; mode: ArtifactMode }[]
  ) =>
    proxyFetch<Artifact[]>(`/api/calls/${callId}/artifacts`, {
      method: "POST",
      body: JSON.stringify({ selections }),
    }),
  list: (callId: string) =>
    proxyFetch<Artifact[]>(`/api/calls/${callId}/artifacts`),
  update: (artifactId: string, data: { content?: string; status?: string; mode?: ArtifactMode }) =>
    proxyFetch<Artifact>(`/api/artifacts/${artifactId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (artifactId: string) =>
    proxyFetch<void>(`/api/artifacts/${artifactId}`, { method: "DELETE" }),
  deleteAll: (callId: string) =>
    proxyFetch<void>(`/api/calls/${callId}/artifacts`, { method: "DELETE" }),
};

export const topicsAPI = {
  extract: (callId: string) =>
    proxyFetch<import("@/types").ExtractionResult>(`/api/calls/${callId}/topics/extract`, {
      method: "POST",
    }),

  save: (callId: string, topics: import("@/types").TopicSavePayload[]) =>
    proxyFetch<{ saved: number }>(`/api/calls/${callId}/topics`, {
      method: "POST",
      body: JSON.stringify(topics),
    }),

  validate: (callId: string) =>
    proxyFetch<{ kanban_stage: string }>(`/api/calls/${callId}/topics/validate`, {
      method: "POST",
    }),

  brief: (callId: string) =>
    proxyFetch<import("@/types").CallBrief>(`/api/calls/${callId}/brief`),

  listForProject: (projectId: string) =>
    proxyFetch<import("@/types").TopicData[]>(`/api/projects/${projectId}/topics`),

  priorToCall: (projectId: string, callId: string) =>
    proxyFetch<import("@/types").TopicData[]>(`/api/projects/${projectId}/topics/prior-to-call/${callId}`),

  timeline: (projectId: string) =>
    proxyFetch<TopicsTimelineData>(`/api/projects/${projectId}/topics/timeline`),

  listForCall: (callId: string) =>
    proxyFetch<import("@/types").TopicData[]>(`/api/calls/${callId}/topics/by-call`),

  extractCall: (callId: string) =>
    proxyFetch<import("@/types").TopicData[]>(`/api/calls/${callId}/topics/extract_call`, {
      method: "POST",
    }),

  aggregate: (callId: string, topics: import("@/types").TopicData[]) =>
    proxyFetch<import("@/types").AggregateResult>(`/api/calls/${callId}/topics/aggregate`, {
      method: "POST",
      body: JSON.stringify({ topics }),
    }),

  deleteFromCall: (callId: string, topicId: string) =>
    proxyFetch<void>(`/api/calls/${callId}/topics/${topicId}`, { method: "DELETE" }),

  getPending: (callId: string) =>
    proxyFetch<import("@/types").TopicData[]>(`/api/calls/${callId}/topics/pending`),

  saveMatches: (callId: string, groups: import("@/types").MatchGroup[]) =>
    proxyFetch<{ saved: number }>(`/api/calls/${callId}/topics/save-matches`, {
      method: "POST",
      body: JSON.stringify(groups),
    }),

  // EPIC-19 — task-level save-matches endpoint (draft=true skips stage advance)
  saveTaskMatches: (callId: string, groups: TaskMatchGroup[], draft: boolean = false) =>
    proxyFetch<{ saved: number }>(`/api/calls/${callId}/topics/save-matches${draft ? '?draft=true' : ''}`, {
      method: "POST",
      body: JSON.stringify(groups),
    }),

  // EPIC-19 — load existing match groups (for restoring drafts on mount)
  loadTaskMatches: (callId: string) =>
    proxyFetch<TaskMatchGroup[]>(
      `/api/calls/${callId}/topics/match-groups`,
      { method: "GET" }
    ),

  getMatchGroups: (callId: string) =>
    proxyFetch<{ project_topic_ids: string[]; project_topic_names: string[]; call_topic_names: string[] }[]>(
      `/api/calls/${callId}/topics/match-groups`
    ),

  /** @deprecated EPIC-16: removed — use verifyNew + verifyNotDiscussed + extractUpdates instead. Stub kept until Task 12 rewrites ProjectUpdatesStage. */
  mergePreview: (_callId: string): Promise<never> => {
    throw new Error("mergePreview removed in EPIC-16 (Task 8). See verifyNew/verifyNotDiscussed/extractUpdates.");
  },

  validateUpdates: (callId: string, topics: import("@/types").TopicData[]) =>
    proxyFetch<{ status: string }>(`/api/calls/${callId}/topics/validate-updates`, {
      method: "POST",
      body: JSON.stringify(topics),
    }),

  verifyNew: (callId: string) =>
    proxyFetch<{ status: string }>(`/api/calls/${callId}/topics/verify-new`, { method: "POST" }),

  verifyNotDiscussed: (callId: string) =>
    proxyFetch<{ status: string }>(`/api/calls/${callId}/topics/verify-not-discussed`, {
      method: "POST",
    }),

  extractUpdates: (callId: string) =>
    proxyFetch<{ status: string }>(`/api/calls/${callId}/topics/extract-updates`, { method: "POST" }),

  promoteNotDiscussed: (callId: string, topicId: string) =>
    proxyFetch<{ ok: true; created: boolean }>(`/api/calls/${callId}/topics/promote-not-discussed`, {
      method: "POST",
      body: JSON.stringify({ topic_id: topicId }),
    }),

  getEvidence: (topicId: string) =>
    proxyFetch<import("@/types").TopicEvidence>(`/api/topics/${topicId}/evidence`),

  patch: (topic_id: string, body: Partial<{
    name: string;
    importance: "high" | "medium" | "low";
    key_terms: string[];
    evidence: EvidenceRef[];
    tasks: TaskData[];
    open_questions: (string | OpenQuestionData)[];
    decisions: (string | DecisionData)[];
  }>): Promise<TopicData> =>
    proxyFetch<TopicData>(`/api/topics/${topic_id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  // Delete a topic from a specific call.
  // Backend handles orphan cleanup: if no other call's update remains for this
  // topic, the topics row itself is removed (see routers/topics.py).
  // `topic_id` must be the topics.id (parent table FK), NOT topic_updates.id.
  deleteTopic: (call_id: string, topic_id: string): Promise<void> =>
    proxyFetch<void>(`/api/calls/${call_id}/topics/${topic_id}`, { method: "DELETE" }),
};

// ─────────────────────────────────────────────────────────────────────────────
// EPIC-20 Stage 1: Topic confirmation
// ─────────────────────────────────────────────────────────────────────────────

export type ExistingTopicEntry = { topic_id: string; name: string; tasks_count: number };
export type NewTopicCandidate = { name: string; v5_cluster_id: string | null; task_count: number };
export type FinalizedTopic = {
  id?: string;
  name: string;
  source: "existing" | "new";
  topic_id: string | null;
  v5_cluster_id?: string | null;
  position?: number;
  _original_name?: string;
};

export const topicConfirmationAPI = {
  load: (callId: string) =>
    proxyFetch<{
      existing: ExistingTopicEntry[];
      new_candidates: NewTopicCandidate[];
      finalized: FinalizedTopic[];
    }>(`/api/calls/${callId}/topic-confirmation`),

  save: (callId: string, topics: FinalizedTopic[]) =>
    proxyFetch<{ saved: number; renames_applied: number }>(
      `/api/calls/${callId}/topic-confirmation/save`,
      {
        method: "POST",
        body: JSON.stringify({ topics }),
      },
    ),
};
