# Synapse — Architecture

Companion to `REQUIREMENTS.md` (what) and `PLAN.md` (build order). This
document is the "how and why" — every non-obvious decision below has its
rationale next to it so a future session doesn't have to rediscover it.

## 1. One repository — content lives inside the app repo

**Decision (revised):** the knowledge content (source material + generated
knowledge) lives as a plain subdirectory of this repo, committed to the same
Git history as the application code — not in a separate repository.

- `Synapse/` (this repo) — backend, frontend, docs, **and**:
  ```
  synapse-knowledge/
    source/          # raw material, append-only
    knowledge/        # canonical generated Markdown
    assets/            # generated diagrams/images referenced from knowledge/
    .synapse/         # app-managed operational state (see §7)
    CLAUDE.md          # instructions for the Claude Code processing engine
  ```
- `KNOWLEDGE_REPO_PATH` (`.env`, optional) still exists as a config value —
  it defaults to `synapse-knowledge/` inside this repo, computed relative to
  the backend package (`backend/app/core/config.py`), so a fresh clone works
  with no per-machine override. Set it only if you want the content
  somewhere else entirely.

**History:** this project originally split content into a second Git
repository specifically to keep "processed a ChatGPT export" commits out of
the app's own commit log, and vice versa (see git history of this file for
the original rationale). That tradeoff was reversed on explicit request —
one repo is simpler to work with day to day, and content commits mixing
into the app's log is an accepted cost. Two things this reversal changes in
practice:
- `git_guard.py`'s `commit_path`/`finalize` now pathspec-scope every
  `git commit` call (`-- <paths>`) rather than committing whatever the
  index happens to hold — content and app code now share one index, so a
  content commit must never sweep in an unrelated staged app-code change
  (or vice versa).
- `--add-dir` in the Claude Code invocation (§5) now points at a
  subdirectory of the same repo Claude Code (the coding assistant) is also
  editing, not an unrelated filesystem location — the `--restricted`
  tool allowlist and the git safety net (§5) are what keep a
  knowledge-processing run's writes confined to `source/`/`knowledge/`,
  not repo separation.

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
    core/
      config.py               # env/.env loading: KNOWLEDGE_REPO_PATH, LLM config paths
    repositories/
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
    services/
      source_service.py         # orchestrates repositories/claude_runner for source operations
      knowledge_service.py       # orchestrates repositories/knowledge for concept read/write
      graph_service.py            # orchestrates knowledge/graph.py + caching (§6 below)
      job_service.py               # orchestrates jobs/ + claude_runner/ for processing runs
      chat_service.py               # strategy dispatch between claude_runner and llm/ engines
    schemas/
      health.py, sources.py, knowledge.py, graph.py, jobs.py, chat.py, settings.py
      # Pydantic request/response models — the API contract layer
    api/
      health.py                     # /api/health
      sources.py                     # /api/sources
      knowledge.py                    # /api/knowledge
      graph.py                         # /api/graph
      jobs.py                           # /api/jobs
      chat.py                            # /api/chat
      settings.py                        # /api/settings/llm
  tests/
```

Layering, thin-to-thick: **`api/`** (validate via `schemas/`, call a service,
return it) → **`services/`** (business logic, composes everything below) →
**`repositories/` / `knowledge/` / `claude_runner/` / `jobs/` / `llm/`**
(single-purpose modules, no knowledge of HTTP). A route never calls a
repository directly, and a repository never imports FastAPI. `core/`
holds cross-cutting app configuration only.

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
export KNOWLEDGE_REPO_PATH=~/synapse-knowledge
cd backend && poetry install                  # or pip install -r requirements.txt
cd frontend && npm install

# day to day
cd backend && uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev                     # Vite dev server, proxies /api to :8000
```

## 14. Engineering standards

Binding for every phase in `PLAN.md`, not just a preference — these are
checked as part of each phase's acceptance, not left to a final cleanup
pass.

### 14.1 Modularity and file size

- **One responsibility per file/module.** The `backend/app/` layout in §6
  and `frontend/src/` layout in §9 are not just folder suggestions — a file
  under `fs/` does filesystem I/O and nothing else, a file under
  `knowledge/` does parsing/graph logic and nothing else, a route file in
  `api/` validates input and delegates, it doesn't contain business logic
  inline. If a module starts doing two of these things, split it before
  adding more to it, not after.
- **No god-files.** If a file is growing past roughly 200–300 lines or
  accumulating unrelated helper functions, that's a signal to extract a
  module, not a size limit to hit and then ignore. Route files in
  particular should stay thin (request → validation → service call →
  response), with the actual work living in the service modules under
  `fs/`, `knowledge/`, `claude_runner/`, `jobs/`, `llm/`.
- Same principle on the frontend: a component that's rendering markup,
  fetching data, and doing non-trivial computation (graph filtering,
  wikilink parsing) should split that computation into a pure function or
  hook (`state/`/`api/`) that's independently testable — this is already
  assumed by `PLAN.md` Phase 4's test plan (pure functions for
  search/filter/focus-view logic, tested apart from rendering).

