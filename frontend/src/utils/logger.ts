const isDev = process.env.NODE_ENV === "development";

type LogOptions = {
  component?: string;
  data?: unknown;
};

function fmt(emoji: string, component: string | undefined, msg: string): string {
  return component ? `${emoji} [${component}] ${msg}` : `${emoji} ${msg}`;
}

function persist(level: string, line: string): void {
  // Fire-and-forget — never blocks the caller
  fetch("/api/logs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ level, message: line }),
  }).catch(() => {
    // Silently drop — log writes must never crash the app
  });
}

export const logger = {
  info: (msg: string, opts?: LogOptions) => {
    const line = fmt("📘", opts?.component, msg);
    if (isDev) {
      if (opts?.data !== undefined) console.log(line, opts.data);
      else console.log(line);
    }
    persist("info", opts?.data !== undefined ? `${line} ${JSON.stringify(opts.data)}` : line);
  },
  warn: (msg: string, opts?: LogOptions) => {
    const line = fmt("⚠️", opts?.component, msg);
    if (opts?.data !== undefined) console.warn(line, opts.data);
    else console.warn(line);
    persist("warn", opts?.data !== undefined ? `${line} ${JSON.stringify(opts.data)}` : line);
  },
  error: (msg: string, opts?: LogOptions) => {
    const line = fmt("❌", opts?.component, msg);
    if (opts?.data !== undefined) console.error(line, opts.data);
    else console.error(line);
    persist("error", opts?.data !== undefined ? `${line} ${JSON.stringify(opts.data)}` : line);
  },
  debug: (msg: string, opts?: LogOptions) => {
    if (!isDev) return;
    const line = fmt("🔍", opts?.component, msg);
    if (opts?.data !== undefined) console.debug(line, opts.data);
    else console.debug(line);
    persist("debug", opts?.data !== undefined ? `${line} ${JSON.stringify(opts.data)}` : line);
  },
  sse: (msg: string, data?: unknown) => {
    if (!isDev) return;
    const line = `📡 [SSE] ${msg}`;
    if (data !== undefined) console.log(line, data);
    else console.log(line);
    persist("info", data !== undefined ? `${line} ${JSON.stringify(data)}` : line);
  },
};
