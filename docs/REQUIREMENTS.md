# Synapse — Requirements

Status: **approved for planning**, pre-implementation.
This document captures functional and non-functional requirements as clarified
with the product owner (Arnav). See `ARCHITECTURE.md` for how these are
satisfied and `PLAN.md` for the build order.

## 1. Purpose

Synapse is a personal, local-first application for turning raw AI-study
material (mostly ChatGPT/Claude/Gemini conversation exports, plus articles,
PDFs, YouTube transcripts, and personal notes) into a single, deduplicated,
navigable **global knowledge graph**, stored as human-readable Markdown, with
Claude Code as the engine that reads new material and updates the knowledge
base.

It is explicitly **not**:
- A conversational AI tutor (the primary interface is not "chat to learn").
- A RAG/vector-search product.
- A multi-user or hosted product.

## 2. Functional Requirements

### FR1 — Source material management
- FR1.1: User can create/add a raw source file (paste text/Markdown content)
  from the frontend, filed under a category the user chooses.
- FR1.2: User can add binary source material (PDF, image) via upload; the
  backend stores bytes as-is, no parsing/OCR pipeline in scope.
- FR1.3: User may also place files directly on disk under `source/` outside
  the app (the original stated workflow); the app must reflect the current
  state of `source/` without requiring everything to go through the API.
- FR1.4: Raw source material is **never modified or deleted** by any
  automated process (Claude Code processing, graph generation, etc.).

### FR2 — Knowledge processing (Claude Code engine)
- FR2.1: User can trigger processing of a specific source file from the
  frontend.
- FR2.2: Processing must not require an external LLM API key — it uses the
  user's existing Claude Code subscription login.
- FR2.3: Processing reads the target source file and the existing knowledge
  base, then creates or updates Markdown concept files under `knowledge/`.
- FR2.4: Processing must not duplicate a concept that already exists under a
  different name/context — it must find and update the existing concept file
  (matched by title, slug, or alias) rather than create a near-duplicate.
- FR2.5: Processing establishes/updates typed relationships between concepts
  using a fixed, meaningful relationship taxonomy (not arbitrary links).
- FR2.6: The user can see the status of a processing run (queued / running /
  succeeded / failed) and a summary of what changed (files created/updated).
- FR2.7: Processing runs must be auditable — it must be possible to see what
  a given run changed, after the fact.

### FR3 — Global knowledge graph
- FR3.1: There is exactly one graph, spanning the whole knowledge base — no
  per-topic subgraphs.
- FR3.2: The graph is derived from the canonical Markdown, not hand-maintained
  separately.
- FR3.3: The frontend renders the graph as an interactive visualization
  (pan, zoom, select) that scales to hundreds of nodes without becoming
  unusable (search, filNorth, and focus/neighborhood views are required, not
  just "render everything and hope").
- FR3.4: Selecting a node opens that concept's structured knowledge.

### FR4 — Knowledge viewer / editor
- FR4.1: Viewing a concept shows the **generated/synthesized** notes, not the
  raw source conversation.
- FR4.2: The generated notes are rendered Markdown, including navigable
  wiki-style links to other concepts.
- FR4.3: The user can manually edit a concept's generated Markdown from the
  frontend, and the edit is saved back to the canonical file.
- FR4.4: From a concept, the user can see which raw source file(s)
  contributed to it, and open that raw material read-only if desired.
- FR4.5: The user can create/edit raw source material from the frontend.

### FR5 — Chat interface
- FR5.1: The frontend provides a chat interface for asking questions answered
  using the knowledge base as context (not general chit-chat).
- FR5.2: By default, chat uses the same no-API-key Claude Code mechanism as
  processing (read-only — it must not write to the repository).
- FR5.3: If an external LLM provider is configured and selected, chat may use
  that provider instead.

### FR6 — LLM provider configuration
- FR6.1: The system supports configuring one or more external LLM
  providers/models via LiteLLM, for use once credentials are available.
- FR6.2: The frontend lets the user choose/enable which model/engine is
  active for chat.
- FR6.3: Provider credentials are managed only on the backend (env vars /
  local config file); they are never sent to or stored by the browser, and
  the frontend never sees key values — only provider/model names and
  configured/not-configured status.
- FR6.4: The core knowledge-processing workflow (FR2) never depends on FR6
  being configured.

## 3. Non-Functional Requirements

- NFR1 — **Local-first, single-user**: runs entirely on the user's machine,
  backend binds to `127.0.0.1` only, no authentication system.
- NFR2 — **No unnecessary database**: application state lives in the
  filesystem (Markdown + small JSON/YAML files for operational state, e.g.
  job records). No RDBMS/vector DB in the initial architecture.
- NFR3 — **Human-readable, Git-friendly canonical storage**: anyone (or any
  future Claude Code session) can inspect the repository on disk and
  understand the full state of the knowledge base without running the app.
- NFR4 — **Simplicity**: no microservices, no message broker, no distributed
  system. One backend process, one frontend build.
- NFR5 — **Evolvability**: the architecture should not block adding RAG,
  more source types, or more LLM providers later, but must not be built
  around those needs now.
- NFR6 — **Data safety**: automated processes must not be able to destroy
  raw source material or silently corrupt the knowledge base; changes from a
  processing run should be reviewable/revertible.
- NFR7 — **Scale target**: hundreds of concept nodes, tens of thousands of
  words of generated knowledge, source material added a few files at a time
  (not bulk-importing thousands of files at once).

## 4. Primary User Workflows

1. **Ingest**: paste a ChatGPT conversation → save as a source file → trigger
   processing → watch job status → new/updated concepts appear in the graph.
2. **Study/navigate**: open the graph → search or browse to a concept →
   read the synthesized notes → follow a relationship link to a related
   concept → repeat.
3. **Correct/refine**: open a concept's generated notes → edit directly →
   save.
4. **Trace back**: while reading a concept, check which raw conversations it
   came from → open the raw material if needed.
5. **Ask**: use chat to ask a question that the app answers using the
   knowledge base as context.
6. **Configure (later)**: add an API key to the backend config → enable a
   provider in the frontend → use it for chat.

## 5. Explicit Non-Goals (v1)

- Multi-user accounts, auth, sharing.
- RAG / vector search / embeddings.
- OCR or PDF text extraction pipeline (binary files are stored and left for
  Claude Code's own file-reading ability during processing, or for the user
  to read directly).
- Automatic ingestion/watching of arbitrary folders outside `source/`.
- Mobile app / offline sync across devices.
- Real-time collaborative editing.
