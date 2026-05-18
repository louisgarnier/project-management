"use client";

import { useState } from "react";

type Props = {
  terms: string[];
  editable?: boolean;
  onChange?: (next: string[]) => void;  // required when editable=true
};

export default function KeyTermChips({ terms, editable = false, onChange }: Props) {
  const [draft, setDraft] = useState("");

  const remove = (i: number) => {
    onChange?.(terms.filter((_, idx) => idx !== i));
  };

  const add = () => {
    const v = draft.trim();
    if (!v || terms.includes(v)) {
      setDraft("");
      return;
    }
    onChange?.([...terms, v]);
    setDraft("");
  };

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 3, alignItems: "center" }}>
      {terms.map((t, i) => (
        <span
          key={`${t}-${i}`}
          style={{
            fontSize: 10.5,
            background: "#f4f5f7",
            border: "1px solid #dfe1e6",
            color: "#42526e",
            padding: "2px 8px",
            borderRadius: 10,
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          {t}
          {editable && (
            <button
              type="button"
              onClick={() => remove(i)}
              style={{
                border: "none",
                background: "none",
                cursor: "pointer",
                color: "#97a0af",
                fontSize: 10,
                padding: 0,
                lineHeight: 1,
              }}
              aria-label={`remove ${t}`}
            >
              ×
            </button>
          )}
        </span>
      ))}
      {editable && (
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          onBlur={() => { if (draft.trim()) add(); }}
          placeholder="+ term"
          style={{
            fontSize: 10.5,
            border: "1px dashed #c1c7d0",
            background: "transparent",
            borderRadius: 10,
            padding: "1px 8px",
            width: 90,
            outline: "none",
            fontFamily: "inherit",
            color: "#42526e",
          }}
        />
      )}
    </div>
  );
}
