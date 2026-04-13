"use client";

import { useRouter, useParams } from "next/navigation";
import type { Call, KanbanStage } from "@/types";

const STAGES: { key: KanbanStage; label: string }[] = [
  { key: "transcript", label: "Transcript" },
  { key: "topics",     label: "Topics"     },
  { key: "artifacts",  label: "Artifacts"  },
  { key: "done",       label: "Done"       },
];

const STAGE_ORDER: KanbanStage[] = ["transcript", "topics", "artifacts", "done"];

const STAGE_INDEX: Record<KanbanStage, number> = Object.fromEntries(
  STAGE_ORDER.map((s, i) => [s, i])
) as Record<KanbanStage, number>;

type CellState = "done" | "active" | "pending" | "locked";

const CELL_STYLE: Record<CellState, React.CSSProperties> = {
  done:    { background: "#f0fdf4", border: "1px solid #bbf7d0" },
  active:  { background: "#ffffff",  border: "1.5px solid #ff8b00" },
  locked:  { background: "#f4f5f7", border: "1px dashed #b3c6e8", opacity: 0.7 },
  pending: { background: "#f4f5f7", border: "1px dashed #dfe1e6" },
};

const STATUS_LABEL: Record<CellState, string> = {
  done:    "✓ Done",
  active:  "→ Active",
  locked:  "Locked",
  pending: "—",
};

const STATUS_BADGE: Record<CellState, React.CSSProperties> = {
  done:    { background: "#bbf7d0", color: "#15803d" },
  active:  { background: "#fff4e6", color: "#974f0c" },
  locked:  { background: "#f4f5f7", color: "#97a0af" },
  pending: { background: "#f4f5f7", color: "#b3bac5" },
};

/**
 * Returns the display state for a single stage cell on a given call.
 *
 * done    — call has already passed this stage
 * active  — this is the call's current stage
 * locked  — stage is artifacts/topics AND the previous call is not fully done
 * pending — stage not yet reached, but reachable
 */
function getCellState(
  call: Call,
  stageKey: KanbanStage,
  prevCallDone: boolean
): CellState {
  const callIdx  = STAGE_INDEX[call.kanban_stage];
  const stageIdx = STAGE_INDEX[stageKey];

  if (callIdx > stageIdx) return "done";
  if (callIdx === stageIdx) {
    // A locked done call is fully finalized — show green done state
    if (stageKey === "done" && call.is_locked) return "done";
    return "active";
  }

  // Stage not yet reached — lock artifacts and topics if prev call is incomplete
  if (stageKey === "artifacts" && !prevCallDone) {
    return "locked";
  }
  return "pending";
}

type Props = {
  calls: Call[];
  onNewCall: () => void;
  onDeleteCall: (callId: string) => void;
};

export default function KanbanBoard({ calls, onNewCall, onDeleteCall }: Props) {
  const router    = useRouter();
  const params    = useParams<{ id: string }>();
  const projectId = params.id;
  if (!projectId) throw new Error("KanbanBoard rendered outside [id] route");

  // Oldest call first
  const sorted = [...calls].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );

  if (sorted.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-[13px] text-[#5e6c84]">No calls yet. Create your first call above.</p>
      </div>
    );
  }

  return (
    <div className="p-4 flex flex-col gap-3 flex-1 overflow-y-auto">

      {/* ── Column headers ── */}
      <div className="flex items-center gap-2">
        {/* Spacer mirrors the call-label column width + padding */}
        <div className="flex-shrink-0 w-[140px] pr-4" />
        <div className="flex-1 flex">
          {STAGES.map((s) => (
            <div
              key={s.key}
              className="flex-1 text-center text-[10px] font-bold uppercase tracking-[0.06em] text-[#5e6c84] px-2"
            >
              {s.label}
            </div>
          ))}
        </div>
      </div>

      {/* ── One row per call ── */}
      {sorted.map((call, idx) => {
        const prevCall     = idx > 0 ? sorted[idx - 1] : null;
        const prevCallDone = prevCall == null || prevCall.kanban_stage === "done";

        return (
          <div key={call.id} className="flex items-stretch gap-2">

            {/* Call label */}
            <div className="flex-shrink-0 w-[140px] flex flex-col justify-center pr-4 group/label relative">
              <span className="text-[12px] font-bold text-[#172b4d]">
                Call {idx + 1}
              </span>
              <span className="text-[11px] text-[#5e6c84] truncate leading-snug mt-0.5">
                {call.title}
              </span>
              <span className="text-[10px] text-[#97a0af] mt-1">
                {new Date(call.created_at).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })}
              </span>
              <button
                onClick={() => {
                  if (confirm(`Delete "${call.title}"? This will also delete its transcript, artifacts, and files.`)) {
                    onDeleteCall(call.id);
                  }
                }}
                className="absolute top-0 right-4 opacity-0 group-hover/label:opacity-100 text-[#97a0af] hover:text-red-500 text-[13px] transition-opacity leading-none"
                title="Delete call"
              >
                ✕
              </button>
            </div>

            {/* Stage cells */}
            <div className="flex-1 bg-white border border-[#dfe1e6] rounded-lg flex gap-2 p-2">
              {STAGES.map((s) => {
                const state     = getCellState(call, s.key, prevCallDone);
                const clickable = state === "active" || state === "done";

                return (
                  <div
                    key={s.key}
                    onClick={() => {
                      if (state === "active") {
                        router.push(`/projects/${projectId}/calls/${call.id}`);
                      } else if (state === "done") {
                        router.push(`/projects/${projectId}/calls/${call.id}?view=${s.key}`);
                      }
                    }}
                    className="flex-1 rounded-md flex flex-col justify-between p-2.5 min-h-[72px]"
                    style={{ ...CELL_STYLE[state], cursor: clickable ? "pointer" : "default" }}
                  >
                    <span
                      className="text-[11px] font-semibold"
                      style={{ color: clickable ? "#172b4d" : "#97a0af" }}
                    >
                      {s.label}
                    </span>
                    <span
                      className="text-[9px] font-bold uppercase tracking-[0.04em] px-[6px] py-[2px] rounded-[3px] self-start"
                      style={STATUS_BADGE[state]}
                    >
                      {STATUS_LABEL[state]}
                    </span>
                  </div>
                );
              })}
            </div>

          </div>
        );
      })}

      {/* ── Add new call ── */}
      <div className="flex items-center gap-2">
        <div className="flex-shrink-0 w-[140px] pr-4" />
        <button
          onClick={onNewCall}
          className="flex-1 py-2 border border-dashed border-[#b3c6e8] rounded-lg text-[12px] text-[#0052cc] font-medium hover:bg-[#e9f0ff] transition-colors"
        >
          + New Call
        </button>
      </div>

    </div>
  );
}
