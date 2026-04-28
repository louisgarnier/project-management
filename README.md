# Project Template

## Two scenarios — pick one

### Scenario A — New project from scratch
Clone this entire repo into a new repository. Everything is ready: scaffold, docs, workflow, CLAUDE.md.
```
git clone <this repo> my-new-project
cd my-new-project
./scripts/setup.sh
```
Then start at Step 1: read `docs/project/requirements/1-BRAINSTORM.md`.

### Scenario B — Adding features to an existing project
Copy the `feature-setup/` folder contents into your existing project root. It contains only the docs and workflow files — no scaffold.
```
cp -r feature-setup/. /path/to/your/existing/project/
```
Then fill in `CLAUDE.md` (project name, stack, non-goals) and start at Step 1.

> The global `~/.claude/CLAUDE.md` handles all process and skill rules for both scenarios.

---

> **Rule:** Any file added to `docs/integrations/` must also be added to `feature-setup/docs/integrations/`. Both must always be in sync.

---

This is a **template project** for quickly starting new full-stack applications with a rigorous development workflow.

## Tech Stack

- **Backend**: FastAPI (Python) + [DB per architecture.md]
- **Frontend**: Next.js (TypeScript/React) + TailwindCSS
- **Testing**: Pytest (backend) + Jest (frontend)
- **Workflow**: Epic → Story → Test → Sign-off methodology

---

## 🚀 Quick Start

### 1. Run Setup Script
```bash
./scripts/setup.sh
```
This will:
- Create Python virtual environment + install dependencies
- Install Node.js dependencies
- Set up project directories

### 2. Start Development Servers

This project runs on **fixed ports**: backend `8765`, frontend `3015`. Chosen
to avoid colliding with other apps on common ports (8000/3000).

**One-shot (recommended):** boot backend + frontend in a single terminal.
```bash
python3 scripts/dev.py
```
Streams both processes' output prefixed with `[BACK ]` / `[FRONT]`. Ctrl+C stops both.

**Or run them manually in separate terminals:**

Backend (run from repo root):
```bash
python3 -m uvicorn backend.main:app --reload --port 8765
```

Frontend (reads `BACKEND_URL` from `frontend/.env.local`):
```bash
cd frontend
npm run dev -- --port 3015
```

### 3. Configure Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in the keys you need:

| Variable | Source |
|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/ |
| `GROQ_API_KEY` | https://console.groq.com/ |
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| `OPENROUTER_API_KEY` | https://openrouter.ai/keys — enables per-prompt model selection |

### 4. Verify Setup
- Backend health check: `http://localhost:8000/health`
- Frontend: `http://localhost:3000`

---

## 📁 Project Structure

```
template_project/
├── CLAUDE.md                   # AI behavioral rules (single source of truth)
├── README.md
├── SETUP_CHECKLIST.md          # Setup verification checklist
├── jest.config.js              # Root Jest config
├── pytest.ini                  # Root Pytest config
│
├── backend/
│   ├── api/
│   │   ├── main.py             # FastAPI app entry point
│   │   ├── models.py           # Data models
│   │   └── routes/
│   │       └── example.py
│   ├── database/
│   │   ├── connection.py
│   │   ├── schema.sql
│   │   └── migrations/
│   ├── tests/
│   │   ├── test_api.py
│   │   └── test_database.py
│   └── requirements.txt
│
├── frontend/
│   ├── app/                    # Next.js app router
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── globals.css
│   ├── src/
│   │   ├── api/client.ts
│   │   ├── components/
│   │   └── types/index.ts
│   ├── __tests__/
│   │   └── example.test.tsx
│   ├── next.config.ts
│   ├── package.json
│   └── tsconfig.json
│
├── docs/
│   └── project/
│       ├── requirements/       # Read-only templates (WHAT to build, steps 1-7)
│       ├── config/             # Generated outputs (brainstorm, prd, architecture…)
│       │   └── epics/          # ACTIVE.md, overview.md, epic-X/story-X.Y.md
│       └── testing/
│           └── BLIND_SCENARIOS.md  # Sealed — do not read during development
│
├── workflow/                   # Living operational docs (always active)
│   ├── ADR.md                  # Architecture Decision Records
│   └── ERRORS.md               # Known Errors Registry
│
├── logs/                       # Runtime log output (gitignored)
│
└── scripts/
    ├── setup.sh                # Automated setup
    ├── git_ops.py              # Git command wrapper
    ├── brainstorm.py           # Interactive brainstorm generator
    └── new_project.py          # New project initializer
```

