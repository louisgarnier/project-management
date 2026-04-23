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

  const systemEntries = entries.filter((e) => e.is_system);
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
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#5e6c84", letterSpacing: ".05em" }}>
                🏛 System ({systemEntries.length})
              </div>
              <button
                type="button"
                onClick={resetSystem}
                disabled={resetting}
                style={{ fontSize: 11, color: "#5e6c84", background: "none", border: "1px solid #dfe1e6", borderRadius: 4, padding: "4px 10px", cursor: resetting ? "default" : "pointer", opacity: resetting ? 0.6 : 1 }}
              >
                {resetting ? "Resetting…" : "⟲ Reset system to defaults"}
              </button>
            </div>
            {systemEntries.map((e) => (
              <LibraryEntryCard key={e.id} entry={e} onUpdated={load} onDeleted={load} />
            ))}

            <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#5e6c84", letterSpacing: ".05em", marginTop: 20, marginBottom: 8 }}>
              👤 Yours ({userEntries.length})
            </div>
            {userEntries.length === 0 && (
              <p style={{ fontSize: 12, color: "#97a0af" }}>
                No user-published entries yet. Publish a custom artifact type from any project via the &quot;↗ Publish to library&quot; button on its card.
              </p>
            )}
            {userEntries.map((e) => (
              <LibraryEntryCard key={e.id} entry={e} onUpdated={load} onDeleted={load} />
            ))}
          </>
        )}
      </div>
    </div>
  );
}
