import type { ChildProcess } from "child_process";

let serverProcess: ChildProcess | null = null;

export function getServerProcess(): ChildProcess | null {
  return serverProcess;
}

export function setServerProcess(p: ChildProcess | null): void {
  serverProcess = p;
}
