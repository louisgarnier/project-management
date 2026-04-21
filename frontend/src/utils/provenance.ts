// Item provenance resolver — given a topic's history of per-call
// topic_updates, identify which call first contributed each current item.
//
// Uses exact-string match only. Items not found in any prior cell's same
// section return null (UI renders a muted "?" pill). Fuzzy matching is
// explicitly out of scope for Story 10.9 (LLM rewordings fall back to "?").

export type CellHistory = {
  call_id: string;
  follow_up_items: string[];
  decisions: string[];
};

export type ProvenanceSection = "follow_up_items" | "decisions";

/**
 * For each item in `currentItems`, return the call_id of the earliest call in
 * `history` whose `section` array contains the exact string (case + whitespace
 * preserved). Returns null for items not found in any call.
 *
 * `history` must be ordered chronologically (oldest first); no sorting is done
 * inside the function.
 */
export function resolveProvenance(
  currentItems: readonly string[],
  history: readonly CellHistory[],
  section: ProvenanceSection,
): (string | null)[] {
  return currentItems.map((item) => {
    for (const cell of history) {
      const arr = cell[section] ?? [];
      if (arr.includes(item)) return cell.call_id;
    }
    return null;
  });
}
