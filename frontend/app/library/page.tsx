"use client";

import { useEffect, useState } from "react";
import { libraryAPI, settingsAPI } from "@/api/client";
import type { LibraryEntry, SystemSettings, LLMProvider } from "@/types";
import LibraryEntryCard from "@/components/LibraryEntryCard";

export default function LibraryPage() {
  const [entries, setEntries] = useState<LibraryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [systemSettings, setSystemSettings] = useState<SystemSettings | null>(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsDraft, setSettingsDraft] = useState<SystemSettings>({ default_llm: "openrouter", default_model: "deepseek/deepseek-v3.2" });

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

  useEffect(() => {
    settingsAPI.get().then((s) => {
      setSystemSettings(s);
      setSettingsDraft(s);
    }).catch((e) => console.error("settings load failed", e));
  }, []);

  async function saveSettings() {
    setSavingSettings(true);
    try {
      const updated = await settingsAPI.update(settingsDraft);
      setSystemSettings(updated);
      setSettingsDraft(updated);
    } catch (e) {
      alert(`Failed to save: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSavingSettings(false);
    }
  }

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
            {/* System Defaults */}
            {systemSettings && (
              <div style={{ background: "white", padding: "16px 18px", border: "1px solid #dfe1e6", borderRadius: 6, marginBottom: 20 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                  <h3 style={{ fontSize: 14, fontWeight: 700, color: "#172b4d", margin: 0 }}>🌍 System Defaults</h3>
                  <span style={{ fontSize: 10, color: "#97a0af" }}>Applied to every NEW project created from now on</span>
                </div>
                <p style={{ fontSize: 11, color: "#5e6c84", margin: "0 0 12px", lineHeight: 1.5 }}>
                  These drive the fallback for every artifact or workflow prompt that has <code style={{ fontSize: 10, background: "#f4f5f7", padding: "1px 4px" }}>llm=null</code>. Changing them does <strong>not</strong> retroactively apply to existing projects — use Reset-to-default on each project&apos;s cards to adopt the new values.
                </p>
                <div style={{ display: "flex", gap: 12, alignItems: "end" }}>
                  <div style={{ flex: 1 }}>
                    <label style={{ fontSize: 10, color: "#5e6c84", display: "block", marginBottom: 3 }}>PROVIDER</label>
                    <select
                      value={settingsDraft.default_llm ?? "openrouter"}
                      onChange={(e) => setSettingsDraft({ ...settingsDraft, default_llm: e.target.value as LLMProvider })}
                      style={{ fontSize: 12, border: "1px solid #dfe1e6", borderRadius: 4, padding: "5px 8px", fontFamily: "inherit", width: "100%" }}
                    >
                      <option value="openrouter">OpenRouter ⭐</option>
                      <option value="groq">Groq (direct)</option>
                      <option value="deepseek">DeepSeek (direct)</option>
                      <option value="claude">Claude (direct)</option>
                      <option value="openai">OpenAI (direct)</option>
                    </select>
                  </div>
                  <div style={{ flex: 2 }}>
                    <label style={{ fontSize: 10, color: "#5e6c84", display: "block", marginBottom: 3 }}>MODEL (OpenRouter slug)</label>
                    <input
                      type="text"
                      value={settingsDraft.default_model ?? ""}
                      onChange={(e) => setSettingsDraft({ ...settingsDraft, default_model: e.target.value })}
                      placeholder="e.g. deepseek/deepseek-v3.2 — or any slug from openrouter.ai/models"
                      style={{ fontSize: 12, border: "1px solid #dfe1e6", borderRadius: 4, padding: "5px 8px", fontFamily: "ui-monospace, Menlo, monospace", width: "100%", boxSizing: "border-box" }}
                    />
                  </div>
                  <button
                    type="button"
                    onClick={saveSettings}
                    disabled={savingSettings || (settingsDraft.default_llm === systemSettings.default_llm && settingsDraft.default_model === systemSettings.default_model)}
                    style={{ fontSize: 11, fontWeight: 600, color: "white", background: "#0052cc", border: "none", borderRadius: 4, padding: "6px 14px", cursor: "pointer", opacity: savingSettings ? 0.6 : 1 }}
                  >
                    {savingSettings ? "Saving…" : "Save"}
                  </button>
                </div>
              </div>
            )}

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
