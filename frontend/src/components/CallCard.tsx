import type { Call, KanbanStage } from "@/types";

const STAGE_CONFIG: Record<
  KanbanStage,
  { color: string; badgeBg: string; badgeText: string; label: string }
> = {
  transcript: {
    color: "#0052cc",
    badgeBg: "#e9f0ff",
    badgeText: "#0052cc",
    label: "Transcript",
  },
  artifacts: {
    color: "#ff8b00",
    badgeBg: "#fff4e6",
    badgeText: "#974f0c",
    label: "Artifacts",
  },
  topics: {
    color: "#6554c0",
    badgeBg: "#f3f0ff",
    badgeText: "#5243aa",
    label: "Topics",
  },
  done: {
    color: "#36b37e",
    badgeBg: "#e3fcef",
    badgeText: "#006644",
    label: "Done",
  },
};

type Props = {
  call: Call;
  onClick: () => void;
};

export default function CallCard({ call, onClick }: Props) {
  const cfg = STAGE_CONFIG[call.kanban_stage];
  const isDone = call.kanban_stage === "done";

  const lineCount = call.transcript
    ? call.transcript.split("\n").filter((l) => l.trim()).length
    : 0;

  return (
    <div
      onClick={onClick}
      className="bg-white rounded p-[10px_12px] shadow-[0_1px_3px_rgba(0,0,0,0.12)] cursor-pointer border-l-[3px] hover:shadow-[0_3px_8px_rgba(0,0,0,0.16)] transition-shadow"
      style={{
        borderLeftColor: cfg.color,
        opacity: isDone ? 0.65 : 1,
      }}
    >
      <p className="text-[13px] font-medium text-[#172b4d] leading-snug mb-2">{call.title}</p>

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
