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
    console.log(`${ts()} ⏳ [LocalServer] Status: starting`);
    return NextResponse.json({ running: false, starting: true });
  }

  return NextResponse.json({ running: false, starting: false });
}
