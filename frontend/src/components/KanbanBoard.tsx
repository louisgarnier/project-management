import { useRouter, useParams } from "next/navigation";
import type { Call, KanbanStage } from "@/types";
import CallCard from "@/components/CallCard";

const COLUMNS: { key: KanbanStage; label: string }[] = [
  { key: "transcript", label: "Get Transcript" },
  { key: "artifacts", label: "Artifacts" },
  { key: "topics", label: "Topics" },
  { key: "done", label: "Done" },
];

type Props = {
  calls: Call[];
};

export default function KanbanBoard({ calls }: Props) {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const projectId = params.id;

  return (
    <div className="flex gap-3 p-4 overflow-x-auto flex-1">
      {COLUMNS.map((col) => {
        const colCalls = calls.filter((c) => c.kanban_stage === col.key);
        return (
          <div key={col.key} className="w-[230px] flex-shrink-0 flex flex-col">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-bold uppercase tracking-[0.06em] text-[#5e6c84]">
                {col.label}
              </span>
              <span className="bg-[#dfe1e6] text-[#5e6c84] text-[10px] font-semibold rounded-full px-[7px] py-[1px]">
                {colCalls.length}
              </span>
            </div>
            <div className="flex flex-col gap-2 flex-1">
              {colCalls.length === 0 ? (
                <div className="border-2 border-dashed border-[#dfe1e6] rounded p-6 text-center">
                  <p className="text-[10px] text-[#b3bac5]">No calls yet</p>
                </div>
              ) : (
                colCalls.map((call) => (
                  <CallCard
                    key={call.id}
                    call={call}
                    onClick={() =>
                      router.push(`/projects/${projectId}/calls/${call.id}`)
                    }
                  />
                ))
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
