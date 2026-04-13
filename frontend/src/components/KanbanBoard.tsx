"use client";

import { useRouter, useParams } from "next/navigation";
import type { Call, KanbanStage } from "@/types";

const STAGES: { key: KanbanStage; label: string }[] = [
  { key: "transcript", label: "Transcript" },
  { key: "artifacts",  label: "Artifacts"  },
  { key: "topics",     label: "Topics"     },
  { key: "done",       label: "Done"       },
];

const STAGE_ORDER: KanbanStage[] = ["transcript", "artifacts", "topics", "done"];

const STAGE_INDEX: Record<KanbanStage, number> = Object.fromEntries(
  STAGE_ORDER.map((s, i) => [s, i])
) as Record<KanbanStage, number>;

type CellState = "done" | "active" | "pending" | "locked";

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
  if (callIdx === stageIdx) return "active";

  // Stage not yet reached — lock artifacts and topics if prev call is incomplete
  if ((stageKey === "artifacts" || stageKey === "topics") && !prevCallDone) {
    return "locked";
  }
  return "pending";
}

type Props = {
  calls: Call[];
};

export default function KanbanBoard({ calls }: Props) {
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
      <div className="flex items-center" style={{ paddingLeft: 148 }}>
        {STAGES.map((s) => (
          <div
            key={s.key}
            className="flex-1 text-center text-[10px] font-bold uppercase tracking-[0.06em] text-[#5e6c84] px-2"
          >
            {s.label}
          </div>
        ))}
      </div>

      {/* ── One row per call ── */}
      {sorted.map((call, idx) => {
        const prevCall     = idx > 0 ? sorted[idx - 1] : null;
        const prevCallDone = prevCall == null || prevCall.kanban_stage === "done";

        return (
          <div key={call.id} className="flex items-stretch">

            {/* Call label */}
            <div
              className="flex-shrink-0 flex flex-col justify-center pr-4"
              style={{ width: 140 }}
            >
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
            </div>

            {/* Stage cells */}
            <div className="flex-1 bg-white border border-[#dfe1e6] rounded-lg flex gap-2 p-2">
              {STAGES.map((s) => {
                const state     = getCellState(call, s.key, prevCallDone);
                const clickable = state === "active" || state === "done";

                const cellStyle: React.CSSProperties = (() => {
                  switch (state) {
                    case "done":   return { background: "#f4f5f7", border: "1px solid #dfe1e6" };
                    case "active": return { background: "#ffffff",  border: "1.5px solid #0052cc" };
                    case "locked": return { background: "#f4f5f7", border: "1px dashed #b3c6e8", opacity: 0.7 };
                    default:       return { background: "#f4f5f7", border: "1px dashed #dfe1e6" };
                  }
                })();

                const statusLabel = (() => {
                  switch (state) {
                    case "done":   return "✓ Done";
                    case "active": return "→ Active";
                    case "locked": return "🔒 Locked";
                    default:       return "—";
                  }
                })();

                const statusColor = (() => {
                  switch (state) {
                    case "done":   return "#36b37e";
                    case "active": return "#0052cc";
                    default:       return "#97a0af";
                  }
                })();

                return (
                  <div
                    key={s.key}
                    onClick={() => {
                      if (state === "active") {
                        router.push(`/projects/${projectId}/calls/${call.id}`);
                      } else if (state === "done") {
                        router.push(
                          `/projects/${projectId}/calls/${call.id}?view=${s.key}`
                        );
                      }
                    }}
                    className="flex-1 rounded-md flex flex-col justify-between p-2.5 min-h-[72px]"
                    style={{ ...cellStyle, cursor: clickable ? "pointer" : "default" }}
                  >
                    <span
                      className="text-[11px] font-semibold"
                      style={{
                        color: state === "active" || state === "done" ? "#172b4d" : "#97a0af",
                      }}
                    >
                      {s.label}
                    </span>
                    <span
                      className="text-[10px] font-semibold"
                      style={{ color: statusColor }}
                    >
                      {statusLabel}
                    </span>
                  </div>
                );
              })}
            </div>

          </div>
        );
      })}

    </div>
  );
}
