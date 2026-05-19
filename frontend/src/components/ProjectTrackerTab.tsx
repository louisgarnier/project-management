"use client";
import { useEffect, useMemo, useState } from "react";
import { logger } from "@/utils/logger";
import { projectsAPI } from "@/api/client";
import type { TopicWithCallHistory } from "@/types";
import DashboardView from "./tracker/DashboardView";
import ChronologyView from "./tracker/ChronologyView";
import AnchorsLifecycleView from "./tracker/AnchorsLifecycleView";
import DecisionsLogView from "./tracker/DecisionsLogView";
import KeyTermsRegistryView from "./tracker/KeyTermsRegistryView";

type SubView = "dashboard" | "chronology" | "anchors" | "decisions" | "key-terms";

const TABS: { id: SubView; label: string; info: string }[] = [
  { id: "dashboard", label: "Dashboard", info: "High-level counts: topics, open questions, decisions, tasks by status." },
  { id: "chronology", label: "Chronology", info: "One row per topic, one column per call. Each cell is a frozen 2-3 sentence summary of what happened to that topic in that call." },
  { id: "anchors", label: "Anchors lifecycle", info: "One row per task or open question with added-in / closed-in call dates." },
  { id: "decisions", label: "Decisions log", info: "Every decision, the topic it belongs to, and the call where it was decided." },
  { id: "key-terms", label: "Key terms registry", info: "Every key term, its topic, and the first call where it appeared." },
];

const VALID_VIEWS: ReadonlySet<SubView> = new Set([
  "dashboard", "chronology", "anchors", "decisions", "key-terms",
]);

function readHashView(): SubView {
  if (typeof window === "undefined") return "dashboard";
  const raw = window.location.hash.slice(1);
  return VALID_VIEWS.has(raw as SubView) ? (raw as SubView) : "dashboard";
}

type Props = { projectId: string };

export default function ProjectTrackerTab({ projectId }: Props) {
  const [currentView, setCurrentView] = useState<SubView>("dashboard");
  const [topics, setTopics] = useState<TopicWithCallHistory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Read hash on mount and on hashchange
  useEffect(() => {
    setCurrentView(readHashView());
    const onHash = () => setCurrentView(readHashView());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // Fetch per-(topic, call) data once on mount (or when projectId changes)
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    projectsAPI
      .getTrackerData(projectId)
      .then((data) => {
        if (cancelled) return;
        setTopics(data);
        logger.info("[ProjectTrackerTab] Tracker data loaded", {
          data: { projectId, topicCount: data.length },
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : String(err);
        logger.error("[ProjectTrackerTab] Tracker data fetch failed", { data: { projectId, error: msg } });
        setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [projectId]);

  const onTabClick = (id: SubView) => {
    if (typeof window !== "undefined") {
      window.location.hash = id;
    }
    setCurrentView(id);
  };

  const onExport = () => {
    // Same-origin proxy route so the browser downloads without CORS friction
    logger.info("[ProjectTrackerTab] Export xlsx requested", { data: { projectId } });
    window.location.href = `/api/proxy/projects/${projectId}/export.xlsx`;
  };

  // Kept for accessibility / potential future header rendering, but body now uses sub-views.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const activeTab = useMemo(
    () => TABS.find((t) => t.id === currentView) ?? TABS[0],
    [currentView],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Header row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <h2 style={{ fontSize: 17, fontWeight: 700, color: "#172b4d", margin: 0 }}>
          Project tracker
        </h2>
        <button
          onClick={onExport}
          style={{
            padding: "8px 16px",
            background: "#0052cc",
            color: "white",
            border: "none",
            borderRadius: 4,
            fontSize: 12,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          ⬇ Export to xlsx
        </button>
      </div>

      {/* Tab strip */}
      <div
        style={{
          display: "flex",
          gap: 16,
          borderBottom: "1px solid #dfe1e6",
        }}
      >
        {TABS.map((t) => {
          const isActive = t.id === currentView;
          return (
            <button
              key={t.id}
              onClick={() => onTabClick(t.id)}
              style={{
                padding: "8px 0",
                background: "transparent",
                border: "none",
                borderBottom: isActive ? "2px solid #0052cc" : "2px solid transparent",
                color: isActive ? "#0052cc" : "#42526e",
                fontWeight: isActive ? 600 : 500,
                fontSize: 12.5,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 4,
              }}
            >
              <span>{t.label}</span>
              <span
                title={t.info}
                style={{
                  fontSize: 11,
                  color: "#7a869a",
                  cursor: "help",
                  marginLeft: 2,
                }}
              >
                ⓘ
              </span>
            </button>
          );
        })}
      </div>

      {/* Body */}
      <div style={{ minHeight: 200 }}>
        {loading && <div style={{ color: "#5e6c84", fontSize: 12 }}>Loading…</div>}
        {error && (
          <div style={{
            background: "#fff1f0",
            border: "1px solid #ffbdad",
            borderRadius: 6,
            padding: "10px 14px",
            fontSize: 12,
            color: "#ae2a19",
          }}>
            {error}
          </div>
        )}
        {!loading && !error && (
          <>
            {currentView === "dashboard" && <DashboardView topics={topics} />}
            {currentView === "chronology" && <ChronologyView topics={topics} />}
            {currentView === "anchors" && <AnchorsLifecycleView topics={topics} />}
            {currentView === "decisions" && <DecisionsLogView topics={topics} />}
            {currentView === "key-terms" && <KeyTermsRegistryView topics={topics} />}
          </>
        )}
      </div>
    </div>
  );
}
