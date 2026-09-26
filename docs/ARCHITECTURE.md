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
- **Superseded by the multi-agent/Postgres+Kùzu migration**: `synapse-knowledge/`
  is no longer where knowledge content lives. `Source`/`Concept`/`Job`
  rows live in Postgres and the concept graph lives in the embedded Kùzu
  DB (§3-ish areas of this doc still describe the pre-migration filesystem
  design below and need a fuller rewrite — tracked as Phase 7 doc work).
  `KNOWLEDGE_REPO_PATH`/`ServerConfig.knowledge_repo_path` has been removed
  entirely; there is no longer a knowledge content directory to configure.

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

**Superseded diagram — this describes the pre-migration filesystem design.**
The real current shape (see §5/§7 for detail):

```
┌─────────────────────────┐        ┌───────────────────────────────────┐
│  Frontend (React/Vite)  │ HTTP   │  Backend (FastAPI, one process)     │
│  - Graph view            │◄──────►│  - Orchestrator (LangGraph)          │
│  - Concept viewer/editor │        │  - Text/Graph/Validation Agent prompts│
│  - Source editor         │        │  - Job queue (in-process)             │
│  - Chat panel             │        │  - ClaudeCodeEngine (subprocess)      │
└─────────────────────────┘        └───────┬───────────────────────┬────┘
                                              │ subprocess (claude -p)  │ SQL
                                              │ + MCP over stdio        ▼
                                              ▼                  ┌──────────┐
                              ┌──────────────────────────┐       │ Postgres │
                              │ MCP server subprocess     │──HTTP─▶ (main    │
                              │ (per-role tool boundary)   │ (graph │ backend)│
                              └──────────────────────────┘  ops)  └──────────┘
                                                                        │
                                                                        ▼
                                                                  ┌──────────┐
                                                                  │  Kùzu    │
                                                                  │ (embedded│
                                                                  │  graph)  │
                                                                  └──────────┘
```

No message broker, no separate graph-DB container — Kùzu is embedded in the
backend process itself. There is no filesystem content directory any more:
`synapse-knowledge/` and `KNOWLEDGE_REPO_PATH` have been fully retired (see
§7 for what actually holds state now, and §14.1 of the top-level `CLAUDE.md`
history for why).

## 3. Filesystem structure (knowledge repo) — RETIRED

**This entire section describes a directory that no longer exists.**
`synapse-knowledge/` (with its `source/`/`knowledge/`/`assets/`/`.synapse/`
subdirectories, the per-concept Markdown files, and the JSON job records)
was deleted outright once the multi-agent migration moved every piece of
this state into Postgres/Kùzu — nothing reads or writes a filesystem content
directory any more. See §7 for where this state actually lives today, and
the multi-agent architecture spec's addendum (§14 there) for how the cutover
happened. The category-folder/flat-file/dedup-contract *ideas* described
below (one global graph, no per-source-folder forking, dedup by searching
existing concepts first) all still hold — they're just enforced by MCP
tools and prompts (`agents/text_agent.py`, `mcp_server/server.py`) against
Postgres/Kùzu now, not by Claude Code editing Markdown files directly.

## 4. Knowledge representation (canonical Markdown) — SUPERSEDED IN PART

**The storage mechanism below (Markdown files with YAML frontmatter) is
retired** — a concept is now a `Concept` row in Postgres
(`id, title, category, body, metadata_, status, job_id` —
`backend/app/db/models.py`) and a relationship is now a `RELATES_TO` edge in
the embedded Kùzu graph (`type, note, justification, confidence, status,
job_id` — `backend/app/db/kuzu_db.py`), not frontmatter. The *ideas* this
section describes carry over directly onto the new storage, though:

- **The relationship taxonomy (§4.2) is unchanged** — the same six types
  (`subtopic-of`, `prerequisite-of`, `example-of`, `used-in`,
  `contrasts-with`, `related-to`) are the real, live taxonomy today,
  defined as `HIERARCHICAL_TYPES`/`SYMMETRIC_TYPES`/
  `DIRECTIONAL_NOT_HIERARCHICAL_TYPES` in `backend/app/repositories/graph_repo.py`.
  A relationship is still stored once on its source concept, not mirrored
  (inverses are still derived at read time, e.g. by `get_graph_neighborhood`).
