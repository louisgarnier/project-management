// 8-color pastel palette cycled by call index. Shared between
// TopicEvidenceDrawer (Story 10.4) and ProvenancePill (Story 10.9) so pill
// colors match card colors throughout the UI.
export const CALL_COLORS = [
  "#dfe7ff", // blue
  "#daf5e4", // green
  "#fff7d6", // yellow
  "#ffe0d3", // orange
  "#f0d3ff", // purple
  "#d3f0ff", // cyan
  "#ffd3e6", // pink
  "#e8e8e8", // gray
] as const;

// Text color paired with each CALL_COLORS entry for readable pill text
export const CALL_TEXT_COLORS = [
  "#0747a6", // blue
  "#00623e", // green
  "#926212", // yellow
  "#a14300", // orange
  "#5f2d7a", // purple
  "#006586", // cyan
  "#8c2659", // pink
  "#5e6c84", // gray
] as const;

export function callColor(callIndex: number): { bg: string; text: string } {
  const i = ((callIndex % CALL_COLORS.length) + CALL_COLORS.length) % CALL_COLORS.length;
  return { bg: CALL_COLORS[i], text: CALL_TEXT_COLORS[i] };
}
