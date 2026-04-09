// All API calls route through the Next.js proxy at /api/proxy/
// This keeps secrets server-side and avoids CORS issues.
// SSE connections (artifact streaming) connect directly to the backend URL.

const PROXY_BASE = "/api/proxy";

async function proxyFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
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

// Further API modules added per epic (projects, calls, artifacts, topics)
