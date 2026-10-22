# Synapse

Synapse turns a topic name or a pile of pasted material into a set of
well-structured, densely linked study notes, and writes them into
[Obsidian](https://obsidian.md) vaults on your own machine.

You give it something to learn: a topic you know nothing about, or notes you
already have. Synapse proposes an outline, you approve it, agents research and
write each note, and you review the drafts before anything touches a vault.
Obsidian then does what it is good at: the graph view, search and editing.

Synapse is a personal, single-user, local-first tool. Nothing is hosted, and it
needs no API key: the agents are the `claude` command-line tool running under
your own Claude subscription.

## What it does

- **Two ways in.** Paste material and Synapse splits it into a tree of linked
  notes. Or name a topic and Synapse researches it on the web first.
- **You approve twice.** First the outline (the tree of notes to write), then
  the drafts. Nothing is written to a vault before the second approval.
- **Domains, each with its own vault.** A domain is an area you study, such as
  System Design or DSA. Each has a profile that sets how deep its notes go, what
  is in scope and what tone to use. You define your own.
- **A dense graph, not a pile of files.** New material that overlaps an existing
  note is merged into it, or linked to it. Every note links to its parent, its
  subtopics and related notes.
- **Your edits are safe.** Edit notes in Obsidian whenever you like. Synapse
  never overwrites a file you changed; it merges against the file as it is now.
- **Clean deletes.** Deleting a note removes the links to it, so Obsidian never
  shows a ghost node, and re-attaches the notes that sat beneath it.
- **Survives restarts.** Jobs run as durable workflows. Stop and restart the
  backend mid-run and each job picks up where it was.

## How it fits together

```
Browser (React) ──HTTP──▶ FastAPI backend (127.0.0.1:8000)
                              │ starts workflows, sends decisions
                              ▼
                    Temporal server (Docker) ◀──▶ Temporal worker (inside the backend)
                              │                        │
                              ▼                        ├─ runs agents: `claude -p` subprocesses
                    Postgres (Docker)                  └─ runs deterministic steps: commit, delete, reconcile
                    app data + Temporal's own data
                                                  Vault folders on disk ◀── written only by the commit step
                                                  Obsidian ───────────────▶ reads the same folders
```

The note files in the vaults are the source of truth. Postgres holds drafts,
jobs, settings and an index of the notes that can be rebuilt from the vaults at
any time.

## Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy (async) with Alembic, Temporal
- Frontend: React, TypeScript, Vite, Tailwind CSS, TanStack Query
- Storage: Postgres and plain Markdown files
- Agents: the `claude` CLI in headless mode

## Documentation

| Document | What it covers |
|---|---|
| [`SETUP.md`](SETUP.md) | Installing and running Synapse, and every setting |
| [`USAGE.md`](USAGE.md) | Day-to-day use, screen by screen |
| [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) | What Synapse must do |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | How it works and why it is built this way |
| [`CLAUDE.md`](CLAUDE.md) | Orientation for AI coding sessions in this repository |
