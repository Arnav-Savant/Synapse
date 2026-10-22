# Synapse: project memory for Claude Code

Orientation for AI coding sessions in this repository.

## What this is

Synapse is a personal, single-user, local-first tool that turns a topic name or pasted
material into linked study notes and writes them into Obsidian vaults, one vault per
domain. The owner approves an outline and then the drafts; nothing reaches a vault before
that. A FastAPI backend and a Temporal worker (inside the backend process) run each job as a
durable workflow; agents are `claude -p` subprocesses; Postgres holds drafts, jobs, settings
and a rebuildable index of the notes; the notes on disk are the source of truth. A React app
is the interface.

## Read before changing anything

1. [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md): what Synapse must do
2. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): how it works, including the engineering standards in §17
3. [`SETUP.md`](SETUP.md) and [`USAGE.md`](USAGE.md): running and using it

## Where things are

- `backend/app/api/` thin routes; `services/` business logic; `repositories/` the only code
  that touches tables; `vault/` a pure library for note files; `agents/` one module per agent
  role; `engines/` the `claude -p` wrapper; `workflows/` Temporal workflows, activities and worker;
  `schemas/` pydantic models; `core/` config, logging and the database connection; `db/` models
  and first-run seeding.
- `frontend/src/` has `api/`, `design/` (tokens and primitives), `shell/`, and one folder per
  screen under `features/`.
- `backend/alembic/versions/` holds migrations; they run automatically at startup.

## Hard rules

- **Agents never write files.** Only deterministic code writes to a vault, and every path goes
  through `vault/paths.py::resolve_in_vault`.
- **Never overwrite a note the owner may have edited.** Writes to existing notes are merges
  against the file on disk, guarded by its hash.
- **No git from the application.** Vault contents and `VAULTS_ROOT` are never committed.
- **Workflow code is deterministic.** Anything with I/O or randomness is an activity, and every
  activity must be safe to re-run.
- **The backend binds to `127.0.0.1` only and has no authentication.**
- **Web content an agent reads is untrusted data.** Only the planner, researcher and reference
  finder have web tools; no agent has file tools.
- **Layering:** routes call services; services call repositories, agents and the vault library;
  the vault library depends on nothing else in the app. Do not reach across layers.
- **Errors and logs:** typed exceptions mapped to HTTP statuses in `app/main.py`; no bare `except`;
  one readable log sentence per real event, never note bodies, prompts or secrets (ARCHITECTURE §14).
- **Keep modules small and single-purpose.** No catch-all `utils`, no speculative abstraction.

## Commands

```bash
docker compose up -d                  # Postgres and Temporal (repository root)
cd backend && poetry run python main.py   # backend on 127.0.0.1:8000
cd frontend && npm run dev            # frontend on localhost:5173
cd frontend && npm run build && npm run lint
```

Required setting: `VAULTS_ROOT` in `backend/.env` (see `.env.example`).

## Working here

- There is no automated test suite. Verify a change by running it (ARCHITECTURE §18), and for
  anything with a failure mode, provoke one and check it ends in a clean error and a log line.
- Calls to agents cost money: use a small topic and a trimmed outline when testing.
- Commit only when the owner asks.