- **The dedup contract (§4.3) is unchanged in spirit** but is now enforced by
  the Graph Agent's/Text Agent's own MCP tool set and prompts
  (`search_concepts`, `get_concept_metadata`) rather than by Claude Code
  searching Markdown files — see the multi-agent architecture spec §4/§7/§8
  for the real mechanism, including the layered structural-correctness
  defenses (referential integrity, cycle detection, duplicate-edge
  rejection, symmetric-both-sides rejection) that didn't exist in the
  original filesystem-based design at all.
- `[[wikilinks]]` in concept body text are still how the frontend renders
  in-app navigation links (`frontend/src/components/knowledge/wikilinkPreprocess.ts`),
  even though the body itself now comes from a Postgres column, not a file.

### 4.1 File = one concept (historical — see note above)

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

**Rewritten to describe the real, current multi-agent mechanism** (the
single-agent, filesystem-`--add-dir`-scoped invocation this section used to
describe is retired — see the multi-agent architecture spec/plan docs for
the full migration). The underlying "why the CLI, not the Agent SDK" reason
(§5.1) hasn't changed.

### 5.1 Why the CLI (`claude -p`), not the Agent SDK

The `claude-agent-sdk` (Python/TypeScript) is Anthropic's recommended
integration for production backends in general — but it authenticates via
`ANTHROPIC_API_KEY`, not the CLI's OAuth subscription login. Requirement
FR2.2 is explicit: the core processing workflow must not depend on an API
key. So the backend invokes the **`claude` CLI in headless/print mode as a
subprocess**, running as the same OS user that is logged into Claude Code
(`~/.claude/.credentials.json`), which inherits that subscription session
with zero extra configuration.

LiteLLM/API-key-backed providers remain a **separate, scaffolded-but-not-live
path** (`engines/litellm_engine.py`), decoupled from this mechanism — not
wired to a live key yet.

### 5.2 `ClaudeCodeEngine`: one engine, four agent roles

`backend/app/engines/claude_code_engine.py`'s `ClaudeCodeEngine` implements
the `AgentEngine` protocol (`engines/base.py`) and can serve any agent
role — role/model/effort are resolved per-call from the `AgentConfig`
Postgres row (`agent_role, engine, model, effort`), never fixed at
construction time. Each `invoke(EngineInvocation)` call spawns a fresh
`claude -p` subprocess:

```bash
claude -p "<agent's prompt>" \
  --restricted --tools "" \
  --mcp-config <per-invocation temp JSON file> --strict-mcp-config \
  --allowedTools mcp__synapse__<tool1> mcp__synapse__<tool2> ... \
  --model <from AgentConfig> --effort <from AgentConfig> \
  --permission-mode acceptEdits --permission-prompts none \
  --output-format json --no-session-persistence
```

- **`--tools ""`** disables every built-in tool (Read/Write/Edit/Bash/...).
  **`--allowedTools mcp__synapse__<name>`** re-adds only the specific MCP
  tools this agent role is granted — this, not a filesystem `--add-dir`
  scope, is what enforces per-role tool boundaries now, by construction:
  an agent literally cannot call a tool it wasn't given.
- **`--mcp-config`**: a per-invocation temp JSON file
  (`{"mcpServers": {"synapse": {"command": ..., "args": ["--role", <role>,
  "--job-id", <job_id>]}}}`) telling the CLI to spawn
  `app/mcp_server/entrypoint.py` as a stdio MCP server subprocess scoped to
  this one role+job. **`--strict-mcp-config`** must always accompany it so
  no other MCP servers already globally registered on the machine leak in.
- **`--output-format json`**: structured result (`result`, `session_id`,
  `total_cost_usd`, `permission_denials`) instead of parsing free text.
  `EngineResult.result_text` is the `result` field — the agent's prompt
  contract requires this to end with a fenced JSON block
  (`agents/structured_output.py::extract_json_object` parses it tolerantly).
