# Synapse — Architecture

Companion to `REQUIREMENTS.md` (what) and `PLAN.md` (build order). This
document is the "how and why" — every non-obvious decision below has its
rationale next to it so a future session doesn't have to rediscover it.

## 1. Two repositories, not one

**Decision:** the application code (this repo) and the knowledge content
(source material + generated knowledge) live in **two separate Git
repositories**.

- `Synapse/` (this repo) — backend, frontend, docs. A normal software repo.
- `<KNOWLEDGE_REPO_PATH>/` (default: `~/Personal/Arnav/synapse-knowledge`,
  configurable via `.env`) — the content repo:
  ```
  synapse-knowledge/
    source/          # raw material, append-only
    knowledge/        # canonical generated Markdown
    assets/            # generated diagrams/images referenced from knowledge/
    .synapse/         # app-managed operational state (see §7)
    CLAUDE.md          # instructions for the Claude Code processing engine
  ```

**Why:** the prompt that seeded this project shows `source/` and
`knowledge/` as if they might sit inside the app repo, but mixing personal
study content with application source code in one Git history is a real
cost: every "processed a ChatGPT export" commit pollutes the app's commit
log (and vice versa), `.gitignore` gymnastics are needed to keep app tooling
(`node_modules`, build artifacts) out of a content repo and content out of
CI, and a single `CLAUDE.md` at the app repo root would have to serve two
unrelated purposes (guiding coding sessions vs. guiding knowledge-processing
sessions). Splitting them costs one config value
(`KNOWLEDGE_REPO_PATH`) and buys a clean history for both. **This is a
deviation from a literal reading of the prompt and is flagged as a
recommendation** — if you'd rather keep one repo, it only affects Phase 0
scaffolding and Phase 2's `--add-dir` path.

The knowledge repo is *itself* a Git repo (see §5, "Git as the safety net").

## 2. High-level shape

```
┌─────────────────────────┐        ┌──────────────────────────────┐
│  Frontend (React/Vite)  │ HTTP   │  Backend (FastAPI, one process)│
│  - Graph view            │◄──────►│  - Filesystem service          │
│  - Concept viewer/editor │        │  - Frontmatter/graph builder   │
│  - Source editor         │        │  - Job queue (in-process)      │
│  - Chat panel             │        │  - Claude Code runner (subprocess)│
│  - Settings (LLM engine) │        │  - LiteLLM adapter (optional)  │
└─────────────────────────┘        └───────────────┬────────────────┘
                                                      │ subprocess (claude -p)
                                                      │ reads/writes files
                                                      ▼
                                      ┌───────────────────────────────┐
                                      │  synapse-knowledge/ (Git repo) │
                                      │  source/  knowledge/  assets/  │
                                      └───────────────────────────────┘
```

No database. No message broker. No separate services. One backend process
with an in-process async job queue (§6).

## 3. Filesystem structure (knowledge repo)

```
synapse-knowledge/
  source/
    prompt-engineering/
      chat-001.md
      chat-002.md
    llm-security/
      chat-001.md
    _uploads/                # binary sources (PDFs, images) via upload endpoint
      2026-09-22-attention-paper.pdf
  knowledge/
    prompt-injection.md
    few-shot-prompting.md
    llm-security.md
    ...
  assets/
    prompt-injection-diagram.png
  .synapse/
    jobs/                    # one JSON file per processing job (operational state)
      job_20260922_143012_ab12.json
    config.yaml              # non-secret app config (active engine, provider list)
    logs/
      claude-runner.log
  CLAUDE.md                  # knowledge-processing behavior contract (see §5.3)
  .gitignore                  # ignores .synapse/logs, keeps jobs/ (audit trail)
```

- **Category folders under `source/`** (`prompt-engineering/`,
  `llm-security/`, …) are purely organizational for the human placing files.
  They have **no effect on the knowledge graph structure** — a concept
  extracted from `source/llm-security/chat-001.md` can just as easily relate
  to a concept mostly sourced from `source/prompt-engineering/`. This is what
  "one global graph" requires: the graph must not accidentally fork by
  source folder.
