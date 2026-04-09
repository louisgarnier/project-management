const STAGES = [
  { key: "transcript", label: "Transcript", color: "#0052cc" },
  { key: "artifacts", label: "Artifacts", color: "#ff8b00" },
  { key: "topics", label: "Topics", color: "#6554c0" },
  { key: "done", label: "Done", color: "#36b37e" },
];

export default function BoardPage() {
  return (
    <div className="p-6 h-full flex flex-col">
      {/* Page header */}
      <div className="flex items-center justify-between mb-6 flex-shrink-0">
        <h1 className="text-xl font-semibold text-[#172b4d]">Board</h1>
        <button
          disabled
          className="bg-[#0052cc] text-white px-4 py-1.5 rounded text-sm font-medium opacity-50 cursor-not-allowed"
          title="Available in EPIC-3"
        >
          + New Call
        </button>
      </div>

      {/* Kanban columns */}
      <div className="flex gap-3 flex-1 overflow-x-auto">
        {STAGES.map((stage) => (
          <div key={stage.key} className="w-[220px] flex-shrink-0">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-semibold text-[#5e6c84] uppercase tracking-wide">
                {stage.label}
              </span>
              <span className="bg-[#dfe1e6] text-[#5e6c84] text-[10px] rounded-full px-1.5 py-0.5">
                0
              </span>
            </div>
            <div className="border-2 border-dashed border-[#dfe1e6] rounded p-6 text-center">
              <p className="text-[10px] text-[#b3bac5]">No calls yet</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