- **`--no-session-persistence`**: each invocation is a fresh, isolated
  session (`--no-session-persistence`) — no multi-turn `--resume`, since
  the Orchestrator's LangGraph state (not CLI session state) is what
  carries context between rounds.

There is no Git-based safety net any more (§5.4 used to describe
`git_guard.py`'s clean-tree-check/revert/commit cycle around the filesystem
knowledge repo) — the transactional boundary is now the Postgres/Kùzu
`pending`→`committed` staging model (§10.2 of the multi-agent spec,
`orchestrator/tools.py::commit_job`/`rollback_job`), described in §7 below.

### 5.3 The MCP server subprocess and the Kùzu access problem

Each `claude -p` invocation's MCP config spawns
`app/mcp_server/entrypoint.py` as its own separate OS process, which
constructs a `SynapseMcpServer(role, job_id)` (`app/mcp_server/server.py`)
and registers only the tools `TOOL_REGISTRY[role]` lists (e.g. Text Agent
gets `read_source, search_concepts, get_concept, create_concept,
update_concept`; Graph Agent gets the graph-mutation tools; Validation
Agent gets read-only tools only — no writes, ever, per its read-only design
contract).

**A real, severe bug was found and fixed here, discovered only during the
first genuine end-to-end run** (every test before that used a stubbed
engine, never a real subprocess): Kùzu is an embedded, single-process-
exclusive database — a second process cannot open the same database file at
all while another process holds it open, not even read-only. The main
backend holds one long-lived Kùzu connection open for its entire life
(`get_kuzu_connection()`), so the MCP server subprocess's own attempt to
open a second handle crashed unconditionally, for every role, before any
tool was even dispatched — the agent saw no tools and could only narrate
intended tool calls as prose.

**Fix**: `app/mcp_server/graph_backend.py`'s `GraphBackend` Protocol has two
implementations — `LocalGraphBackend(kuzu_conn)` (direct delegation to
`graph_repo`, used only by tests that already hold a connection) and
`RemoteGraphBackend(base_url)` (used by every real subprocess — makes
synchronous `httpx.Client` calls to six new internal-only routes,
`app/api/internal_graph.py`'s `/internal/graph/*`, on the main backend
process, which is the one process that legitimately holds the Kùzu file
open). `SynapseMcpServer.__init__` picks between them based on whether an
explicit `kuzu_conn` was passed in — the two construction sites in the
codebase (the real subprocess entrypoint, and test fixtures) make this a
100%-reliable signal, not a heuristic. `RemoteGraphBackend` reconstructs the
exact same dataclasses and exception types from the HTTP response, so no
caller above this boundary can tell local from remote. See the multi-agent
architecture spec's addendum (§14) for the full write-up.

Postgres is unaffected by any of this — it's a real client/server database
over TCP (`asyncpg`), and any number of processes opening independent
connections against one running server is exactly what it's built for.

### 5.4 Concurrency

**One processing job runs at a time**, via a single-worker in-process queue
(`jobs/queue.py`) — the staging model (§7) assumes only one job has
`pending` rows against a given concept/edge at once.

### 5.5 The Orchestrator: a deterministic LangGraph pipeline, not an agentic loop

A source is no longer processed by one fused `claude -p` call. It runs
through `orchestrator/graph.py::build_graph`, a **LangGraph `StateGraph`**
over `OrchestratorState` (`orchestrator/state.py`) with four real agent
roles:

```
START → assess_signals → invoke_text_agent ─┬─(concepts written)─→ invoke_graph_agent ─┐
                                              └─(no concepts)──────────────────────────→ invoke_validation_agent
                                                                                              │
                                              ┌── pass ─────────────────────────────────────→ commit → END
                                              ├── reject, cap/no-progress ──────────────────→ rollback → END
                                              └── reject, retry ────→ invoke_text_agent or invoke_graph_agent (loop back)
```