---

## 📖 Documentation Architecture

This template uses a **3-tier documentation system**:

### 1. `docs/project/requirements/` — Instructions (Read-Only)
Sequential files (1-7) that tell you **WHAT to build**:
- `1-BRAINSTORM.md` → Validate idea
- `2-PRD.md` → Requirements source of truth
- `3-ARCHITECTURE.md` → Technical decisions
- `4-LOGGING.md` → Logging setup
- `5-EPICS.md` → Work breakdown (Epics → Stories)
- `6-BUILD.md` → Session-by-session build log
- `7-CODEBASE.md` → Living codebase documentation

**Output:** Each file generates content in `docs/project/config/`

### 2. `docs/project/config/` — Generated Output (Project-Specific)
- `brainstorm.md`, `prd.md`, `architecture.md`, `logging.md`
- `build-log.md`, `codebase.md`
- `epics/` folder: `ACTIVE.md`, `overview.md`, `epic-X/story-X.Y.md`

**This is where ALL project-specific content lives.**

### 3. `workflow/` — Behavioral Rules (Always Active)
- `ADR.md` — Architecture Decision Records (append-only)
- `ERRORS.md` — Known Errors Registry (searchable)

**Updated continuously during development.**

---

## 🔧 Development Workflow

The AI follows this **mandatory sequence** for every code change (defined in `CLAUDE.md`):

1. **Understand requirement** → ask questions if unclear
2. **Propose approach** → get user approval before coding
3. **Implement** → only after approval
4. **Create test script** → executable `.py` file in `backend/tests/`
5. **Propose test** → show what it does, wait for user approval
6. **Run test** → verify it passes, check logs (backend + frontend)
7. **Get user confirmation** → user says "done"
8. **Update MDs** → ONLY now: check [x] tasks, update status

---

## 🧪 Testing

### Backend Tests
```bash
cd backend
pytest
```

### Frontend Tests
```bash
cd frontend
npm test
```

### Blind Test Scenarios
- Located in `docs/project/testing/BLIND_SCENARIOS.md`
- **SEALED during development** — AI cannot read this file
- Run ONLY after development is complete

---

## 🔀 Git Workflow

All git operations use `scripts/git_ops.py` — never craft git commands manually.

```bash
# Check status
python scripts/git_ops.py status

# Commit (stages all + commits)
python scripts/git_ops.py commit "[EPIC-X] feat: description"

# Push
python scripts/git_ops.py push

# View history
python scripts/git_ops.py log
```

See `CLAUDE.md` for commit message conventions.

---

## 🆕 Starting a New Project with This Template

### One-time setup

1. **Clone this repository** and run `./scripts/setup.sh`
2. **Reset the template** for your new project:
   ```bash
   python scripts/new_project.py
   ```
   This clears all `docs/project/config/` and `workflow/` files back to blank templates.
3. **Keep `CLAUDE.md` unchanged** — it's the AI's behavioral contract. Never modify it.

---

### How each stage works

Every stage follows the same pattern:

| Step | Who | What |
|---|---|---|
| **Trigger** | You | Tell the AI which stage to run (see phrases below) |
| **Guide** | AI | Reads the requirements template, asks you questions |
| **Decide** | You | All decisions are yours — the AI never decides for you |
| **Write** | AI | Fills the output file in `docs/project/config/` |
| **Review** | You | Read the output, request changes if needed |
| **Confirm** | You | Say "looks good" — AI marks the stage complete |
| **Handoff** | AI | Summarises what feeds into the next stage |

---

### Stage-by-stage guide

#### Stage 1 — Brainstorm (`1-BRAINSTORM.md`)
**Goal:** Decide if the idea is worth building.

**Trigger phrase:** *"Let's start the brainstorm for [project name]"*

**What happens:**
- AI reads `docs/project/requirements/1-BRAINSTORM.md`
- Walks you through §0–6: freeform dump → one-liner → problem → solution → risks → feasibility → Go/No-Go
- You make the Go/No-Go call — the AI cannot commit on your behalf
- AI writes `docs/project/config/brainstorm.md`

**Alternative:** Run the script yourself instead:
```bash
python scripts/brainstorm.py
```

**Done when:** `brainstorm.md` exists with a **GO** decision.

**Feeds into:** Stage 2 — the PRD reads your one-liner, problem, solution, and assumptions.

---

#### Stage 2 — PRD (`2-PRD.md`)
**Goal:** Lock requirements before any technical decisions.

