# Story 11.5 — Artifact Type Card + Project Settings

**Epic:** EPIC-11 — Call Topics Extraction Overhaul
**Status:** `done` — 2026-04-22
**Spec:** `docs/project/config/2026-04-22-call-topics-extraction-overhaul-design.md` §4.4.4, §4.6.4
**Plan:** `docs/project/config/2026-04-22-call-topics-extraction-overhaul-plan.md` Tasks 12–13

---

## Goal
Rebuild the `ArtifactTypeCard` as the one place users see the full prompt that will actually run — provider dropdown (6 options), conditional OpenRouter model picker, expandable prompt textarea, "Show runtime context" preview of what the system appends, and a "Reset to default" button. Mirror the provider + model controls on the project settings page for `default_llm` / `default_model`.

## Acceptance Criteria
- [x] `ArtifactTypeCard` provider dropdown shows Inherit / Groq / DeepSeek / Claude / OpenAI / OpenRouter ⭐
- [x] When provider=openrouter, Model dropdown appears populated from `MODEL_RECOMMENDATIONS[type.category]` + a "Custom…" row; custom slug input surfaces a free-text field
- [x] Prompt textarea has ⤢ Expand / ⤡ Collapse toggle (~120px ↔ ~500px)
- [x] "Show runtime context" `<details>` disclosure renders a read-only preview of what the system auto-appends (project context / vocabulary / schema / transcript headers with `{placeholders}`)
- [x] "Reset to default" button — confirm dialog, calls `GET /api/artifact-types/defaults/{category}`, overwrites `prompt` + `llm` + `model` in the draft state
- [x] Project settings page exposes the same provider + model controls for `default_llm` / `default_model`
- [x] `ArtifactSelector` labels show OpenRouter + model slug when artifact type resolves to openrouter
- [x] `tsc --noEmit` + `npm run lint` clean

## Tasks
Covers Plan Task 12 (artifact type card), Task 13 (project settings + ArtifactSelector).
