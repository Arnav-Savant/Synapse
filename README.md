# Synapse

A personal, local-first application for turning raw AI-study material
(ChatGPT/Claude/Gemini conversations, articles, PDFs, YouTube transcripts,
notes) into a single, deduplicated, navigable **global knowledge graph**.

Synapse is not a chatbot that teaches you. It's a knowledge-management
system: you drop raw material in, Claude Code reads it and your existing
knowledge base, and updates a canonical set of human-readable Markdown
concept files with meaningful relationships between them. The app renders
that as a global graph you navigate to study — the graph and the generated
notes are the product, not a conversation.

## Status

**Pre-implementation.** Architecture and phased build plan are complete;
code has not been written yet. See:

- [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) — what the app must do
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how it's built and why
- [`docs/PLAN.md`](docs/PLAN.md) — the phase-by-phase build order

## Core ideas

- **Filesystem is the source of truth.** Raw material lives in `source/`
  (untouched, ever) and generated knowledge lives in `knowledge/` as
  Markdown with frontmatter — both inside `synapse-knowledge/`, a
  subdirectory of this repo (see `ARCHITECTURE.md` §1). No database.
- **One global graph.** Every concept is a single node regardless of how
  many different topics/contexts it shows up in; the graph is derived from
  the canonical Markdown, not maintained separately.
- **Claude Code is the processing engine**, invoked headlessly by the
  backend against your existing paid subscription — no API key required for
  the core ingestion workflow.
- **The app is the study interface.** A graph-based navigator plus a
  cleaned-up knowledge viewer/editor — no dependency on Obsidian or any
  other external tool.

## Stack

- Backend: Python, FastAPI, no database
- Frontend: React, TypeScript, Vite, Tailwind CSS, Cytoscape.js for the
  graph
- Knowledge engine: `claude` CLI (headless/`-p` mode), subprocess-invoked
- Optional external LLMs (later, chat only): LiteLLM

## Getting started

Not yet runnable — see [`docs/PLAN.md`](docs/PLAN.md) Phase 0. Once Phase 0
lands, `SETUP.md` will have real install/run steps and `USAGE.md` will
describe day-to-day use.
