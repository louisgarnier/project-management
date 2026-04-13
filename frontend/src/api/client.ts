// All API calls route through the Next.js proxy at /api/proxy/
// This keeps secrets server-side and avoids CORS issues.
// SSE connections (artifact streaming) connect directly to the backend URL.

import type { Project, Call, CallFile, ArtifactType, Artifact, LLMProvider, ArtifactMode } from "@/types";

const PROXY_BASE = "/api/proxy";

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
    throw new Error((error && error.detail) || `HTTP ${response.status}`);
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
  update: (id: string, data: { default_llm: LLMProvider }) =>
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
  delete: (callId: string) => proxyFetch<void>(`/api/calls/${callId}`, { method: "DELETE" }),
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
    throw new Error((error && error.detail) || `HTTP ${response.status}`);
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
    data: { name?: string; prompt?: string; llm?: LLMProvider | null }
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
