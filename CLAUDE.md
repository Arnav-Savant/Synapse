# Synapse — project memory for Claude Code

This file guides Claude Code sessions doing **application development** on
this repository.

**Historical note**: earlier revisions of this file described a separate
`CLAUDE.md` inside a `synapse-knowledge/` content directory that governed
headless filesystem-based knowledge-processing runs. That whole mechanism —
the directory, its own `CLAUDE.md`, and the single fused `claude -p` pass
that read it — was retired by the multi-agent architecture migration (see
below) and no longer exists. There is only this one `CLAUDE.md` in the
repo now.

## What this project is

Synapse is a personal, local-first knowledge-management app: raw AI-study
material is submitted as a `Source` (Postgres row), a multi-agent pipeline
(Orchestrator + Text/Graph/Validation Agents, invoked headlessly via
`claude -p`) turns it into a deduplicated global knowledge graph — concepts
in Postgres, relationships in an embedded Kùzu graph DB — and this app
(FastAPI + React) is the interface for triggering that processing and
studying the result via a graph visualization and knowledge viewer/editor.
See `docs/ARCHITECTURE.md` §5/§7 for the real mechanism and storage model.

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
(hardening/polish) of *that* plan have not been started — don't start them
without explicit direction. (Note: `docs/PLAN.md`'s own Phase 7/8 numbering
is unrelated to the multi-agent architecture plan's own Phase 7, below,
which is now done — two different plan documents, two different phase
numbering schemes; see `docs/superpowers/plans/2026-09-24-multi-agent-architecture.md`.)

**The multi-agent architecture migration (all 7 phases + Group E cleanup)
is complete** — this is the single biggest change since the phase plans
above, and is the current source of truth for how the backend actually
works, superseding the filesystem-based mechanism `docs/PLAN.md` was
written against:
- **Multi-agent ingestion pipeline**: a source is processed by a LangGraph
  `StateGraph` Orchestrator (`backend/app/orchestrator/graph.py`) that
  invokes real Text/Graph/Validation Agents (`backend/app/agents/`) as
  scoped `claude -p` subprocess calls through an MCP tool-boundary
  mechanism (`backend/app/mcp_server/`), with a retry/escalation loop on
  Validation Agent rejection (targeted re-invocation, no-progress
  detection, escalation to `needs_review`). See `docs/ARCHITECTURE.md` §5.
- **Storage**: Postgres (`Job`/`JobRound`/`AgentConfig`/`Source`/`Concept`)
  + embedded Kùzu (concept relationships) — no filesystem content directory
  any more (`synapse-knowledge/` and `KNOWLEDGE_REPO_PATH` are both fully
  retired). See `docs/ARCHITECTURE.md` §7.
- **A real, severe bug was found and fixed post-implementation**: Kùzu's
  single-process exclusivity meant the MCP server subprocess crashed on
  every real agent invocation until `mcp_server/graph_backend.py`'s
  `GraphBackend` (`LocalGraphBackend`/`RemoteGraphBackend`) + an internal
  loopback HTTP API (`api/internal_graph.py`) fixed it — this was only
  caught by an actual end-to-end run, not the (extensive) stubbed-engine
  test suite. See `docs/ARCHITECTURE.md` §5.3 and the multi-agent spec's
  §14 addendum for the full write-up; this is required reading before
  touching `mcp_server/` or Kùzu access from any new code path.
- **Auto-naming**: saving a source no longer takes a manual filename.
  `backend/app/agents/naming_agent.py` asks Claude Code to reason about
  category from the existing concept categories in Postgres; the user can
  optionally give a `topic_hint`, never a filename.
- **Auto-triggered processing**: saving a source enqueues its processing
  job in the same request (`backend/app/services/source_service.py`) —
  save and process are one action, not two.
- **Topic tree view**: the Knowledge tab renders a collapsible hierarchy
  derived from `subtopic-of` relationships
  (`frontend/src/components/knowledge/topicTree.ts`), alongside the graph
  visualization.
## Hard rules

- The multi-agent architecture migration moved all application state off
  the filesystem. `synapse-knowledge/` no longer exists and
  `KNOWLEDGE_REPO_PATH`/`ServerConfig.knowledge_repo_path` have been removed
  entirely — there is no knowledge content directory to configure.
  Sources/concepts/jobs live in Postgres (`backend/app/db/models.py`,
  accessed only through `backend/app/repositories/`), and the concept graph
  lives in the embedded Kùzu DB (`backend/app/db/kuzu_db.py`), accessed
  directly only by the main backend process — never by a second process
  (see `docs/ARCHITECTURE.md` §5.3's Kùzu single-process-exclusivity
  write-up before adding any new code path that touches the graph DB).
  `docs/ARCHITECTURE.md` has been updated to reflect this (Phase 7 of the
  multi-agent plan, done).
- Follow `docs/ARCHITECTURE.md` §14 (Engineering Standards) for all backend
  and frontend code: modular, single-responsibility files, no god-files,
  repository/strategy/adapter patterns where the design already implies
  them, no speculative abstraction otherwise.
- The backend binds to `127.0.0.1` only; no auth system (single-user local
  app, see NFR1).
