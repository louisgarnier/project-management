# Server Control — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Start/Stop server button to the transcript stage badge so the user never needs a terminal.

**Architecture:** Three Next.js App Router route handlers (`/api/local/start`, `/api/local/stop`, `/api/local/status`) run on the local Node.js server and use `child_process.spawn` to manage the transcription process. A module-level singleton tracks the `ChildProcess` reference. The `TranscriptionStatusBadge` calls these routes and renders Start/Stop controls based on server state. `OfflineModal` is deleted.

**Tech Stack:** Next.js 15 App Router, TypeScript, Node.js `child_process`, Tailwind v4

---

## Context for implementers

- Working directory: `/Users/louisgarnier/Claude/Project management`
- All git commits via: `python3 scripts/git_ops.py commit -m "message"`
- Run lint: `cd frontend && npx eslint . --max-warnings 0`
- No automated frontend tests — verify with ESLint only
- Tailwind v4: `@import "tailwindcss"` in globals.css, no tailwind.config.js
- `process.cwd()` in Next.js dev mode = the `frontend/` directory (where `package.json` lives)
- So `run_transcription.sh` is at: `path.join(process.cwd(), '..', 'run_transcription.sh')`
- The proxy at `/api/proxy/` is unrelated — local routes live at `/api/local/` and are NOT proxied

## Current state of files being changed

### `frontend/src/api/client.ts` — add `localServerAPI` after `transcriptionAPI`

### `frontend/src/components/TranscriptionStatusBadge.tsx` — full replacement

Current version polls `transcriptionAPI.health()` every 30s and renders a static badge. Replacing with a stateful badge that polls `localServerAPI.status()` every 5s and renders Start/Stop buttons.

### `frontend/src/components/TranscriptStage.tsx` — remove OfflineModal

Remove: `import OfflineModal`, `showOfflineModal` state, `setShowOfflineModal(true)` call, `<OfflineModal .../>` render. Replace the offline guard in `handleMp3Change` with an inline error message.

### `frontend/src/components/OfflineModal.tsx` — delete

---

## Task 1: Local server API routes

**Files:**
- Create: `frontend/app/api/local/process.ts`
- Create: `frontend/app/api/local/start/route.ts`
- Create: `frontend/app/api/local/stop/route.ts`
- Create: `frontend/app/api/local/status/route.ts`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Create `frontend/app/api/local/process.ts`**

This is the singleton that holds the spawned process reference. Module-level state persists between requests in Next.js dev mode.

```typescript
import type { ChildProcess } from "child_process";

let serverProcess: ChildProcess | null = null;

export function getServerProcess(): ChildProcess | null {
  return serverProcess;
}

export function setServerProcess(p: ChildProcess | null): void {
  serverProcess = p;
}
```

- [ ] **Step 2: Create `frontend/app/api/local/start/route.ts`**

```typescript
import { NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import { getServerProcess, setServerProcess } from "../process";

const ts = () => new Date().toISOString().replace("T", " ").substring(0, 23);

export async function POST(): Promise<NextResponse> {
  const existing = getServerProcess();
  if (existing && !existing.killed) {
    console.log(`${ts()} ℹ️ [LocalServer] Already running (PID ${existing.pid})`);
    return NextResponse.json({ ok: true, message: "Already running" });
  }

  const projectRoot = path.join(process.cwd(), "..");
  const scriptPath = path.join(projectRoot, "run_transcription.sh");
  console.log(`${ts()} 🚀 [LocalServer] Starting: ${scriptPath}`);

  const child = spawn("bash", [scriptPath], {
    cwd: projectRoot,
    detached: false,
    stdio: "inherit",
  });

  child.on("error", (err) => {
    console.error(`${ts()} ❌ [LocalServer] Failed to start:`, err.message);
    setServerProcess(null);
  });

  child.on("exit", (code) => {
    console.log(`${ts()} 🛑 [LocalServer] Exited with code ${code}`);
    setServerProcess(null);
  });

  setServerProcess(child);
  console.log(`${ts()} ✅ [LocalServer] Spawned (PID ${child.pid})`);
  return NextResponse.json({ ok: true, pid: child.pid });
}
```

- [ ] **Step 3: Create `frontend/app/api/local/stop/route.ts`**

