# Synapse — project memory for Claude Code

This file guides Claude Code sessions doing **application development** on
this repository. It is separate from, and unrelated to, the
`CLAUDE.md` inside `synapse-knowledge/` (a subdirectory of this same repo,
not a separate one — see `docs/ARCHITECTURE.md` §1), which governs headless
knowledge-processing runs (see `docs/ARCHITECTURE.md` §5.3) — do not merge
or confuse the two.

## What this project is

Synapse is a personal, local-first knowledge-management app: raw AI-study
material goes into `synapse-knowledge/` (a content directory inside this
repo), Claude Code (invoked headlessly by the backend) turns it into a
deduplicated global knowledge graph stored as canonical Markdown, and this
app (FastAPI + React) is the interface for triggering that processing and
studying the result via a graph visualization and knowledge viewer/editor.

**Read before doing anything else in this repo:**
1. `docs/REQUIREMENTS.md` — functional/non-functional requirements
2. `docs/ARCHITECTURE.md` — the design and the rationale behind every
   non-obvious decision (content directory placement, Claude Code invocation
   mechanism, no database, graph library choice, engineering standards
   in §14)
3. `docs/PLAN.md` — the phased build order with per-phase acceptance
   criteria

## Current status

Phases 0–6 of `docs/PLAN.md` are complete (scaffolding through the chat
interface). Phase 7 (LiteLLM provider configuration) and Phase 8
(hardening/polish) have not been started — don't start them without
explicit direction.

Beyond the phase plan, the following has since been built and is live in
the app today; `docs/PLAN.md`'s phase write-ups predate all of it and
describe the original build order (including the pre-merge two-repo
architecture), so treat this section, not the phase docs, as the source of
truth for what's actually implemented:
- **Auto-naming**: saving a source no longer takes a manual filename.
  `backend/app/claude_runner/naming.py` asks Claude Code to reason about
  category/filename from the existing `source/` structure; the user can
  optionally give a `topic_hint`, never a filename.
- **Richer ingestion**: the processing prompt (`backend/app/claude_runner/prompts.py`)
  and `synapse-knowledge/CLAUDE.md` now require a broad survey of the
  existing knowledge base and active relationship-creation on every run,
  not just obvious title matches.
- **Auto-triggered processing**: saving a source enqueues its processing
  job in the same request (`backend/app/services/source_service.py`) —
  save and process are one action, not two.
- **Topic tree view**: the Knowledge tab renders a collapsible hierarchy
  derived from `subtopic-of` relationships
  (`frontend/src/components/knowledge/topicTree.ts`), alongside the graph
  visualization.
- **One-repo merge**: `synapse-knowledge/` is now a plain subdirectory of
  this repo, committed to the same git history — it used to be a separate
  sibling repository. See `docs/ARCHITECTURE.md` §1 (revised) for what
  changed and why, including the `git_guard.py` fix this required.

## Hard rules

- The knowledge content directory is `synapse-knowledge/` at this repo's
  root, addressed via `KNOWLEDGE_REPO_PATH` (see `.env.example`, defaults
  to that path). This repo's code treats it as
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
