# Synapse — project memory for Claude Code

This file guides Claude Code sessions doing **application development** on
this repository. It is separate from, and unrelated to, the
`CLAUDE.md` inside the sibling `synapse-knowledge/` repository, which
governs headless knowledge-processing runs (see `docs/ARCHITECTURE.md`
§5.3) — do not merge or confuse the two.

## What this project is

Synapse is a personal, local-first knowledge-management app: raw AI-study
material goes into a separate content repository, Claude Code (invoked
headlessly by the backend) turns it into a deduplicated global knowledge
graph stored as canonical Markdown, and this app (FastAPI + React) is the
interface for triggering that processing and studying the result via a
graph visualization and knowledge viewer/editor.

**Read before doing anything else in this repo:**
1. `docs/REQUIREMENTS.md` — functional/non-functional requirements
2. `docs/ARCHITECTURE.md` — the design and the rationale behind every
   non-obvious decision (two-repo split, Claude Code invocation mechanism,
   no database, graph library choice, engineering standards in §14)
3. `docs/PLAN.md` — the phased build order with per-phase acceptance
   criteria

## Current status

Phase 0 (scaffolding) is in progress/complete — see `docs/PLAN.md` for what
that covers and what Phase 1 onward looks like. **Do not implement ahead of
the current phase**; each phase is meant to land as a complete, tested
increment before the next starts.

## Hard rules

- The knowledge content repository lives outside this repo, at
  `KNOWLEDGE_REPO_PATH` (see `.env.example`, default
  `~/synapse-knowledge`). This repo's code treats it as
  external data, always accessed through the path-safety-checked repository
  modules described in `docs/ARCHITECTURE.md` §6/§14.2 — never with ad hoc
  file I/O scattered through routes or components.
- No database. Application state is the filesystem plus small JSON/YAML
  operational files under `synapse-knowledge/.synapse/` — see
  `docs/ARCHITECTURE.md` §7 before proposing to add one.
- Follow `docs/ARCHITECTURE.md` §14 (Engineering Standards) for all backend
  and frontend code: modular, single-responsibility files, no god-files,
  repository/strategy/adapter patterns where the design already implies
  them, no speculative abstraction otherwise.
- The backend binds to `127.0.0.1` only; no auth system (single-user local
  app, see NFR1).
