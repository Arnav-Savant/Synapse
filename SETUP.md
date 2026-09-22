# Setup

**Status: Phase 0 (scaffolding) only.** The app runs, but the only real
feature right now is a health check proving the frontend can reach the
backend and see the knowledge repo path. Real functionality (source
ingestion, Claude Code processing, the graph, the knowledge viewer, chat)
lands in Phases 1–8 — see [`docs/PLAN.md`](docs/PLAN.md).

## Prerequisites

(Verified 2026-09-22, Ubuntu 24.04, local machine — versions are what was
tested, not hard minimums beyond what's noted.)

- Python 3.12+ and [Poetry](https://python-poetry.org/)
- Node.js 22+ and npm
- Claude Code CLI, logged into a paid subscription (`claude login` if you
  haven't). Not required to run Phase 0 itself, but required starting
  Phase 2 (knowledge processing) — no `ANTHROPIC_API_KEY` needed for that
  path.

## One-time setup

1. Create the knowledge content repository — a separate git repo from this
   one (see `docs/ARCHITECTURE.md` §1). It defaults to `~/synapse-knowledge`;
   pick any location you want, as long as `KNOWLEDGE_REPO_PATH` (below)
   points at it.
   ```bash
   mkdir -p ~/synapse-knowledge/{source,knowledge,assets,.synapse/jobs,.synapse/logs}
   cd ~/synapse-knowledge && git init
   ```
2. Backend environment file:
   ```bash
   cp .env.example backend/.env
   ```
   Edit `backend/.env` and set `KNOWLEDGE_REPO_PATH` to the directory from
   step 1 (skip this if you used the default `~/synapse-knowledge`).
3. Backend dependencies:
   ```bash
   cd backend
   poetry install
   ```
4. Frontend dependencies:
   ```bash
   cd frontend
   npm install
   ```

## Running it

Two processes, in two terminals.

**Backend** — `poetry install` already created a project-local virtualenv at
`backend/.venv` (nothing to create by hand). Activate it once per terminal,
then just run the script:

```bash
# Terminal 1 — backend, http://127.0.0.1:8000
cd backend
source .venv/bin/activate      # once per terminal session
python main.py                  # equivalent to: uvicorn app.main:app --reload --port 8000
```

(`poetry run python main.py` also works without activating, if you prefer
not to `source` anything.)

```bash
# Terminal 2 — frontend, http://localhost:5173
cd frontend
npm run dev
```

Open **http://localhost:5173** in a browser. The Vite dev server proxies
`/api/*` requests to the backend (configured in `frontend/vite.config.ts`),
so no CORS setup is needed for local dev.

You should see:
```
Synapse
Phase 0 — scaffolding

status            ok
knowledge_repo_path   <your resolved KNOWLEDGE_REPO_PATH, e.g. /home/you/synapse-knowledge>
knowledge_repo_exists true
```

If `knowledge_repo_exists` shows `false`, check `KNOWLEDGE_REPO_PATH` in
`backend/.env` points at a real directory.

### Quick sanity check without a browser

```bash
curl http://127.0.0.1:8000/api/health
```

## Running the backend tests

```bash
cd backend
poetry run pytest
```

## Config reference

`backend/.env` (see `.env.example` for the template):

| Variable | Meaning | Default |
|---|---|---|
| `KNOWLEDGE_REPO_PATH` | Absolute path to the knowledge content repo | `~/synapse-knowledge` |
| `FRONTEND_ORIGIN` | Allowed CORS origin for the backend (only matters if you bypass the Vite proxy) | `http://localhost:5173` |