### 14.2 Patterns to use deliberately (not decoratively)

- **Repository pattern** for all filesystem access: `repositories/
  source_repo.py` and `repositories/knowledge_repo.py` are the only modules
  that touch `source/`/`knowledge/` on disk. Nothing else — not API routes,
  not services, not the graph builder — reads or writes files directly;
  everything goes through these repositories. This is what makes
  path-safety (§11) and testability (swap in a temp-dir fixture) hold
  everywhere at once instead of being re-implemented per call site.
- **Strategy pattern for chat engines** (Phase 6/7): define one small
  interface (e.g. a `ChatEngine` protocol with a single `respond(message,
  context) -> str` method) implemented by the Claude Code read-only runner
  and, later, the LiteLLM adapter. `services/chat_service.py` depends on
  the interface and picks an implementation based on the active-engine
  setting; the `POST /api/chat` route just calls the service — neither
  layer branches on provider name inline. This is also what keeps Phase 7
  additive: implementing the interface again for a new provider shouldn't
  require touching the route or the service's dispatch logic.
- **Adapter pattern** for LiteLLM (`llm/litellm_adapter.py`): isolates the
  third-party call shape from the rest of the app, consistent with the
  strategy interface above.
- **Dependency injection via FastAPI's `Depends`** for anything
  request-scoped or configuration-derived (repo paths, the active chat
  engine, the job queue handle) — services take their dependencies as
  constructor/function arguments, not by reaching for globals or
  re-reading `.env` deep inside unrelated modules.
- **Pure functions for anything analytical**: frontmatter parsing, graph
  building, wikilink extraction, graph search/filter/focus-view logic —
  all take data in and return data out, with no I/O and no framework
  dependency, so they're trivially unit-testable per §12 and reusable if
  the frontend graph logic ever needs to move (e.g. server-side filtering
  at larger scale).

### 14.3 Mandatory per-change checklist

Every piece of backend code written from this point forward — new or
modified, however small it looks — must satisfy all of the following
before it's considered done. These are checked as part of the change
itself, not left to a final cleanup pass:

- **Exception handling.** Any operation that can fail (I/O, subprocess,
  network, parsing, a third-party call) is handled at the layer that can
  meaningfully react to it — surfaced as a typed domain exception (the
  `*Error` classes already used throughout, e.g. `ClaudeRunnerError`,
  `PathTraversalError`) and mapped to an HTTP response centrally in
  `main.py`. Never silently swallowed, never left to propagate as a raw,
  unhandled traceback to the caller.
- **Class-based modularity where a module owns real state or a cohesive
  set of operations acting on shared internal data** (a connection, a
  resource with a defined lifecycle) — a class, not a loose bag of
  module-level functions passing the same arguments around (e.g.
  `PostgresConnection` in `core/postgres_connection.py`). Plain functions
  remain correct for genuinely stateless, single-purpose logic (parsing,
  pure computation) — this is the same "no abstraction without a reason"
  principle as §14.4, applied to this axis, not overridden by it.
- **Appropriate naming**: a name says what a thing is/does without the
  reader needing to open the file (`PostgresConnection`,
  `seed_default_agent_configs`, `ClaudeRunnerError`) — no abbreviations
  that aren't already established in this codebase, no single-letter
  names outside a tight local scope (a comprehension, a short loop).
- **Logging.** Every module that does meaningful operational work (not a
  pure/parsing function) gets a `logger = logging.getLogger(__name__)` and
  logs at the points that matter: something started, something finished
  (with outcome), something failed, a safety net fired (e.g.
  `git_guard.finalize`'s revert-on-`source/`-change). Configuration is
  centralized in `core/logging_config.py`'s `configure_logging()`, called
  once at process startup in `main.py` — never `print()`, never an ad hoc
  handler set up elsewhere. Match level to severity: `info` for normal
  lifecycle events, `warning` for a recovered/degraded condition, `error`
  or `exception` for a failure that surfaces to the caller.
- **Files live in the folder their responsibility already maps to**, per
  the layout in §6 (`core/` for cross-cutting config/connections, `db/`
  for ORM models/migrations/embedded-graph schema once the storage layer
  lands — see the multi-agent architecture spec). Never a new top-level
  file or a catch-all `utils.py`. If a change doesn't obviously belong in
  an existing module, that's a signal to reconsider the folder
  responsibilities in §6/§14.1 before adding one, not to drop it wherever
  is convenient.

None of this is a new principle — §14.1–14.2 already established
modularity and deliberate pattern use. This section makes explicit that
exception handling and logging are held to the same bar, on every change,
not just for new subsystems.

### 14.4 What this deliberately doesn't mean

Per the project's own stated philosophy (avoid unnecessary abstraction):
this is about separating genuinely distinct responsibilities and reusing an
established pattern where one actually fits (chat engines are a textbook
strategy-pattern case because there will provably be ≥2 implementations
behind one interface by Phase 7) — not about adding interfaces, factories,
or abstraction layers for single-implementation code "for future
flexibility." A module with one obvious way to do it stays a plain
function/class; the patterns above apply where the design doc already
implies more than one implementation or a shared access boundary.
