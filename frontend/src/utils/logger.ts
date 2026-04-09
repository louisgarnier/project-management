const isDev = process.env.NODE_ENV === "development";

type LogOptions = {
  component?: string;
  data?: unknown;
};

function fmt(emoji: string, component: string | undefined, msg: string): string {
  return component ? `${emoji} [${component}] ${msg}` : `${emoji} ${msg}`;
}

export const logger = {
  info: (msg: string, opts?: LogOptions) => {
    if (!isDev) return;
    const line = fmt("📘", opts?.component, msg);
    if (opts?.data !== undefined) console.log(line, opts.data);
    else console.log(line);
  },
  warn: (msg: string, opts?: LogOptions) => {
    const line = fmt("⚠️", opts?.component, msg);
    if (opts?.data !== undefined) console.warn(line, opts.data);
    else console.warn(line);
  },
  error: (msg: string, opts?: LogOptions) => {
    const line = fmt("❌", opts?.component, msg);
    if (opts?.data !== undefined) console.error(line, opts.data);
    else console.error(line);
  },
  debug: (msg: string, opts?: LogOptions) => {
    if (!isDev) return;
    const line = fmt("🔍", opts?.component, msg);
    if (opts?.data !== undefined) console.debug(line, opts.data);
    else console.debug(line);
  },
  sse: (msg: string, data?: unknown) => {
    if (!isDev) return;
    const line = `📡 [SSE] ${msg}`;
    if (data !== undefined) console.log(line, data);
    else console.log(line);
  },
};