- **`knowledge/` is flat.** One file per concept, named by its slug. No
  nested folders by domain — domain/tag membership is metadata
  (`domains:` frontmatter), not filesystem placement, again so a concept
  belonging to multiple domains doesn't need to "pick a folder."
- **`.synapse/` is operational state, not knowledge.** It's what stands in
  for a database (see §7) — job records, non-secret config. It's part of the
  knowledge repo (not the app repo) because it's specific to *that* content
  repo's processing history.

## 4. Knowledge representation (canonical Markdown)

### 4.1 File = one concept

`knowledge/<slug>.md`, slug = kebab-case ASCII of the canonical title.

```markdown
---
id: prompt-injection
title: Prompt Injection
aliases:
  - Prompt Injection Attack
  - Injection Attack (LLM)
domains: [prompt-engineering, ai-security, llm-security]
status: developing        # stub | developing | stable
created: 2026-09-22
updated: 2026-09-22
sources:
  - source/ai-security/chat-003.md
  - source/prompt-engineering/chat-001.md
relationships:
  - type: subtopic-of
    target: llm-security
  - type: subtopic-of
    target: prompt-engineering
  - type: example-of
    target: few-shot-prompting
    note: Few-shot examples can themselves be an injection vector.
  - type: contrasts-with
    target: jailbreaking
---

# Prompt Injection

<synthesized explanation — definition, why it matters, how it works,
examples — written from what the source material actually said, not a
generic textbook summary>

## Related
- See [[llm-security]] for the broader defensive context.
- Contrast with [[jailbreaking]].
```

- **`relationships:` in frontmatter is the authoritative, typed edge data**
  (has a `type` from the fixed taxonomy, a `target` slug, optional `note`).
  This is what the graph is built from.
- **`[[wiki-links]]` in the prose body** are for human/Obsidian-style
  in-context navigation. Any `[[target]]` found in the body that isn't
  already declared in frontmatter is treated as an implicit `related-to`
  edge (deduplicated against frontmatter edges by concept pair) — so
  writing naturally still contributes to the graph, but the frontmatter
  stays the source of truth for edge *type*.
- **Relationships are stored once, on the source concept of the edge**, not
  mirrored on both files (e.g. `prompt-injection.md` declares
  `subtopic-of → llm-security`; `llm-security.md` does not also declare a
  reverse `has-subtopic → prompt-injection`). The graph builder derives
  inverses at read time. This avoids the two-files-disagree failure mode.

### 4.2 Relationship taxonomy (fixed, small, meaningful)

| type | meaning | inverse (derived, not stored) |
|---|---|---|
| `subtopic-of` | A is a more specific topic within B | `has-subtopic` |
| `prerequisite-of` | Understanding A helps/is needed before B | `depends-on` |
| `example-of` | A is a concrete instance/example of concept B | `has-example` |
| `used-in` | A is applied/used within the context of B | `uses` |
| `contrasts-with` | A and B are often compared/confused; understanding the difference matters | symmetric |
| `related-to` | Meaningful association that doesn't fit the above | symmetric |

Chosen to cover exactly the relationship shapes that show up when studying
AI concepts (hierarchy, dependency ordering, applied examples, comparisons),
and kept deliberately small — a concept file with 15 relationship types
would stop being "meaningful relationships" and become link soup. This list
can grow later if a real, recurring relationship shape doesn't fit, but
starts minimal per the requirement to avoid inventing structure that isn't
needed.

### 4.3 Deduplication contract

This is the crux of "one global graph, no duplicate concepts," and it's
enforced by **instruction to Claude Code**, not by application code (the
application can't itself decide semantic sameness — that's exactly the
reasoning task delegated to Claude Code). The contract lives in the knowledge
repo's `CLAUDE.md` (§5.3) and says, roughly:

