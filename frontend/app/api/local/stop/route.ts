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
