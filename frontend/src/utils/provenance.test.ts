// Lightweight assertion script — no Jest. Run via `npx tsx` from frontend/.
// If any assertion fails the process exits non-zero.
import { resolveProvenance, type CellHistory } from "./provenance";

function assertEqual<T>(actual: T, expected: T, label: string): void {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) {
    console.error(`FAIL: ${label}\n  expected: ${e}\n  got:      ${a}`);
    process.exit(1);
  }
  console.log(`PASS: ${label}`);
}

// Test 1: item present in earliest call → tagged with that call
const h1: CellHistory[] = [
  { call_id: "c1", follow_up_items: ["a", "b"], decisions: [] },
  { call_id: "c2", follow_up_items: ["a", "b", "c"], decisions: [] },
];
assertEqual(
  resolveProvenance(["a", "b", "c"], h1, "follow_up_items"),
  ["c1", "c1", "c2"],
  "earliest-match ordering",
);

// Test 2: item not present anywhere → null
assertEqual(
  resolveProvenance(["x"], h1, "follow_up_items"),
  [null],
  "missing item returns null",
);

// Test 3: decisions are independent of follow_up_items
const h3: CellHistory[] = [
  { call_id: "c1", follow_up_items: ["share"], decisions: [] },
  { call_id: "c2", follow_up_items: [], decisions: ["share"] },
];
assertEqual(
  resolveProvenance(["share"], h3, "decisions"),
  ["c2"],
  "follow-up and decision sections don't cross-match",
);

// Test 4: empty history returns all nulls
assertEqual(
  resolveProvenance(["anything"], [], "follow_up_items"),
  [null],
  "empty history returns null for every item",
);

// Test 5: same item appears in multiple calls → earliest wins
const h5: CellHistory[] = [
  { call_id: "c1", follow_up_items: ["dup"], decisions: [] },
  { call_id: "c2", follow_up_items: ["dup"], decisions: [] },
  { call_id: "c3", follow_up_items: ["dup"], decisions: [] },
];
assertEqual(
  resolveProvenance(["dup"], h5, "follow_up_items"),
  ["c1"],
  "earliest of multiple matches wins",
);

console.log("\nAll provenance tests passed.");