1. Before creating a new `knowledge/*.md` file, search existing files (by
   `title`, `aliases`, and slug similarity) for a concept that already
   represents what you're about to create.
2. If a match exists, update that file (merge new information, add/update
   `relationships:`, append to `sources:`) instead of creating a new one.
3. Only create a new file when the concept is genuinely new to the graph.
4. When updating an existing file, preserve what's already there — extend
   and refine, don't wholesale rewrite content that isn't stale/wrong.
5. Never modify anything under `source/`.

## 5. Claude Code as the knowledge-processing engine

### 5.1 Why the CLI (`claude -p`), not the Agent SDK

The `claude-agent-sdk` (Python/TypeScript) is Anthropic's recommended
integration for production backends in general — but it authenticates via
`ANTHROPIC_API_KEY`, not the CLI's OAuth subscription login. Requirement
FR2.2 is explicit: the core processing workflow must not depend on an API
key. So the backend invokes the **`claude` CLI in headless/print mode as a
subprocess**, running as the same OS user that is logged into Claude Code
(`~/.claude/.credentials.json`), which inherits that subscription session
with zero extra configuration. This was confirmed against the installed CLI
(v2.1.278) directly, not assumed.

LiteLLM/API-key-backed providers remain available as a **separate, optional
path** (§6) for chat, decoupled from this mechanism.

### 5.2 Invocation shape

```bash
claude -p "<task prompt, see 5.3>" \
  --restricted \
  --tools "Read,Write,Edit,Glob,Grep" \
  --add-dir "$KNOWLEDGE_REPO_PATH" \
  --permission-mode acceptEdits \
  --permission-prompts none \
  --output-format json \
  --no-session-persistence
```
run with `cwd=$KNOWLEDGE_REPO_PATH`, as a `subprocess.run(..., timeout=...)`
call (async via `asyncio.create_subprocess_exec` in the FastAPI backend).

Flag rationale (each verified against `claude --help`, v2.1.278):
- **`--restricted`**: removes command-execution tools (Bash/PowerShell/REPL)
  and `WebFetch` unless explicitly named in `--tools` (they aren't), and
  confines file tools to the working directory + `--add-dir` paths. This is
  the actual safety boundary — Claude Code physically cannot run shell
  commands or touch files outside the knowledge repo in this mode.
  Deliberately **not** `--bare`: `--bare` additionally skips `CLAUDE.md`
  auto-discovery, and the whole dedup/behavior contract (§4.3) lives in
  `CLAUDE.md` — `--restricted` keeps `CLAUDE.md` loading while still cutting
  out Bash/network.
- **`--tools "Read,Write,Edit,Glob,Grep"`**: explicit allowlist. No Bash, no
  WebFetch/WebSearch, no MCP tools.
- **`--add-dir`**: scopes file access to the knowledge repo only (the app
  repo is never exposed to this invocation).
- **`--permission-mode acceptEdits`** + **`--permission-prompts none`**:
  file edits auto-approve (needed — that's the whole point), and anything
  that would still require a prompt is auto-denied instead of hanging
  forever waiting for a human who isn't there. (Exact behavioral edge cases
  between `acceptEdits`/`dontAsk` should be confirmed with a real spike run
  in Phase 2 before relying on it — see Phase 2 acceptance criteria.)
- **`--output-format json`**: structured result (`result`, `session_id`,
  usage/cost) instead of parsing free text.
- **`--no-session-persistence`**: each processing run is a fresh, isolated
  session — we don't need multi-turn `--resume` for this workflow (one
  source file in, one set of knowledge updates out; see §5.4 for why chat is
  different).

### 5.3 `CLAUDE.md` in the knowledge repo

A checked-in file that is the actual "prompt" governing every processing
run (the per-invocation task prompt just says *which* source file changed;
`CLAUDE.md` is auto-loaded context that says *how* to behave). Contents,
authored in Phase 2:
- The dedup contract (§4.3).
- The frontmatter schema (§4.1) and relationship taxonomy (§4.2), with the
  instruction to use exactly those relationship types.
