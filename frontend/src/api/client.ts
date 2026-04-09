// All API calls route through the Next.js proxy at /api/proxy/
// This keeps secrets server-side and avoids CORS issues.
// SSE connections (artifact streaming) connect directly to the backend URL.

import type { Project, Call } from "@/types";

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
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  if (response.status === 204) return {} as T;
  return response.json();
}

export const healthAPI = {
  check: () => proxyFetch<{ status: string; db: string }>("/health"),
};

export const projectsAPI = {
  list: () => proxyFetch<Project[]>("/api/projects"),
  create: (data: { name: string; description: string }) =>
    proxyFetch<Project>("/api/projects", {
      method: "POST",
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
  submitTranscript: (callId: string, transcript: string) =>
    proxyFetch<Call>(`/api/calls/${callId}/transcript`, {
      method: "POST",
      body: JSON.stringify({ transcript }),
    }),
};

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

// Further API modules added per epic (artifacts, topics)