**Trigger phrase:** *"Let's write the PRD"*

**What happens:**
- AI reads `docs/project/requirements/2-PRD.md` + your `brainstorm.md`
- Works through goals/non-goals, user stories, functional & non-functional requirements
- You approve each section — nothing is locked until you confirm
- AI writes `docs/project/config/prd.md`

**Done when:** `prd.md` status is **Locked**.

**Feeds into:** Stage 3 — architecture reads locked requirements to make tech decisions.

---

#### Stage 3 — Architecture (`3-ARCHITECTURE.md`)
**Goal:** Define the full tech stack and system design. Lock it before building.

**Trigger phrase:** *"Let's do the architecture"*

**What happens:**
- AI reads `docs/project/requirements/3-ARCHITECTURE.md` + locked `prd.md`
- Fills the tech stack table (you choose from options), system diagram, component breakdown, env vars, API design
- AI writes `docs/project/config/architecture.md`

**Done when:** `architecture.md` status is **Locked**. No new packages may be added without updating it.

**Feeds into:** Stage 4 — logging setup is driven by the stack choices made here.

---

#### Stage 4 — Logging (`4-LOGGING.md`)
**Goal:** Set up structured logging across all layers before writing business logic.

**Trigger phrase:** *"Let's set up logging"*

**What happens:**
- AI reads `docs/project/requirements/4-LOGGING.md` + locked `architecture.md`
- Implements backend logger, HTTP middleware, frontend logger, log file structure
- AI writes `docs/project/config/logging.md` and the actual logger code

**Done when:** `logging.md` status is **Locked** and end-to-end logging is tested.

**Feeds into:** Stages 5–7 — all build sessions use the logging conventions defined here.

---

#### Stage 5 — Epics (`5-EPICS.md`)
**Goal:** Break all work into Epics → Stories before touching code.

**Trigger phrase:** *"Let's define the epics"*

**What happens:**
- AI reads `docs/project/requirements/5-EPICS.md` + locked `prd.md` + `architecture.md`
- Proposes epics and stories — you approve, reorder, or cut scope
- AI writes `docs/project/config/epics/overview.md` and one `story-X.Y.md` per story

**Done when:** All epics and stories are defined, prioritised, and approved.

**Feeds into:** Stage 6 — each build session picks up the next story from `epics/ACTIVE.md`.

---

#### Stage 6 — Build (`6-BUILD.md`) — repeating
**Goal:** Implement one story per session, with evidence.

**Trigger phrase:** *"Let's work on [EPIC-X / Story Y.Z]"*

**What happens each session:**
- AI reads `CLAUDE.md` session-start sequence (prd → architecture → build-log → codebase → ACTIVE.md)
- Proposes approach → you approve → AI implements → creates test → you approve → test runs → you confirm done
- AI updates `build-log.md`, `codebase.md`, `workflow/ADR.md` (if decision made), `workflow/ERRORS.md` (if bug hit)

**Done when:** All stories complete, Definition of Done checklist in `build-log.md` is fully checked.

---

#### Stage 7 — Codebase doc (`7-CODEBASE.md`) — ongoing
**Goal:** Keep `codebase.md` current after every story — not a stage you "do once".

Updated automatically by the AI at the end of every build session.

---

#### Final — Blind Test Scenarios
**Trigger phrase:** *"Let's run the blind test scenarios"*

AI is unsealed from `docs/project/testing/BLIND_SCENARIOS.md` only at this point.
Run scenarios cold, record results, fix failures, re-run.

---

### The rules that never change

- All git via `python scripts/git_ops.py` — never raw git commands
- No code before approval — AI proposes, you confirm, then it builds
- No [x] before tests pass — never mark a task done without a passing test
- No new packages without updating `architecture.md` first
- Append to `workflow/ADR.md` for every significant technical decision
- Append to `workflow/ERRORS.md` for every bug encountered and fixed

---

## 📝 Key Principles

- **Single source of truth**: All AI rules live in `CLAUDE.md`
- **Test before marking done**: Never check [x] before tests pass
- **Document decisions**: Use ADR.md for technical choices
- **Log errors**: Use ERRORS.md to prevent recurring bugs
- **Check logs always**: After every code change, verify backend + frontend logs

---

## 🔗 Quick Links

- **AI Rules**: `CLAUDE.md`
- **Master Workflow**: `docs/project/requirements/REQUIREMENTS_WORKFLOW.md`
- **Error Registry**: `workflow/ERRORS.md`
- **Architecture Decisions**: `workflow/ADR.md`