- "Never write to `source/`."
- Slug/naming conventions.
- A note that `knowledge/` files may contain human edits that must be
  preserved/extended, not overwritten.

This file is the primary lever for improving processing quality over time —
it's edited directly, not templated by the backend.

### 5.4 Git as the safety net and audit trail

The knowledge repo is a Git repository. Around every processing run:

1. Before invoking Claude Code, the backend verifies the working tree is
   clean (or refuses to run — surfaced to the user rather than silently
   stacking uncommitted state).
2. After the run, the backend diffs changed files. **If anything under
   `source/` changed, the run is flagged as failed and those changes are
   reverted** (`git checkout -- source/`) — belt-and-braces on top of the
   `--restricted`/`CLAUDE.md` instruction, since instruction-following isn't
   a hard guarantee.
3. If only `knowledge/`/`assets/` changed, the backend commits them with a
   message identifying the job (e.g.
   `knowledge: process source/llm-security/chat-003.md [job ab12]`).

This directly satisfies NFR6 (data safety / revertibility) and FR2.7
(auditability) for free, using a tool that's already a first-class citizen
of the "Git-friendly" requirement — no bespoke audit log needed.

### 5.5 Concurrency

Although independent `claude -p` invocations can safely run in parallel
against different working directories, **all invocations in this app target
the same knowledge repo**. Running two concurrently risks two Claude Code
processes editing the same `knowledge/*.md` file at once. The backend
therefore runs **one processing job at a time**, via a single-worker queue
(§6) — not because the CLI requires it, but because the shared target
repository does.

## 6. Backend (FastAPI)

Single process, no external services.

```
backend/
  app/
    main.py                 # FastAPI app, CORS (localhost only), route registration
    config.py                # env/.env loading: KNOWLEDGE_REPO_PATH, LLM config paths
    fs/
      paths.py               # path resolution + traversal guards, all confined to repo roots
      source_repo.py         # create/read/list source files (text + binary upload)
      knowledge_repo.py      # read/list/write knowledge files
    knowledge/
      frontmatter.py         # parse/write YAML frontmatter + body
      graph.py                # build nodes/edges from knowledge/*.md -> graph JSON
      wikilinks.py            # extract [[...]] links from body
    claude_runner/
      runner.py               # subprocess wrapper around `claude -p ...` (§5.2)
      prompts.py               # task-prompt templates (ingestion, chat)
      git_guard.py             # clean-tree check, diff, revert/commit (§5.4)
    jobs/
      queue.py                 # in-process asyncio queue, single worker
      store.py                 # job record read/write to .synapse/jobs/*.json
    llm/
      litellm_adapter.py       # optional external-provider chat path (Phase 7)
      settings.py               # provider/model config, never exposes key values
    api/
      sources.py                # /api/sources
      knowledge.py               # /api/knowledge
      graph.py                    # /api/graph
      jobs.py                      # /api/jobs
      chat.py                       # /api/chat
      settings.py                   # /api/settings/llm
  tests/
```

- **No database.** Job state is small, low-volume, and append-mostly — a
  JSON file per job under `.synapse/jobs/` is sufficient, and it's
  inspectable on disk like everything else (NFR3). The job queue itself is
  in-memory (an `asyncio.Queue` with one consumer task); on backend restart,
  any job left "running" in its JSON file is reconciled to `failed`
  (interrupted) on startup — no attempt at true crash-resumability, which
  would be over-engineering for a personal local app.
- **Graph JSON is computed, not stored.** `GET /api/graph` walks
  `knowledge/*.md`, parses frontmatter + wikilinks, and returns
  `{nodes, edges}`. It's recomputed on request with a simple in-memory cache
  invalidated whenever a processing job commits or a knowledge file is
  saved via the editor — cheap at "hundreds of nodes" scale, so no need for
  incremental indexing.
