# UI Shell Design — Call Tracker
**Date:** 2026-04-09
**Status:** Approved

---

## Overview

Replace the minimal placeholder UI with a Jira-like app shell: dark blue top nav, light grey sidebar with two-level navigation (projects + per-project sections), and a kanban board main area.

---

## Layout Structure

### Top Navigation Bar
- Background: `#0052cc` (Jira blue)
- Height: 44px
- Left: app logo mark (white "CT" on blue) + "Call Tracker" wordmark in white
- Right: user avatar initials circle
- No page links in the nav bar — navigation lives in the sidebar

### Sidebar
- Background: `#f4f5f7` (Jira light grey)
- Width: 220px
- Border-right: `#dfe1e6`
- Two sections separated by a divider:

**Section 1 — Projects**
- Label: "PROJECTS" (uppercase, muted)
- Each project: coloured square avatar + project name
- Active project: highlighted with `#0052cc` background + white text
- Bottom item: "+ New project" with dashed border avatar

**Section 2 — Per-project navigation** (shown when a project is selected)
- Label: project name (uppercase, muted)
- Items: Board · Topics · File History
- Active item: light blue background (`#e3f2fd`), blue text
- Icons: 📋 Board · 🗺️ Topics · 📁 File History

### Main Content Area
- Background: `#ffffff`
- Page header: breadcrumb (`Project Name`) + page title + primary action button (`+ New Call`, blue)
- Content: kanban board columns

---

## Kanban Board

Four columns: **Transcript → Artifacts → Topics → Done**

Each column:
- Header: uppercase label + count badge (grey pill)
- Cards: `#f4f5f7` background, `border-radius: 3px`, left-border colour coding:
  - Transcript: `#0052cc` (blue)
  - Artifacts: `#ff8b00` (orange)  
  - Topics: `#6554c0` (purple)
  - Done: `#36b37e` (green)
- Card content: call title, relative timestamp, artifact/topic counts (for Done cards)
- Empty column: dashed border placeholder with muted text

---

## Components to Build

| Component | Path | Notes |
|---|---|---|
| App shell layout | `frontend/app/layout.tsx` | Replace root layout with sidebar + top nav wrapper |
| Top nav | `frontend/src/components/TopNav.tsx` | Static for now (no auth) |
| Sidebar | `frontend/src/components/Sidebar.tsx` | Receives project list + active project/page as props |
| Project list page | `frontend/app/page.tsx` | Redirect to first project or show project picker in sidebar |
| Board page | `frontend/app/projects/[id]/board/page.tsx` | Kanban columns, fetches calls |
| Topics page | `frontend/app/projects/[id]/topics/page.tsx` | Placeholder — built in EPIC-6 |
| File History page | `frontend/app/projects/[id]/history/page.tsx` | Placeholder — built in EPIC-5 |
| Call card | `frontend/src/components/CallCard.tsx` | Reused across board columns |

---

## Navigation Routing

| URL | View |
|---|---|
| `/` | Redirects to `/projects` |
| `/projects` | Project list (sidebar active state: none selected) |
| `/projects/[id]/board` | Kanban board (default project view) |
| `/projects/[id]/topics` | Topics dashboard (placeholder until EPIC-6) |
| `/projects/[id]/history` | File History (placeholder until EPIC-5) |

Clicking a project in the sidebar navigates to `/projects/[id]/board`.

---

## Colour Palette

| Token | Value | Usage |
|---|---|---|
| `brand-blue` | `#0052cc` | Top nav bg, active project, primary buttons, active nav item text |
| `brand-blue-dark` | `#0065ff` | Avatar bg in top nav |
| `sidebar-bg` | `#f4f5f7` | Sidebar background |
| `border` | `#dfe1e6` | Sidebar border, card borders |
| `text-primary` | `#172b4d` | Headings, card titles |
| `text-muted` | `#5e6c84` | Labels, secondary text, counts |
| `active-nav-bg` | `#e3f2fd` | Active sidebar nav item background |
| `card-bg` | `#f4f5f7` | Kanban card background |
| `stage-transcript` | `#0052cc` | Card left border — Transcript |
| `stage-artifacts` | `#ff8b00` | Card left border — Artifacts |
| `stage-topics` | `#6554c0` | Card left border — Topics |
| `stage-done` | `#36b37e` | Card left border — Done |

---

## Scope of Changes

This redesign replaces Story 2.2's output and establishes the shell used by all subsequent frontend stories.

**Replaces:**
- `frontend/app/layout.tsx` (root layout — add shell)
- `frontend/app/page.tsx` (home page — project list view)
- `frontend/app/projects/[id]/page.tsx` (project detail — redirect to board)

**Adds:**
- `frontend/src/components/TopNav.tsx`
- `frontend/src/components/Sidebar.tsx`
- `frontend/src/components/CallCard.tsx`
- `frontend/app/projects/[id]/board/page.tsx`
- `frontend/app/projects/[id]/topics/page.tsx` (placeholder)
- `frontend/app/projects/[id]/history/page.tsx` (placeholder)

---

## Non-Goals
- Authentication / user management
- Mobile / responsive layout
- Dark mode
- Drag-and-drop on kanban (future)