```typescript
import { NextResponse } from "next/server";
import { getServerProcess, setServerProcess } from "../process";

const ts = () => new Date().toISOString().replace("T", " ").substring(0, 23);

export async function POST(): Promise<NextResponse> {
  const proc = getServerProcess();
  if (!proc || proc.killed) {
    console.log(`${ts()} ℹ️ [LocalServer] Not running`);
    return NextResponse.json({ ok: true, message: "Not running" });
  }

  proc.kill("SIGTERM");
  setServerProcess(null);
  console.log(`${ts()} 🛑 [LocalServer] Stopped`);
  return NextResponse.json({ ok: true });
}
```

- [ ] **Step 4: Create `frontend/app/api/local/status/route.ts`**

The status route checks the process reference first, then falls back to a direct health check. This means it correctly reports "online" even if the server was started externally (outside the app).

```typescript
import { NextResponse } from "next/server";
import { getServerProcess } from "../process";

const ts = () => new Date().toISOString().replace("T", " ").substring(0, 23);

async function isHealthy(): Promise<boolean> {
  try {
    const r = await fetch("http://localhost:8001/health", {
      signal: AbortSignal.timeout(1000),
    });
    return r.ok;
  } catch {
    return false;
  }
}

export async function GET(): Promise<NextResponse> {
  const proc = getServerProcess();
  const processAlive = proc !== null && !proc.killed;

  const healthy = await isHealthy();

  if (healthy) {
    console.log(`${ts()} ✅ [LocalServer] Status: running`);
    return NextResponse.json({ running: true, starting: false });
  }

  if (processAlive) {
    // Process was spawned but not yet responding — still starting up
    console.log(`${ts()} ⏳ [LocalServer] Status: starting`);
    return NextResponse.json({ running: false, starting: true });
  }

  return NextResponse.json({ running: false, starting: false });
}
```

- [ ] **Step 5: Add `localServerAPI` to `frontend/src/api/client.ts`**

Add this block after the `transcriptionAPI` export (before the comment at the end of the file):

```typescript
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
```

- [ ] **Step 6: Lint**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend && npx eslint app/api/local src/api/client.ts --max-warnings 0
```

Expected: 0 errors, 0 warnings

- [ ] **Step 7: Commit**

```bash
python3 scripts/git_ops.py commit -m "[EPIC-4] feat: local server API routes — start, stop, status + localServerAPI client"
```

---

## Task 2: Update TranscriptionStatusBadge

**Files:**
- Modify: `frontend/src/components/TranscriptionStatusBadge.tsx`

The badge gains 4 states: `offline | starting | online | stopping`. It polls `/api/local/status` every 5 seconds. Start/Stop buttons appear inline next to the badge.

- [ ] **Step 1: Replace `frontend/src/components/TranscriptionStatusBadge.tsx` entirely**

```typescript
"use client";

import { useCallback, useEffect, useState } from "react";
import { localServerAPI } from "@/api/client";
import { logger } from "@/utils/logger";

type ServerState = "offline" | "starting" | "online" | "stopping";