- **Path safety**: every filesystem operation resolves the requested path
  against the relevant repo root and rejects anything that escapes it
  (`..`, symlink traversal, absolute paths). This is the main "security
  boundary" that matters for NFR1 (no auth, but still shouldn't let the
  frontend read/write arbitrary files on the machine).

## 7. Why no database (explicit)

Checked against every piece of state the app needs:

| State | Where it lives |
|---|---|
| Knowledge (concepts, relationships) | `knowledge/*.md` (canonical) |
| Raw material | `source/**` (canonical) |
| Derived graph for the UI | Computed on request from `knowledge/*.md`, cached in memory |
| Processing job history/status | `.synapse/jobs/*.json` |
| Non-secret app config (active chat engine, known providers) | `.synapse/config.yaml` |
| LLM provider credentials | Backend process env vars / `.env` (never written to any repo file) |

Nothing here needs transactions, relational queries, or concurrent-writer
guarantees beyond what the single-worker job queue and Git already provide.
Introducing SQLite/Postgres would add a schema-migration surface and a
second source of truth for zero functional benefit — consistent with the
project's explicit instruction to not add a database "because this is a
conventional web application."

## 8. Graph visualization

**Library: Cytoscape.js** (via `react-cytoscapejs`), with the `cose-bilkent`
or `fcose` layout extension for force-directed layout at hundreds-of-nodes
scale.

Considered and rejected:
- **react-flow**: excellent for hand-authored node/edge diagrams (flow
  builders), but its layout model assumes you position nodes yourself or
  bolt on an external layout engine (`dagre`/`elk`) for anything auto-laid;
  less suited to "arbitrary graph, auto-layout, hundreds of nodes" as the
  primary mode.
  - **Sigma.js** (WebGL, via `graphology`): built for much larger graphs
  (10k+ nodes) and would out-perform Cytoscape at that scale, but has a
  steeper API and thinner React ecosystem. Overkill for "hundreds of nodes"
  and adds complexity the requirement doesn't need yet. Documented here as
  the upgrade path if the graph ever grows past what Cytoscape handles
  smoothly.

Navigation strategy for a dense, hundreds-of-nodes graph (FR3.3):
- **Global view**: full graph, force-directed layout, on load.
- **Search-first navigation**: a search box (fuzzy match on title/aliases)
  is the primary way to jump to a concept in a large graph — not scanning
  visually.
- **Focus/ego view**: selecting a node re-centers and can filter to that
  node's immediate neighborhood (configurable depth, e.g. 1–2 hops) to make
  dense regions legible, with a one-click "back to global view."
- **Filtering**: toggle visibility by `domains:` tag and by `status:`
  (stub/developing/stable), so the graph can be narrowed to a study area
  without that narrowing being a *separate graph* (FR3.1) — it's a view-level
  filter over the one graph, not a different data source.
- **Current-context breadcrumb**: the currently selected concept (and how
  the user navigated to it) stays visible so orientation isn't lost when
  panning/filtering.

## 9. Frontend

```
frontend/
  src/
    routes/            # graph view, concept view, source editor, chat, settings
    components/
      graph/            # Cytoscape wrapper, search, filters, focus view
      knowledge/         # markdown viewer (renders [[wikilinks]] as nav links), editor
      source/             # source list/create/edit
      chat/                 # chat panel
      jobs/                  # processing trigger + status/poll UI
      settings/               # LLM engine selection
    api/                # typed fetch client for backend endpoints
    state/               # minimal client state (selected node, active filters) — no
                          # global store framework needed at this scope; React context
                          # + query-library caching (e.g. TanStack Query) is enough
```

