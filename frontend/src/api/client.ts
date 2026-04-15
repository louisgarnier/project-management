// All API calls route through the Next.js proxy at /api/proxy/
// This keeps secrets server-side and avoids CORS issues.
// SSE connections (artifact streaming) connect directly to the backend URL.

import type { Project, Call, CallFile, ArtifactType, Artifact, LLMProvider, ArtifactMode, ContextScope, TopicsTimelineData } from "@/types";

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
    throw new Error(parseApiError(error, response.status));
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
  update: (id: string, data: { default_llm?: LLMProvider; context?: string }) =>
    proxyFetch<Project>(`/api/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
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
    throw new Error(parseApiError(error, response.status));
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
  create: (projectId: string, data: { name: string; prompt: string }) =>
    proxyFetch<ArtifactType>(`/api/projects/${projectId}/artifact-types`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (
    projectId: string,
    typeId: string,
    data: { name?: string; prompt?: string; llm?: LLMProvider | null; context_scope?: ContextScope; is_default?: boolean }
  ) =>
    proxyFetch<ArtifactType>(`/api/projects/${projectId}/artifact-types/${typeId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (projectId: string, typeId: string) =>
    proxyFetch<void>(`/api/projects/${projectId}/artifact-types/${typeId}`, {
      method: "DELETE",
    }),
  import: (projectId: string, typeIds: string[]) =>
    proxyFetch<ArtifactType[]>(`/api/projects/${projectId}/artifact-types/import`, {
      method: "POST",
      body: JSON.stringify({ type_ids: typeIds }),
    }),
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

  getMatchGroups: (callId: string) =>
    proxyFetch<{ project_topic_id: string | null; project_topic_name: string | null; call_topic_names: string[] }[]>(
      `/api/calls/${callId}/topics/match-groups`
    ),

  mergePreview: (callId: string) =>
    proxyFetch<{ status: string }>(`/api/calls/${callId}/topics/merge-preview`, {
      method: "POST",
    }),

  validateUpdates: (callId: string, topics: import("@/types").TopicData[]) =>
    proxyFetch<{ status: string }>(`/api/calls/${callId}/topics/validate-updates`, {
      method: "POST",
      body: JSON.stringify(topics),
    }),
};
