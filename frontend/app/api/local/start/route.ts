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