- **"Model B" — deterministic control flow, narrow LLM judgment.** The
  Orchestrator's own control flow is plain LangGraph node/conditional-edge
  structure, never an open-ended agentic tool-calling loop deciding what to
  do next. Genuine LLM judgment happens only inside the three specialist
  invocations (Text/Graph/Validation Agent), each a single, narrow,
  structured-output-only call.
- **Text Agent** (`agents/text_agent.py`): three-stage decomposition
  (segmentation → overlap-check → synthesis, §7 of the multi-agent spec),
  writes/updates `Concept` rows via its MCP tools.
- **Graph Agent** (`agents/graph_agent.py`): runs only when the Text Agent
  actually wrote/updated a concept this round (`should_run_graph_agent`,
  `orchestrator/tools.py`). Its `justification` field is required to cite
  **topological evidence only** (shared neighbors, cluster/category
  alignment) — never a text quote — because it structurally never reads
  concept body text, a deliberate information asymmetry versus the Text
  Agent.
- **Validation Agent** (`agents/validation_agent.py`): read-only tools only
  (no write tool is ever granted to it — enforced by `TOOL_REGISTRY`, not
  convention). Returns `{verdict: "pass"|"reject", issues: [{category,
  severity, target_id, description}]}` against a closed category taxonomy
  (`TEXT_AGENT_CATEGORIES`/`GRAPH_AGENT_CATEGORIES`,
  `target_agent_for_category` maps each to the specialist responsible).
- **Retry/escalation loop** (`orchestrator/tools.py`): a rejected round with
  real per-round progress re-invokes only the agent(s) responsible for the
  flagged issues, via an additive critique-delta prompt (`text_agent_critique_delta`/
  `graph_agent_critique_delta` on `OrchestratorState`, consumed and cleared
  on each agent's next successful invocation — single-use, not permanently
  reapplied). `has_no_progress` detects the same `(category, target_id)`
  pair recurring from the prior round (an existential check, not a
  set-equality one) and, combined with a hard `MAX_VALIDATION_RETRIES = 3`
  cap, escalates instead of retrying further: rolls back all staged writes
  for the job and marks it `needs_review` — never silently failed, never
  silently committed.
- **Traceability**: every node's invocation is recorded as a `JobRound` row
  (`agent_type, prompt_delta, output_summary, structured_output_json,
  cost_usd`) — the full round-by-round trace of a job, including every
  validation verdict and critique delta, is reconstructable from Postgres
  alone.

## 6. Backend (FastAPI)

Single process, no external services.

```
backend/
  app/
    main.py                 # FastAPI app, CORS (localhost only), route registration
    core/
      config.py               # ServerConfig: env/.env loading (no more KNOWLEDGE_REPO_PATH)
      postgres_connection.py  # PostgresConnection: engine/session singleton
      logging_config.py       # configure_logging(), called once at startup
    db/
      models.py               # Job, JobRound, AgentConfig, Source, Concept (SQLAlchemy)
      kuzu_db.py               # get_kuzu_connection(), Concept/RELATES_TO schema
      seed.py                  # seed_default_agent_configs
    repositories/
      concept_repo.py          # Postgres Concept CRUD, pending/committed staging
      graph_repo.py             # Kùzu relationship CRUD + Layer 1 structural checks
      source_record_repo.py     # Postgres Source CRUD
      job_repo.py, job_round_repo.py, agent_config_repo.py
    agents/
      text_agent.py, graph_agent.py, validation_agent.py   # per-role build_prompt/parse_output
      chat_agent.py, naming_agent.py
      structured_output.py     # shared tolerant JSON-block extraction
    orchestrator/
      graph.py                 # LangGraph StateGraph (§5.5)
      state.py                 # OrchestratorState TypedDict
      tools.py                 # get_source_signals, commit_job/rollback_job, has_no_progress
    engines/
      base.py                  # AgentEngine protocol, EngineInvocation/EngineResult
      claude_code_engine.py     # ClaudeCodeEngine (§5.2)
      litellm_engine.py         # scaffold only, not wired to a live key
    mcp_server/
      entrypoint.py             # subprocess entrypoint, self-locates via __file__
      server.py                 # SynapseMcpServer, AgentRole/TOOL_REGISTRY (§5.3)
      graph_backend.py           # GraphBackend Protocol: LocalGraphBackend/RemoteGraphBackend (§5.3)
    jobs/
      queue.py                 # in-process asyncio queue, single worker
      reconciliation.py         # startup sweep: orphaned "running" jobs -> rollback + "failed"
    services/
      source_service.py, knowledge_service.py, graph_service.py,
      job_service.py, chat_service.py, agent_config_service.py
    schemas/
      health.py, sources.py, knowledge.py, graph.py, jobs.py, chat.py, agent_config.py
      # Pydantic request/response models — the API contract layer
    api/
      health.py                     # /api/health
      sources.py                     # /api/sources
      knowledge.py                    # /api/knowledge
      graph.py                         # /api/graph
      internal_graph.py                 # /internal/graph/* — loopback-only, MCP-subprocess use only (§5.3)
      jobs.py                           # /api/jobs
      chat.py                            # /api/chat
      agent_config.py                     # /api/agent-configs
  tests/
```

