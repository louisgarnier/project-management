import { useMemo } from "react";
import type { Call, KanbanStage } from "@/types";

const STAGE_CONFIG: Record<
  KanbanStage,
  { color: string; dimColor: string; badgeBg: string; badgeText: string; label: string }
> = {
  transcript: {
    color: "#0052cc",
    dimColor: "#0052cc66",
    badgeBg: "#e9f0ff",
    badgeText: "#0052cc",
    label: "Transcript",
  },
  artifacts: {
    color: "#ff8b00",
    dimColor: "#ff8b0066",
    badgeBg: "#fff4e6",
    badgeText: "#974f0c",
    label: "Artifacts",
  },
  topics: {
    color: "#6554c0",
    dimColor: "#6554c066",
    badgeBg: "#f3f0ff",
    badgeText: "#5243aa",
    label: "Topics",
  },
  done: {
    color: "#36b37e",
    dimColor: "#36b37e66",
    badgeBg: "#e3fcef",
    badgeText: "#006644",
    label: "Done",
  },
};

type Props = {
  call: Call;
  isHistorical?: boolean;
  onClick: () => void;
};

export default function CallCard({ call, isHistorical = false, onClick }: Props) {
  const cfg = STAGE_CONFIG[call.kanban_stage];
  const isDone = call.kanban_stage === "done";

  const lineCount = useMemo(
    () =>
      call.transcript
        ? call.transcript.split("\n").filter((l) => l.trim()).length
        : 0,
    [call.transcript]
  );

  return (
    <div
      onClick={onClick}
      className="rounded p-[10px_12px] shadow-[0_1px_3px_rgba(0,0,0,0.12)] cursor-pointer border-l-[3px] hover:shadow-[0_3px_8px_rgba(0,0,0,0.16)] transition-shadow"
      style={{
        backgroundColor: isHistorical ? "#f4f5f7" : "#ffffff",
        borderLeftColor: isHistorical ? cfg.dimColor : cfg.color,
        // Dim active done-column cards (historical done cards already look muted via dimColor border)
        opacity: isDone && !isHistorical ? 0.65 : 1,
      }}
    >
      <div className="flex items-start justify-between gap-1 mb-2">
        <p className="text-[13px] font-medium text-[#172b4d] leading-snug">{call.title}</p>
        {isHistorical && (
          <span className="text-[9px] font-semibold text-[#36b37e] bg-[#e3fcef] px-[5px] py-[1px] rounded flex-shrink-0">
            ✓
          </span>
        )}
      </div>

      {/* Transcript metadata */}
      {call.kanban_stage === "transcript" && !call.transcript && (
        <p className="text-[10px] text-[#97a0af] mb-2">No transcript yet</p>
      )}
      {call.transcript && (
        <p className="text-[10px] text-[#97a0af] mb-2">
          {lineCount} lines
          {call.transcript_source ? ` · ${call.transcript_source}` : ""}
        </p>
      )}

      <div className="flex items-center justify-between">
        <span
          className="text-[10px] font-semibold px-[7px] py-[2px] rounded-[3px] uppercase tracking-[0.04em]"
          style={{ background: cfg.badgeBg, color: cfg.badgeText }}
        >
          {cfg.label}
        </span>
        <span className="text-[10px] text-[#97a0af]">
          {new Date(call.created_at).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
          })}
        </span>
      </div>
    </div>
  );
}
