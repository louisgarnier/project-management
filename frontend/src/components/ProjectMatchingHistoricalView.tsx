"use client";

// EPIC-20 read-only view for past-stage Project Matching cards.
// Renders the committed group → topic → tasks output via the shared component.
// Pre-EPIC-20 M:N pill layout removed 2026-05-29.

import TaskGroupsReadOnly from "@/components/TaskGroupsReadOnly";

type Props = {
  callId: string;
  projectId: string;  // unused but kept for parent-call signature parity
};

export default function ProjectMatchingHistoricalView({ callId }: Props) {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ padding: "16px 20px 4px", borderBottom: "1px solid #dfe1e6", flexShrink: 0 }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, color: "#172b4d", margin: 0 }}>
          Project Topic Matching
        </h2>
      </div>
      <TaskGroupsReadOnly
        callId={callId}
        bannerText="Read-only — matching decisions were saved"
      />
    </div>
  );
}
