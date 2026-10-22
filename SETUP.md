# Setup

How to install and run Synapse on one machine. For day-to-day use see
[`USAGE.md`](USAGE.md).

## What you need

- **Python 3.12 or newer** and [Poetry](https://python-poetry.org/)
- **Node.js 22 or newer** and npm
- **Docker** with Docker Compose, for Postgres and Temporal
- **The Claude Code CLI** (`claude`) on your `PATH`, logged in to a paid Claude
  subscription (`claude login`). The agents are `claude` subprocesses that use
  that login, so no API key is needed. The backend must run as the same user
  who is logged in.
- **[Obsidian](https://obsidian.md)**, to read and edit the notes

## One-time setup

1. **Choose where the vaults live.** Make an empty folder outside this
   repository, for example `~/synapse-vaults`. Every domain gets its own
   sub-folder in it, and Synapse never commits it to git.

2. **Create the backend settings file** and set `VAULTS_ROOT` to that folder
   (an absolute path):

   ```bash
   cp .env.example backend/.env
   # then edit backend/.env and set VAULTS_ROOT=/home/you/synapse-vaults
   ```

3. **Install the backend:**

   ```bash
   cd backend
   poetry install
   ```

4. **Install the frontend:**

   ```bash
   cd frontend
   npm install
   ```

## Running it

Start the services first, then the backend, then the frontend.

```bash
# from the repository root: Postgres and Temporal
docker compose up -d
```

```bash
# terminal 1: backend on http://127.0.0.1:8000
cd backend
poetry run python main.py
```

```bash
# terminal 2: frontend on http://localhost:5173
cd frontend
npm run dev
```

Open **http://localhost:5173**.

On every start the backend:

1. checks that `VAULTS_ROOT` is an existing, writable folder (it stops with a
   clear message if not),
2. brings the database up to date (migrations run automatically),
3. creates the three starter domains (System Design, DSA, AI) and their vault
   folders if you have no domains yet,
4. scans each vault so notes you added or edited in Obsidian are picked up,
5. connects to Temporal, starts the worker, and resumes any job that was in
   flight.

### First run with Obsidian

In Obsidian choose **Open folder as vault** and pick a domain's folder, for
example `~/synapse-vaults/system-design`. Do this once per domain. Obsidian
creates its own `.obsidian/` folder inside; Synapse never touches it.

### Quick checks

```bash
curl http://127.0.0.1:8000/api/health   # {"status":"ok"}
```

The Temporal web UI at **http://127.0.0.1:8233** shows every workflow and the
step it is on.

## Settings

All backend settings live in `backend/.env` (template: `.env.example`).

| Variable | Meaning | Default |
|---|---|---|
| `VAULTS_ROOT` | Folder that holds one sub-folder per domain. Must exist and be writable. **Required.** | none |
| `DATABASE_HOST` / `DATABASE_PORT` | Where Postgres is | `localhost` / `5433` |
| `DATABASE_USER` / `DATABASE_PASSWORD` / `DATABASE_NAME` | Postgres credentials | `synapse` / `synapse` / `synapse` |
| `TEMPORAL_ADDRESS` | Temporal server address | `localhost:7233` |
| `TEMPORAL_NAMESPACE` | Temporal namespace | `default` |
| `MAX_CLAUDE_PROCESSES` | How many `claude` subprocesses may run at once. Lower it if you hit subscription rate limits. | `4` |
| `FRONTEND_ORIGIN` | Browser origin the backend accepts (only matters if you bypass the Vite proxy) | `http://localhost:5173` |
| `APP_HOST` / `APP_PORT` | Where the backend listens. It is meant for `127.0.0.1` only. | `127.0.0.1` / `8000` |
| `LOG_LEVEL` | Backend log level | `INFO` |

Which Claude model each agent uses, and each domain's profile, are edited in the
app under **Settings**, not in `.env`.

## Ports and data

| What | Where |
|---|---|
| Frontend | `http://localhost:5173` |
| Backend API | `http://127.0.0.1:8000` |
| Postgres | `127.0.0.1:5433` |
| Temporal | `127.0.0.1:7233` |
| Temporal web UI | `http://127.0.0.1:8233` |

Postgres data lives in the Docker volume `pg-data`, and your notes live in the
vault folders. Stopping with `docker compose down` keeps both.
`docker compose down -v` also deletes the database volume; the notes in the
vaults stay, and **Notes → Check vaults for changes** rebuilds the index from
them.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Backend exits with `VAULTS_ROOT is not set` or `is not an existing directory` | Set `VAULTS_ROOT` in `backend/.env` to an existing, writable absolute path. |
| Backend exits with `cannot reach Temporal` | Run `docker compose up -d` and wait a few seconds for Temporal to finish starting, then start the backend again. |
| Backend exits during migrations | Postgres is not up. Run `docker compose up -d postgres` and check `DATABASE_PORT`. |
| The sidebar says "Backend not reachable" | The backend is not running, or is not on port 8000. |
| Jobs fail at their first step with a `claude` error | `claude` is not on the `PATH` of the user running the backend, or is not logged in. Run `claude` once in a terminal to check. |
| Jobs wait forever in "Queued" | At most two jobs run at a time; the rest wait for a slot. Jobs waiting for your approval do not count. |
