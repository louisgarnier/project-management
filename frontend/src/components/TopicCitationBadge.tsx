"use client";

type Props = {
  callId: string;
  callShortName: string;   // e.g. "Call 1"
  citationIndex: number;
};

export default function TopicCitationBadge({ callId, callShortName, citationIndex }: Props) {
  const onClick = () => {
    const el = document.getElementById(`cit-${callId}-${citationIndex}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        fontSize: 10,
        fontWeight: 600,
        padding: "1px 6px",
        borderRadius: 3,
        background: "#deebff",
        color: "#0052cc",
        border: "1px solid #b3d4ff",
        cursor: "pointer",
        fontFamily: "inherit",
      }}
      title="Scroll to citation"
    >
      → {callShortName} cit-{citationIndex}
    </button>
  );
}