export default function TranscriptionStatusBadge() {
  const [state, setState] = useState<ServerState | null>(null);

  const poll = useCallback(async () => {
    const status = await localServerAPI.status();
    if (status.running) {
      setState("online");
    } else if (status.starting) {
      setState("starting");
    } else {
      setState("offline");
    }
  }, []);

  useEffect(() => {
    poll();
    const interval = setInterval(poll, 5_000);
    return () => clearInterval(interval);
  }, [poll]);

  async function handleStart() {
    setState("starting");
    logger.info("Starting transcription server", { component: "TranscriptionStatusBadge" });
    try {
      await localServerAPI.start();
    } catch (err) {
      logger.error("Failed to start server", { component: "TranscriptionStatusBadge", data: err });
      setState("offline");
    }
  }

  async function handleStop() {
    setState("stopping");
    logger.info("Stopping transcription server", { component: "TranscriptionStatusBadge" });
    try {
      await localServerAPI.stop();
    } catch (err) {
      logger.error("Failed to stop server", { component: "TranscriptionStatusBadge", data: err });
    }
    poll();
  }

  if (state === null) return null;

  if (state === "online") {
    return (
      <div className="inline-flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#006644] bg-[#e3fcef] px-2 py-0.5 rounded-full">
          <span className="w-1.5 h-1.5 rounded-full bg-[#36b37e]" />
          Server online
        </span>
        <button
          onClick={handleStop}
          className="text-[11px] text-[#5e6c84] bg-[#f4f5f7] px-2 py-0.5 rounded hover:bg-[#dfe1e6]"
        >
          Stop
        </button>
      </div>
    );
  }

  if (state === "starting" || state === "stopping") {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#5e6c84] bg-[#f4f5f7] px-2 py-0.5 rounded-full">
        <span className="w-1.5 h-1.5 rounded-full bg-[#97a0af] animate-pulse" />
        {state === "starting" ? "Starting…" : "Stopping…"}
      </span>
    );
  }

  // offline
  return (
    <div className="inline-flex items-center gap-2">
      <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[#974f0c] bg-[#fff4e6] px-2 py-0.5 rounded-full">
        <span className="w-1.5 h-1.5 rounded-full bg-[#ff8b00]" />
        Server offline
      </span>
      <button
        onClick={handleStart}
        className="text-[11px] text-white bg-[#0052cc] px-2 py-0.5 rounded hover:bg-[#0065ff]"
      >
        Start server
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Lint**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend && npx eslint src/components/TranscriptionStatusBadge.tsx --max-warnings 0
```

Expected: 0 errors, 0 warnings

- [ ] **Step 3: Commit**

```bash
python3 scripts/git_ops.py commit -m "[EPIC-4] feat: TranscriptionStatusBadge — start/stop controls, 4-state polling"
```

---

## Task 3: Remove OfflineModal from TranscriptStage, delete OfflineModal.tsx

**Files:**
- Modify: `frontend/src/components/TranscriptStage.tsx`
- Delete: `frontend/src/components/OfflineModal.tsx`

- [ ] **Step 1: Replace `frontend/src/components/TranscriptStage.tsx` entirely**

The `showOfflineModal` state, the `OfflineModal` import, and the `OfflineModal` render are removed. The offline guard in `handleMp3Change` now sets an inline error instead.

```typescript
"use client";

import { useEffect, useRef, useState } from "react";
import { callsAPI, transcriptionAPI } from "@/api/client";
import { logger } from "@/utils/logger";
import type { Call } from "@/types";
import TranscriptionStatusBadge from "@/components/TranscriptionStatusBadge";

interface Props {
  call: Call;
  onAdvance: () => void;
}

export default function TranscriptStage({ call, onAdvance }: Props) {
  const [uploading, setUploading] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mp3Ref = useRef<HTMLInputElement>(null);
  const txtRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!uploading) return;
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [uploading]);

  async function handleMp3Change(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    const online = await transcriptionAPI.health();
    if (!online) {
      logger.info("Transcription server offline", { component: "TranscriptStage" });
      setError("Server is offline. Use the Start server button above.");
      return;
    }

    setUploading(true);
    setError(null);
    let success = false;
    try {
      setStatusMsg("Transcribing… this may take a few minutes.");
      logger.info("Starting MP3 transcription", { component: "TranscriptStage", data: { callId: call.id } });
      const transcript = await transcriptionAPI.transcribe(file);
      setStatusMsg("Saving transcript…");
      await callsAPI.submitTranscript(call.id, transcript);
      logger.info("Transcript submitted", { component: "TranscriptStage", data: { callId: call.id } });
      success = true;
    } catch (err) {
      logger.error("Transcription failed", { component: "TranscriptStage", data: err });
      setError(err instanceof Error ? err.message : "Transcription failed. Please try again.");
    } finally {
      setUploading(false);
      setStatusMsg(null);
    }
    if (success) onAdvance();
  }

  async function handleTxtChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    setUploading(true);
    setError(null);
    let success = false;
    try {
      setStatusMsg("Reading file…");
      logger.info("Submitting .txt transcript", { component: "TranscriptStage", data: { callId: call.id } });
      const transcript = await file.text();
      setStatusMsg("Saving transcript…");
      await callsAPI.submitTranscript(call.id, transcript);
      logger.info("Transcript submitted", { component: "TranscriptStage", data: { callId: call.id } });
      success = true;
    } catch (err) {
      logger.error("TXT upload failed", { component: "TranscriptStage", data: err });
      setError(err instanceof Error ? err.message : "Upload failed. Please try again.");
    } finally {
      setUploading(false);
      setStatusMsg(null);
    }
    if (success) onAdvance();
  }

  if (uploading) {
    return (
      <div className="bg-white border border-[#dfe1e6] rounded-lg">
        <div className="px-4 py-3 border-b border-[#dfe1e6] flex items-center justify-between">
          <span className="text-[14px] font-semibold text-[#172b4d]">Get Transcript</span>
          <TranscriptionStatusBadge />
        </div>
        <div className="p-8 text-center">
          <div className="text-[13px] font-medium text-[#172b4d] mb-1">{statusMsg}</div>
          <div className="text-[12px] text-[#5e6c84]">Do not close this tab.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-[#dfe1e6] rounded-lg">
      <div className="px-4 py-3 border-b border-[#dfe1e6] flex items-center justify-between">
        <span className="text-[14px] font-semibold text-[#172b4d]">Get Transcript</span>
        <TranscriptionStatusBadge />
      </div>
      <div className="p-4">
        {error && (
          <div className="mb-3 text-[12px] text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
            {error}
          </div>
        )}

        {/* MP3 upload */}
        <div
          onClick={() => mp3Ref.current?.click()}
          className="border-2 border-dashed border-[#dfe1e6] rounded-md p-6 text-center cursor-pointer hover:border-[#0052cc] hover:bg-[#f8f9ff] transition-colors mb-3"
        >
          <div className="text-2xl mb-2">🎵</div>
          <div className="text-[14px] font-semibold text-[#172b4d] mb-1">Upload MP3</div>
          <div className="text-[12px] text-[#5e6c84]">Transcribed locally via Whisper + pyannote</div>
        </div>
        <input ref={mp3Ref} type="file" accept=".mp3" className="hidden" onChange={handleMp3Change} />

        <div className="flex items-center gap-2 my-3">
          <hr className="flex-1 border-[#dfe1e6]" />
          <span className="text-[11px] text-[#97a0af] uppercase tracking-wide">or</span>
          <hr className="flex-1 border-[#dfe1e6]" />
        </div>

        {/* TXT upload */}
        <div
          onClick={() => txtRef.current?.click()}
          className="border-2 border-dashed border-[#dfe1e6] rounded-md p-6 text-center cursor-pointer hover:border-[#0052cc] hover:bg-[#f8f9ff] transition-colors"
        >
          <div className="text-2xl mb-2">📄</div>
          <div className="text-[14px] font-semibold text-[#172b4d] mb-1">Upload transcript (.txt)</div>
          <div className="text-[12px] text-[#5e6c84]">Already have a transcript? Upload it directly.</div>
        </div>
        <input ref={txtRef} type="file" accept=".txt" className="hidden" onChange={handleTxtChange} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Delete `frontend/src/components/OfflineModal.tsx`**

```bash
rm /Users/louisgarnier/Claude/Project\ management/frontend/src/components/OfflineModal.tsx
```

- [ ] **Step 3: Full lint**

```bash
cd /Users/louisgarnier/Claude/Project\ management/frontend && npx eslint . --max-warnings 0
```

Expected: 0 errors, 0 warnings

- [ ] **Step 4: Commit**

```bash
python3 scripts/git_ops.py commit -m "[EPIC-4] feat: remove OfflineModal, inline error on offline MP3 attempt"
```

---

## Dev Tests (manual, in order)

With `npm run dev` running from `frontend/`:

1. **Badge shows offline** — load the transcript stage page, badge should show "Server offline" + "Start server" button
2. **Start server** — click "Start server" → badge shows "Starting…" → within ~30s transitions to "Server online" + "Stop" button
3. **MP3 upload while online** — choose an MP3 → "Transcribing…" message appears
4. **Stop server** — click "Stop" → badge shows "Stopping…" → transitions to "Server offline"
5. **MP3 upload while offline** — choose an MP3 → red inline error "Server is offline. Use the Start server button above." — no modal, no terminal
6. **TXT upload works regardless of server state** — choose a .txt → advances to Artifacts stage
