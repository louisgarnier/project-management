"use client";

import { useEffect, useState } from "react";
import { libraryAPI } from "@/api/client";
import type { LibraryEntry } from "@/types";
import LibraryEntryCard from "@/components/LibraryEntryCard";

export default function LibraryPage() {
  const [entries, setEntries] = useState<LibraryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setEntries(await libraryAPI.list());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function resetSystem() {
    if (!confirm("Restore all system library entries to their original defaults? Your edits to system entries will be lost. User-published entries are not affected.")) return;
    setResetting(true);
    try {
      await libraryAPI.resetSystem();
      await load();
    } catch (e) {
      alert(`Failed to reset: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setResetting(false);
    }
  }

  // Workflow Tier 1 entries come first (category != 'artifacts').
  // Then Tier 2 system artifact entries, then user-published.
  const workflowEntries = entries.filter(
    (e) => e.is_system && e.category !== "artifacts"
  );
  const systemArtifactEntries = entries.filter(
    (e) => e.is_system && e.category === "artifacts"
  );
  const userEntries = entries.filter((e) => !e.is_system);

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px 12px", background: "white", borderBottom: "1px solid #dfe1e6" }}>
        <h1 style={{ fontSize: 18, fontWeight: 700, color: "#172b4d", margin: 0 }}>Artifact Library</h1>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
        {loading && <p style={{ fontSize: 12, color: "#5e6c84" }}>Loading…</p>}
        {error && <p style={{ fontSize: 12, color: "#ae2a19" }}>Error: {error}</p>}
        {!loading && !error && (
          <>
            {/* Tier 1: Workflow Prompts */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#5e6c84", letterSpacing: ".05em" }}>
                  ⚙️ Workflow Prompts ({workflowEntries.length})
                </div>
                <div style={{ fontSize: 11, color: "#97a0af", marginTop: 2 }}>
                  Essential LLM prompts that run inside the extraction / matching / verification pipeline. Edit here to change the canonical default for all projects (existing projects must click Reset-to-default to adopt the change).
                </div>
              </div>
              <button
                type="button"
                onClick={resetSystem}
                disabled={resetting}
                style={{ fontSize: 11, color: "#5e6c84", background: "none", border: "1px solid #dfe1e6", borderRadius: 4, padding: "4px 10px", cursor: resetting ? "default" : "pointer", opacity: resetting ? 0.6 : 1, flexShrink: 0, marginLeft: 12 }}
              >
                {resetting ? "Resetting…" : "⟲ Reset all system to defaults"}
              </button>
            </div>
            {workflowEntries.length === 0 && (
              <p style={{ fontSize: 12, color: "#97a0af" }}>
                No workflow prompts in library. Run migration 023 + restart backend to seed.
              </p>
            )}
            {workflowEntries.map((e) => (
              <LibraryEntryCard key={e.id} entry={e} onUpdated={load} onDeleted={load} />
            ))}

            {/* Tier 2: System Artifact Prompts */}
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#5e6c84", letterSpacing: ".05em", marginTop: 24, marginBottom: 4 }}>
              📝 System Artifact Prompts ({systemArtifactEntries.length})
            </div>
            <div style={{ fontSize: 11, color: "#97a0af", marginBottom: 8 }}>
              Canonical artifact types (LLM / Template / Hybrid) that projects pick from. Edit here for the canonical version; projects already using them must click Reset-to-default to adopt the change.
            </div>
            {systemArtifactEntries.map((e) => (
              <LibraryEntryCard key={e.id} entry={e} onUpdated={load} onDeleted={load} />
            ))}

            {/* User-published */}
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#5e6c84", letterSpacing: ".05em", marginTop: 24, marginBottom: 4 }}>
              👤 Your Artifact Prompts ({userEntries.length})
            </div>
            <div style={{ fontSize: 11, color: "#97a0af", marginBottom: 8 }}>
              Custom artifact types you published from any project, available for reuse across projects.
            </div>
            {userEntries.length === 0 ? (
              <p style={{ fontSize: 12, color: "#97a0af" }}>
                No user-published entries yet. Publish a custom artifact type from any project via the &quot;↗ Publish to library&quot; button on its card.
              </p>
            ) : (
              userEntries.map((e) => (
                <LibraryEntryCard key={e.id} entry={e} onUpdated={load} onDeleted={load} />
              ))
            )}
          </>
        )}
      </div>
    </div>
  );
}