Stack: React + TypeScript + Vite + Tailwind (as specified). Markdown
rendering via `react-markdown` with a custom link renderer that turns
`[[concept]]` into an in-app navigation link (select that node / open its
viewer) rather than a dead link. Data fetching/caching via TanStack Query
(polling job status, invalidating graph query on job completion) rather than
hand-rolled fetch+state — this is the one small library addition beyond the
prescribed stack, justified because job polling + cache invalidation is
exactly what it's for and hand-rolling it is the kind of unnecessary
abstraction the project explicitly wants to avoid building itself.

## 10. Chat interface

Two engines behind one `/api/chat` endpoint:

1. **Default — Claude Code (no key required)**: same subprocess mechanism as
   processing (§5.2), but **read-only**: `--tools "Read,Glob,Grep"` (no
   `Write`/`Edit`), scoped to the knowledge repo via `--add-dir`, so a chat
   question can never mutate the knowledge base. This keeps FR5.1/5.2 true
   without requiring any API key, consistent with the rest of the app.
2. **Optional — configured LiteLLM provider**: once a provider/model is
   configured server-side and selected in the frontend Settings screen, chat
   requests go through `litellm.completion(...)` instead, with relevant
   concept content assembled into the prompt as context (no vector search —
   consistent with the RAG non-goal; context is either the currently-open
   concept, or a small set of concepts matched by simple keyword/frontmatter
   search, not embeddings).

The frontend Settings screen lets the user pick the active engine and model
per FR6.2; the backend `/api/settings/llm` endpoint only ever returns
provider names + `configured: true/false`, never key values (FR6.3).

## 11. Security boundaries summary

- Backend binds to `127.0.0.1` only; no auth layer (NFR1, confirmed).
- Browser never executes shell commands or Claude Code directly — every
  mutation goes through a backend endpoint that itself invokes a
  tightly-scoped subprocess (§5.2).
- Claude Code invocations are `--restricted`, tool-allowlisted, and
  directory-scoped; `source/` is additionally protected by the Git-diff
  guard (§5.4) as defense in depth.
- Chat's Claude Code invocation is read-only at the tool-allowlist level.
- LLM API keys live only in backend-side env/config, are never returned to
  the frontend, and are never written into either Git repo.
- Filesystem API endpoints resolve and validate all paths against the
  configured repo roots.

## 12. Testing strategy

- **Backend (pytest)**: unit tests for path-safety guards, frontmatter
  parse/write round-tripping, graph builder (fixture knowledge repo with a
  handful of concept files → assert expected nodes/edges/inverse relations),
  job store, and the Git guard's revert-on-`source/`-change behavior
  (exercised against a throwaway temp Git repo, not the real knowledge repo).
  The `claude_runner` subprocess wrapper is tested with the subprocess call
  mocked/stubbed — these are unit tests, not integration tests that spend
  real Claude Code usage.
- **A real-invocation smoke test** exists separately (manual, or an opt-in
  pytest marker) that runs one real `claude -p` call against a disposable
  temp knowledge repo, to catch CLI flag/behavior drift across Claude Code
  versions. Not part of the default fast test run.
- **Frontend**: component tests (Vitest + React Testing Library) for the
  markdown viewer's wikilink rendering, the graph filter/search logic, and
  the job-status polling component. No end-to-end browser suite in v1 —
  disproportionate for a single-user local app; manual verification in a
  real browser is the acceptance method for graph interaction quality (feel
  of pan/zoom/layout isn't meaningfully unit-testable anyway).
- **Quality of what Claude Code actually produces** (good dedup, sensible
  relationships) is *not* something automated tests can verify — it's a
  judgment call on real content. Every phase that touches processing quality
  includes a manual acceptance step using real source material, not just
  synthetic fixtures.

## 13. Local development workflow (summary, detailed in `SETUP.md` as phases land)

```
# one-time
claude login                                  # if not already logged in
export KNOWLEDGE_REPO_PATH=~/Personal/Arnav/synapse-knowledge
cd backend && poetry install                  # or pip install -r requirements.txt
cd frontend && npm install

# day to day
cd backend && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev                     # Vite dev server, proxies /api to :8000
```
