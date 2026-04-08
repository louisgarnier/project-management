# Call Tracker — Project Description

## Overview

Call Tracker is a solo-use web application designed to manage and process client project calls. It provides a structured, kanban-based workflow to go from raw call recordings to organized project artifacts and a living topic dashboard — all within a single interface.

The app is built on a **Next.js / FastAPI / Supabase** stack.

---

## Core Concept

The app is organized around **Projects**. Each project represents a client engagement or initiative. Inside a project, every client call is tracked as a **card** that moves through a fixed kanban pipeline from raw audio to fully processed and documented output.

Over time, the collection of processed calls builds up a **project-level Topic Dashboard** that tracks key themes and follow-up items across the entire engagement.

---

## Project-Level View

When the app opens, the user sees a list of all active projects. Opening a project shows two main areas:

- **Kanban Board** — all calls for this project, each as a card moving through the pipeline
- **Topic Dashboard** — a living tracker of all key topics surfaced across calls

---

## Kanban Pipeline (Per Call)

Each call card progresses through the following columns:

### 1. Load Call
The user drops an MP3 file for the call. The file is stored and the card is created.

### 2. Convert Call
The user passes the audio through their existing speech-to-text tool (external app, provided separately) and drops the resulting `.txt` transcript file into the app. The transcript is stored and linked to the call card.

### 3. Artifacts
This is the core processing step. It has two sub-phases:

**a) Select Artifacts**
The user selects which artifact types to generate for this call. Default artifact types include:
- High-level call recap
- Detailed call summary
- Next steps
- Action items before next call
- Questions for next call

The user can add, edit, or remove artifact types per call or globally per project. Prompts behind each artifact type are editable.

**b) Generate & Review Artifacts**
All selected artifacts are generated simultaneously via the Claude API. Each artifact displays its own progress status. The user can review and edit each artifact. Once satisfied, they mark it as **Done**. The call card only moves forward once all selected artifacts are marked done.

### 4. Topics
After artifacts are validated, the app processes the transcript to extract or update **key topics** — recurring themes or items that need follow-up across the project.

- On **Call 1**: key topics are extracted fresh from the transcript and artifacts. The user reviews, edits, adds, or removes topics.
- On **Call 2+**: the app checks the new transcript for updates on existing topics and surfaces any new ones. The user validates and edits the topic list.

Each topic carries a status, a latest update, and open follow-up items.

### 5. Done ✓
All artifacts are complete and topics are validated. The call is fully processed. A new call card can be created for the next session.

---

## Topic Dashboard (Project Level)

A dedicated tab at the project level aggregates all topics across all calls into a single view. For each topic it shows:

- When it was first raised (which call)
- Latest status / update (from the most recent call where it appeared)
- Open follow-up items
- History of updates call by call

This gives the user a bird's-eye view of project health and ensures nothing falls through the cracks between calls.

---

## Prompt & Artifact Management

- Default artifact prompts are provided at app launch but are fully editable
- New artifact types can be created at any time
- Prompts can be customized per project if needed
- Topic extraction also uses a configurable prompt

---

## Data Storage

All data is persisted in **Supabase (PostgreSQL)**:

- Projects
- Calls (with MP3 reference and transcript text)
- Artifacts (type, prompt used, generated content, status)
- Topics (per project, with per-call update history)

No authentication is required — this is a solo-use tool.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js |
| Backend / API | FastAPI |
| Database | Supabase (PostgreSQL) |
| AI Processing | Claude API |
| Speech-to-Text | External app (provided separately) |
| File Storage | Supabase Storage |

---

## Key Design Principles

- **Call-centric**: every piece of work is anchored to a specific call
- **Non-destructive**: all artifacts and transcripts are stored and versioned per call
- **Incremental**: the project knowledge base grows naturally call by call
- **Flexible**: prompts and artifact types adapt to how each project evolves