Layering, thin-to-thick: **`api/`** (validate via `schemas/`, call a service,
return it) → **`services/`** / **`orchestrator/`** (business logic, composes
everything below) → **`repositories/` / `agents/` / `engines/` /
`mcp_server/` / `jobs/`** (single-purpose modules, no knowledge of HTTP). A
route never calls a repository directly, and a repository never imports
FastAPI. `core/` holds cross-cutting app configuration/connections only.

- **Job state, concepts, and sources live in Postgres** (`db/models.py`) —
  see §7 for the full storage picture; there is no more per-job JSON file
  and no filesystem content directory.
- **Graph data lives in the embedded Kùzu DB**, accessed by the main backend
  process directly and by MCP-subprocess tool calls via the internal HTTP
  API (§5.3) — never both at once from a second process opening the file.

## 7. Storage: Postgres + Kùzu (supersedes the original "why no database" decision)

**This section originally argued against adding a database at all** (kept
below, struck through in spirit, for the historical record — a future
session should not resurrect that reasoning, since the multi-agent
migration's requirements genuinely changed what "no database" would have
cost). Once the pipeline needed relational job/round traceability
(`job_rounds` as a queryable audit trail, spec §5.3), structural graph
queries (cycle detection, neighborhood traversal) faster than hand-rolled
Markdown parsing, and true `pending`/`committed` staging with rollback
across concurrent-ish writers, a database stopped being "unnecessary
infrastructure" and became the right tool. Two databases, not a
general-purpose one plus a document store — confirmed as a deliberate
simplification of the original multi-agent design spec (§9.2 proposed SQL +
NoSQL as separate stores; this was consolidated into Postgres alone with
JSONB columns, since a document store's only job here — "flexible-schema
text + metadata" — Postgres JSONB does natively).

| State | Where it lives |
|---|---|
| Jobs, per-round trace (`agent_type`, prompts, structured output, cost) | Postgres `jobs`/`job_rounds` |
| Agent engine/model/effort config | Postgres `agent_configs` |
| Sources (raw material) | Postgres `sources` |
| Concepts (title/category/body/metadata, staging status) | Postgres `concepts` |
| Concept relationships (typed, directional, with justification/confidence) | Kùzu `RELATES_TO` edges (embedded graph DB) |
| Concept nodes mirrored for graph traversal | Kùzu `Concept` nodes (kept in sync from Postgres via `get_concept_metadata`'s cross-store composition — see `mcp_server/server.py`) |
| LLM provider credentials | Backend process env vars / `.env` (never written to the database) |

**Why Kùzu specifically, and why it's embedded, not a container**: an
embedded property-graph database gives real Cypher-style traversal (cycle
detection via `SHORTEST` path queries, variable-length neighborhood
expansion) without running a second server process — consistent with the
project's local-first, minimal-infrastructure posture. The real cost of
this choice is **single-process exclusivity**: only one OS process may hold
the database file open at a time, at all, even for a second read-only
handle. This is why the MCP server subprocess cannot open its own Kùzu
connection (§5.3) and must instead call back into the main backend over
loopback HTTP — a direct, load-bearing consequence of choosing an embedded
graph DB, not an incidental bug in how the MCP tools were wired.

**`pending`/`committed` staging replaces Git as the transactional
boundary** (§5's old §5.4 described Git commit/revert around filesystem
writes — that mechanism is gone). Every domain-tool write during a job is
tagged `status=pending, job_id=<job>` in both stores; `commit_job()` flips
matching rows to `committed`, `rollback_job()` deletes them
(`orchestrator/tools.py`). There is no real cross-store transaction
spanning Postgres and Kùzu — a mid-function failure between the two
`commit`/`rollback` steps can leave them inconsistent, an accepted,
explicitly-logged limitation (loud `logger.exception` on that path) rather
than a silently-ignored one. A startup reconciliation sweep
(`jobs/reconciliation.py`) rolls back any job still `status=running` when
the backend restarts (interrupted mid-run), so orphaned `pending` rows
never linger silently.

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

## 10. Chat interface — mechanism updated, design intent unchanged

Two engines behind one `/api/chat` endpoint (the `--tools "Read,Glob,Grep"`/
`--add-dir` filesystem-scoping described below is retired — chat now goes
through `agents/chat_agent.py` and `ClaudeCodeEngine` like every other
agent role, with `AgentRole.CHAT`'s `TOOL_REGISTRY` entry granting only
read-only MCP tools, §5.2/§5.3):

1. **Default — Claude Code (no key required)**: same `ClaudeCodeEngine`
   mechanism as processing (§5.2), but **read-only** by tool grant — no
   write tool is ever registered for the `chat` role, so a chat question
   can never mutate the knowledge base. This keeps FR5.1/5.2 true without
   requiring any API key, consistent with the rest of the app.
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
- Claude Code invocations run with `--tools ""` (every built-in tool
  disabled) plus `--allowedTools mcp__synapse__<name>` re-adding only the
  specific MCP tools that role's `TOOL_REGISTRY` entry grants (§5.2/§5.3) —
  an agent cannot call a tool it wasn't given, by construction.
- The Validation Agent's tool grant is read-only, with no write tool ever
  registered for it — the same enforcement mechanism as above, not a
  separate read-only mode.
- The internal graph API (`/internal/graph/*`, §5.3) is loopback-only
  plumbing for the MCP server subprocess, never exposed to or called by the
  frontend — same no-auth/127.0.0.1-only posture as the rest of the app
  (NFR1), not a new trust boundary.
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
  `engines/claude_code_engine.py`'s subprocess wrapper and the orchestrator
  graph are tested with `AgentEngine.invoke` stubbed — these are unit tests,
  not integration tests that spend real Claude Code usage. (This exact gap
  is what let the Kùzu single-process-exclusivity bug, §5.3, ship
  undetected through six phases of otherwise-thorough review — a stubbed
  engine structurally cannot exercise the real MCP subprocess. A genuine
  end-to-end run against the live app, not just the stubbed test suite, is
  now treated as a required step before considering a phase of this
  pipeline done.)
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
docker compose up -d postgres                 # or: docker run ... postgres:16-alpine
cp .env.example backend/.env
cd backend && poetry install
cd frontend && npm install

# day to day
cd backend && python main.py                   # runs Alembic migrations, then uvicorn --reload
cd frontend && npm run dev                     # Vite dev server, proxies /api to :8000
```
No `KNOWLEDGE_REPO_PATH` any more — see §7, there is no filesystem content
directory to point at. See `SETUP.md` for the full current setup flow.

## 14. Engineering standards

Binding for every phase in `PLAN.md`, not just a preference — these are
checked as part of each phase's acceptance, not left to a final cleanup
pass.

### 14.1 Modularity and file size

- **One responsibility per file/module.** The `backend/app/` layout in §6
  and `frontend/src/` layout in §9 are not just folder suggestions — a file
  under `repositories/` does data access and nothing else, a file under
  `agents/` builds prompts/parses one agent's output and nothing else, a
  route file in `api/` validates input and delegates, it doesn't contain
  business logic inline. If a module starts doing two of these things,
  split it before adding more to it, not after.
- **No god-files.** If a file is growing past roughly 200–300 lines or
  accumulating unrelated helper functions, that's a signal to extract a
  module, not a size limit to hit and then ignore. Route files in
  particular should stay thin (request → validation → service call →
  response), with the actual work living in the service modules under
  `repositories/`, `agents/`, `orchestrator/`, `engines/`, `mcp_server/`,
  `jobs/`.
- Same principle on the frontend: a component that's rendering markup,
  fetching data, and doing non-trivial computation (graph filtering,
  wikilink parsing) should split that computation into a pure function or
  hook (`state/`/`api/`) that's independently testable — this is already
  assumed by `PLAN.md` Phase 4's test plan (pure functions for
  search/filter/focus-view logic, tested apart from rendering).

### 14.2 Patterns to use deliberately (not decoratively)

- **Repository pattern** for all data access: `repositories/concept_repo.py`
  (Postgres concepts), `repositories/graph_repo.py` (Kùzu relationships),
  `repositories/source_record_repo.py` (Postgres sources), etc. are the only
  modules that touch their respective store directly. Nothing else — not
  API routes, not services, not the orchestrator — reads or writes to
  Postgres/Kùzu directly; everything goes through these repositories. This
  is what makes testability (swap in a fixture session/connection) hold
  everywhere at once instead of being re-implemented per call site.
- **Strategy pattern, worked example: `GraphBackend`**
  (`mcp_server/graph_backend.py`). One small `Protocol` (the six
  `graph_repo` operations the MCP tools need, minus the `conn` argument),
  two implementations behind it — `LocalGraphBackend` (direct delegation to
  `graph_repo`, when a real connection is already in hand) and
  `RemoteGraphBackend` (an HTTP call to the main backend's internal API,
  when the caller is a separate subprocess that can't hold its own
  connection, §5.3). `SynapseMcpServer` depends on the interface and picks
  an implementation based on how it was constructed; every tool builder
  calls `server._graph_backend.<op>(...)` and cannot tell which
  implementation is behind it. This is the textbook case for the pattern —
  there are provably two implementations behind one interface because of a
  real constraint (Kùzu's single-process exclusivity), not speculative
  future-proofing.
- **`AgentEngine` protocol** (`engines/base.py`): `ClaudeCodeEngine` is the
  only live implementation; `litellm_engine.py` is a scaffold. Same
  reasoning as above — the interface exists because a second implementation
  is a named, concrete future item (LiteLLM provider configuration), not
  invented ahead of need.
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
  `*Error` classes already used throughout, e.g. `ClaudeCodeEngineError`,
  `ConceptNotFoundInGraphError`) and mapped to an HTTP response centrally in
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
  `orchestrator/tools.py::commit_job`/`rollback_job` logging loudly before
  re-raising on the no-real-cross-store-transaction path, §7). Configuration
  is centralized in `core/logging_config.py`'s `configure_logging()`, called
  once at process startup in `main.py` — never `print()`, never an ad hoc
  handler set up elsewhere. Match level to severity: `info` for normal
  lifecycle events, `warning` for a recovered/degraded condition, `error`
  or `exception` for a failure that surfaces to the caller.
- **Files live in the folder their responsibility already maps to**, per
  the layout in §6 (`core/` for cross-cutting config/connections, `db/` for
  ORM models/migrations/embedded-graph schema, `repositories/` for data
  access, `agents/`/`orchestrator/`/`engines/`/`mcp_server/` for the
  multi-agent pipeline). Never a new top-level file or a catch-all
  `utils.py`. If a change doesn't obviously belong in an existing module,
  that's a signal to reconsider the folder responsibilities in §6/§14.1
  before adding one, not to drop it wherever is convenient.

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
