# Synapse Multi-Agent Architecture — Design

Status: draft, pending author review
Date: 2026-09-24
Supersedes (for the areas it covers): `docs/ARCHITECTURE.md` §5 (Claude Code
invocation / git-based safety net), §7 (no-database storage model), and the
single-invocation ingestion pipeline described in §5.3–§5.5. Does not
change §1 (content directory), §6/§14.2 repository pattern intent (the
*principle* survives; its filesystem implementation does not), or NFR1
(local-only, no auth).

## 1. Objective

Evolve Synapse's knowledge-processing pipeline from a single fused
`claude -p` invocation into a genuine multi-agent system, and use this
project as a deliberate vehicle for learning and solving real multi-agent
architecture problems — not just decomposing one prompt into several
prompts called in a fixed sequence.

The guiding test applied throughout this design: an agent, or a loop, or a
branch in control flow, only belongs in this architecture if it depends on
**actual reasoning whose outcome isn't known in advance** — either because
two agents hold genuinely different information and can disagree, or
because a decision (retry, escalate, fan out, skip a stage) depends on a
judgment call, not a fixed script. Anything that's actually deterministic
is a tool, not an agent, per the project's own stated principle.

## 2. Current state (baseline being replaced)

As of the last full read of the codebase:

- **One `claude -p` invocation per saved source file** does the entire
  ingestion job: concept identification, dedup/matching against existing
  knowledge, markdown writing, relationship authoring, and a self-driven
  "did I miss relationships" review — all fused into one prompt governed by
  `synapse-knowledge/CLAUDE.md`. No separate validation pass exists.
- The knowledge graph is **not persisted** — it's derived at read time from
  markdown frontmatter (`relationships:`) plus body wikilinks
  (`backend/app/knowledge/graph.py`), cached in memory, invalidated on
  writes.
- **No database anywhere** — filesystem plus small JSON job records under
  `.synapse/`; `docs/ARCHITECTURE.md` §7 explicitly rejected a database for
  this single-user, low-volume app.
- Storage access already goes through a repository layer
  (`source_repo.py`, `knowledge_repo.py`) — nothing else touches disk
  directly.
- Git is the current safety net: `git_guard.py` verifies a clean tree
  before a run, and after a run reverts anything touched under `source/`
  while committing `knowledge/`/`assets/` changes — this is what makes a
  bad or partial write recoverable today.
- Only one processing job runs at a time (single-worker queue) — a
  shared-repo/shared-store constraint, not a CLI limitation.
- Two other existing one-call LLM invocations sit alongside ingestion: a
  read-only chat engine (`chat_engine.py`, implements a `ChatEngine`
  Strategy interface per §14.2) and a read-only source-naming/filing call
  (`naming.py`).
- A known, observed bug: the ingestion prompt instructs "don't declare a
  symmetric relationship on both sides," and a real run has been observed
  to violate this (`graph.py` code comment) — caught defensively by dedup
  logic at graph-build time, not prevented.

## 3. Goals and non-goals

**Goals of this design:**
- Split ingestion into agents with genuinely distinct responsibilities and
  genuinely distinct information, so disagreement between them is possible.
- Make control flow (which agents run, in what order, how many times)
  depend on real judgment calls (triviality/ambiguity assessment, a
  validation critique loop), not a fixed pipeline.
- Materially reduce the two concrete failure modes called out during
  design: hallucinated/wrong graph edges, and topic
  over-fragmentation/overlap during concept decomposition.
- Move persistence off the filesystem onto free, Docker-hostable databases,
  with a graph DB as the graph's actual storage (not a derived view).
- Make each agent's model/provider/effort independently configurable, with
  Claude Code CLI (subscription-based, no API key) as today's only live
  path and LiteLLM as a per-agent opt-in for later.

**Explicit non-goals (deferred to future, separate design work):**
- UI/dashboard visual design (styling, layout, the traceability dashboard's
  presentation) — parked; this doc only specifies the data the UI will
  read and the config data it will write.
- LiteLLM provider-management UX (the settings-screen experience for
  adding providers) — the underlying mechanism is in scope, the UI is not.
- A Consolidation/Curator Agent (periodic, corpus-wide audit and
  restructuring) — noted as a natural future extension of the Validation
  Agent's critique pattern, not designed here.
- A Study/Quiz Agent (adaptive review, spaced repetition) — noted as a
  future net-new feature, not designed here.
- Concurrent/parallel job execution (e.g., fanning out multiple source
  files at once) — the single-worker constraint is preserved unchanged.
  Relaxing it would reopen the transactional-consistency design in §8 and
  is explicitly flagged there as a tripwire, not solved here.
- A separate Context/Retrieval Agent — data retrieval stays deterministic,
  performed via the tool APIs defined in §6, per the project owner's
  explicit instruction.

## 4. Agent roster

Four agents participate in ingestion. Two pre-existing standalone
invocations (Naming, Chat) are unchanged in responsibility but are folded
into the same engine/config framework (§9).

### 4.1 Orchestrator
Single agent, not split into a separate Planner/Coordinator (a split was
considered and rejected — see §5.4). Responsible for:
- Assessing incoming work (via a cheap, deterministic signal, not a full
  content read — see §5.1) and forming an initial, provisional execution
  plan.
- Revising that plan once the Text Agent's real output is available.
- Invoking each specialist agent via `invoke_agent`.
- Running the validation retry loop: interpreting the Validation Agent's
  structured critique, constructing additive follow-up prompts, deciding
  when to stop (pass, retry-cap, or no-progress).
- Committing or rolling back the job's staged writes (§8).
- Does **not** perform concept identification, relationship reasoning, or
  validation itself — those stay with the specialists.

### 4.2 Text / Knowledge Agent
Understands raw source material, decides how it decomposes into one or
more concept units, decides new-vs-existing (dedup) per unit, and writes
concept content. Full decomposition mechanics in §7.

### 4.3 Graph Agent
Reasons about graph structure only. Deliberately does **not** get read
access to full concept body content (§6.2) — it reasons from graph
topology (existing edges, neighborhood density, centrality) rather than
from text, which is what makes genuine disagreement with the Text Agent
possible (e.g., Text Agent says "new concept," Graph Agent's topology view
says "this looks structurally identical to an existing hub node").

### 4.4 Validation Agent
Read-only across both concept content and graph structure (needs to check
consistency between the two). Never writes — its only output is a
structured critique (§5.2). Tuned to favor precision over recall: a
hallucinated connection actively misleads later study; a missed connection
self-heals the next time related material is ingested, so rejecting on
doubt is the right default.

### 4.5 Naming and Chat (pre-existing, unchanged responsibility)
Naming (source filing/category suggestion) and Chat (read-only Q&A over
the knowledge base) keep their current scope. They're included in the
per-agent engine/model/effort config (§9) for consistency, since there's
no reason to force them onto the same model as the four agents above.

## 5. Control flow: genuine non-determinism

Two decision points were deliberately designed to depend on runtime
judgment rather than a fixed sequence — without these, the four agents
would just be functions called in a hardcoded order.

### 5.1 Dynamic orchestration (plan formed, then revised)
1. Orchestrator calls a deterministic tool, `get_source_signals(source_id)`
   — content length, any user-supplied `topic_hint`, and a cheap
   string/title-similarity score against existing concept titles. No LLM
   call; this is plain lookup logic, same category of operation as
   `search_concepts`.
2. From that signal alone, Orchestrator forms a **provisional** plan: Text
   Agent always runs (something has to actually read the material); Graph
   Agent is tentatively included or excluded.
3. Once Text Agent's real, structured output is available (concept count,
   confidence, scope), Orchestrator **revises** the plan: decides whether
   Graph Agent actually runs, and whether the source's scope warrants
   fanning out (see §7, Stage A/B) — with real information, not a proxy.

This intentionally avoids giving the Orchestrator its own full-content read
tool: that would duplicate the Text Agent's real read (extra LLM cost and
latency) for a judgment that's answerable more cheaply, and it keeps the
Orchestrator's own reasoning step small and fast rather than a second
heavyweight pass.

### 5.2 Validation-driven rework loop
1. Orchestrator invokes the planned specialists.
2. Orchestrator invokes Validation Agent, which returns a structured
   critique: `{verdict: pass|reject, issues: [{category, severity,
   target_id, description}]}`.
3. **Pass** → proceed to commit (§8).
4. **Reject** → Orchestrator compares this round's critique to the prior
   round's. If the same issue (same category and target) was flagged last
   round too, that's a **no-progress signal** — stop immediately and
   escalate, rather than spend remaining retries on something the agent
   has already shown it can't fix.
5. If the critique is new/different, Orchestrator builds an **additive**
   follow-up prompt: the fixed base contract (per-agent instructions,
   unchanged) plus this round's specific critique appended as a delta —
   never a full prompt rewrite, to avoid drift or accumulated
   contradictions across rounds. Re-invokes only the agent responsible for
   the flagged issue (targeted rework, not a full pipeline re-run).
6. Loop 2–5 up to a hard retry cap, regardless of the no-progress check.
7. Terminates via: pass → commit; cap or no-progress → rollback all staged
   writes for this job (§8) and mark the job `needs_review` (not silently
   failed, not silently committed) with the full trace attached.

### 5.3 Traceability (replaces formal evals for now)
No golden/offline eval dataset exists yet (explicit decision — see §10).
Every plan decision, every specialist invocation (including the exact
prompt used, with any appended critique delta), every validation round's
critique, and the no-progress comparison made are logged automatically
around the `invoke_agent` call — not something an agent calls explicitly.
This is a precursor to future offline evals: real observed failures
(a validator false-positive, an unwarranted escalation, a plan that should
have fanned out but didn't) get harvested into fixture test cases later,
once there are enough real examples to be worth curating, rather than
inventing synthetic cases now.

### 5.4 Rejected alternative: separate Planner/Coordinator split
Considered splitting the Orchestrator into a narrow Planner/Router (pure
classification, no side effects) and a separate Coordinator (execution,
retries, git/DB safety, replanning callbacks on failure). Rejected: the
extra LLM round-trip for every job adds latency and cost that isn't
justified once §5.1's cheap-signal approach removes the need for the
Planner to do a genuine first read of the content. A single Orchestrator
handling both planning and execution reasoning, with its own internal
retry loop, is the simpler and cheaper design that still satisfies the
non-determinism test.

## 6. Tool interfaces

Tool boundaries are the actual enforcement mechanism for agent
responsibilities — an agent can't perform an operation outside its role
because the tool for it doesn't exist in its toolset, not because a prompt
tells it not to. This directly replaces the class of problem `git_guard`
patched after the fact (§8).

### 6.1 Text / Knowledge Agent
- Read: `read_source(source_id)`, `search_concepts(query)`,
  `get_concept(concept_id)` (full content + metadata, for merge decisions)
- Write: `create_concept(title, category, content, metadata)`,
  `update_concept(concept_id, content, metadata)`
- No relationship tools. No source-write tool (source material stays
  immutable and is never written by any agent tool — an unchanged hard
  rule carried forward from the current `CLAUDE.md` contract).

### 6.2 Graph Agent
- Read: `get_graph_neighborhood(concept_id, depth?)` (topology: edges,
  degree/centrality), `search_relationships(concept_id)`,
  `get_concept_metadata(concept_id)` — **title/category only, never full
  body content**. This exclusion is deliberate: it's what preserves the
  information asymmetry with the Text Agent that makes genuine
  disagreement (§4.3) possible instead of cosmetic.
- Write: `add_relationship(source_id, target_id, type, note, justification,
  confidence?)`, `update_relationship(...)`, `remove_relationship(...)`.
  `justification` is a required argument (§7.3, Layer 2) — a specific
  citation of the evidence grounding the claim, not a free-text note.
- No concept-content tools.

### 6.3 Validation Agent
- Read: `get_concept(concept_id)`, `get_graph_neighborhood(concept_id)`,
  `search_concepts(query)` — full cross-cutting read access, since it must
  check text/graph consistency.
- Write: **none.** Read-only by construction, not by convention. Its only
  output is the structured critique object (§5.2), returned to the
  Orchestrator, never written directly to the store.

### 6.4 Orchestrator
- `get_source_signals(source_id)` — deterministic, non-LLM (§5.1)
- `invoke_agent(agent_type, prompt_delta, context)` — dispatch to a
  specialist; this is a control tool, not a knowledge-domain tool
- `commit_job()` / `rollback_job()` — the transactional boundary that
  replaces `git_guard`'s commit/revert (§8)
- Trace logging (§5.3) happens automatically around `invoke_agent`, not as
  an explicit tool call

## 7. Text Agent: topic decomposition and overlap prevention

Today's single fused pass has no intermediate checkpoint between "read the
source" and "write concepts" — decomposition and writing happen invisibly
in one pass, so there's no artifact to inspect when topics get
over-fragmented or overlap. This design splits it into three stages.

### Stage A — Segmentation (structured output, no writes yet)
Text Agent's first output is a structured list of candidate topic units:
`{title, scope_description, source_excerpt_refs}`. This is a
table-of-contents step, not prose generation — a real, inspectable
artifact that lands in the trace log. `source_excerpt_refs` binds each
candidate to the specific portion of source material it may draw from,
which is the concrete mechanism (not just prompt discipline) for limiting
topic bleed at synthesis time.

### Stage B — Overlap check (self-consistency pass on the candidate list)
Before any writing, Text Agent must pass its own candidate list through a
disjointness check: does any pair's `scope_description` substantially
subsume or repeat another's? If so, they must be merged into one candidate
or have their scopes clearly redrawn before proceeding. Same pattern as
the existing "revisit relationships before finishing" pass in today's
`CLAUDE.md`, applied one stage earlier and at low cost (titles and
one-liners, not full content).

### Stage C — Per-topic synthesis
For each finalized candidate: run the existing dedup check against the
*global* knowledge base (Stage B only checked overlap within this batch),
then write via `create_concept`/`update_concept`, grounded only in that
candidate's attributed excerpt. This is where genuine synthesis judgment
belongs — writing a good explanatory note is real generative work, not
something to over-mechanize; the new discipline is that it's bounded to a
specific source slice rather than the whole document.

### Backstop — deterministic post-check
A cheap title/content similarity check across concepts committed in the
same job, catching over-fragmentation that slipped past Stage B's
self-check. Same "don't rely solely on the LLM's discipline, add a cheap
structural catch" principle as the graph-side backstops in §7 below —
consistent shape across both agents.

## 8. Graph construction: layered defenses against wrong edges/nodes

Relationship-building is the most inference-heavy, hallucination-prone
part of the pipeline (the existing prompt explicitly incentivizes an
aggressive "find every undeclared relationship" pass). Four layers, from
cheapest/most-certain to most-judgment-dependent:

### Layer 1 — Structural prevention (deterministic, inside the tool, no LLM judgment)
`add_relationship` refuses to create an edge when:
- The target concept ID doesn't exist (referential integrity — with a real
  graph DB this eliminates the "dangling reference" class of error that
  today's system only catches as a non-fatal `warning` after the fact).
- The edge would create a **cycle in a hierarchical edge type**
  (`subtopic-of`, `prerequisite-of`) — a reachability check before insert.
  See §8.1 for why only hierarchical types are constrained this way.
- An exact duplicate edge (same source/target/type) already exists,
  staged or committed, for this job.
- The edge would declare the **same symmetric relationship on both
  sides** — the specific bug already observed in the current system
  (§2). Prevented structurally here instead of relying on the prompt
  being followed correctly.

### Layer 2 — Required justification (raises the bar on what's proposed at all)
`add_relationship` requires a `justification` argument: a specific
citation of evidence (a quote or reference) grounding the claim — not a
free-text `note`. This turns "is this relationship real?" (hard to judge
from scratch) into "does this cited evidence actually support this claim?"
(checkable). An optional `confidence` field routes low-confidence
proposals through stricter validation scrutiny.

### Layer 3 — Semantic validation (Validation Agent's actual judgment)
For each staged edge: does the justification actually support the claim?
Is the relationship type appropriate given what the justification says
(not just structurally valid)? Does it duplicate an existing edge's intent
even if not byte-identical? Deliberately tuned to favor precision over
recall (§4.4) — reject on doubt.

### Layer 4 — Correction loop
The retry mechanism from §5.2, now operating on specific flagged edges
with concrete justification references — "your justification for X
doesn't establish Y, reconsider or remove" is a targeted delta prompt, not
a vague "try harder."

### 8.1 Is the graph a DAG?
Not uniformly — this splits by edge type:
- **Hierarchical/directional types** (`subtopic-of`, `prerequisite-of`)
  should be acyclic: "A is a subtopic of B, which is a subtopic of A" is a
  real contradiction. Enforced structurally at Layer 1, not left as a soft
  validation flag.
- **Symmetric/associative types** (`related-to`, `similar-to`) have no
  meaningful direction, so DAG-ness doesn't apply; cycles through these
  edges are expected and fine (concepts legitimately cluster).

The graph as a whole is a general (mixed directed/undirected) graph, not a
DAG. Only the subgraph formed by hierarchical edge types is constrained to
be acyclic.

## 9. Storage architecture

Three stores, each chosen for the kind of data it holds — not three
technologies for their own sake.

### 9.1 SQL
Relational, transactional data:
- `jobs(id, source_id, status, created_at, updated_at, error)` — status:
  `queued → running → succeeded | failed | needs_review`
- `job_rounds(job_id FK, round_number, agent_type, prompt_delta,
  output_summary, critique_json, cost_usd, timestamp)` — the full
  traceability record (§5.3)
- `agent_configs(agent_role PK, engine, provider, model, effort,
  env_key_name, updated_at)` — per-agent engine/model config (§9.4)

### 9.2 NoSQL (document store)
- `sources` — immutable, write-once: `{id, content, uploaded_at,
  topic_hint}`. No agent tool can write here (§6.1); writing a source is
  an app-level action outside the agent toolset entirely.
- `concepts` — `{id, title, category, body, metadata/aliases,
  status: pending|committed, job_id}` when pending. This is the direct
  document-store analog of a markdown file plus YAML frontmatter — same
  flexibility, no schema migration needed per new metadata field.

### 9.3 Graph DB (property graph model)
- **Nodes** — one per concept, keyed by the same `concept_id` as the
  NoSQL document, holding only a thin denormalized copy: `{id, title,
  category}`. Never independently authored — kept in sync only via
  `get_concept_metadata` reads, per §6.2's information-asymmetry design.
- **Edges** — `{type, note, justification, confidence, status:
  pending|committed, job_id, created_at}`, directed. Symmetric types are
  stored as a single directed edge and treated as bidirectional at query
  time (never physically duplicated — Layer 1, §8).

A graph database's native model (nodes + edges, traversal-optimized query
engine) is what actually earns its place here: it replaces today's
full-corpus scan-and-derive (`build_graph` reading and parsing every
markdown file on every cache miss) with real neighborhood/centrality
queries, which the Graph Agent's tools (§6.2) depend on directly.

**Local-first constraint on the graph DB choice:** the project's own
NFR1 (local-only, single-user, `127.0.0.1`-only, no infra to run) survives
this storage pivot even though the no-database rule doesn't. A
client/server graph DB (e.g. Neo4j, which runs as a separate JVM process)
cuts against that. **Kùzu** — an embedded graph database (same operating
model as SQLite: in-process, no separate server) with a property-graph
model — fits this project's actual scale and stated constraints
significantly better and is the recommended default, with a
client/server option left available if query needs outgrow it later.

### 9.4 Docker / free-and-open-source constraint
All three stores must run free, self-hosted, in Docker. Concrete pick,
pending your confirmation: **Postgres** (SQL, official Docker image),
**MongoDB** (NoSQL document store, official Docker image or a
Docker-friendly free alternative if licensing terms matter to you), and
**Kùzu** (graph, embedded — technically doesn't need its own Docker
container at all, since it's in-process, but can be colocated in the
backend's own container). None of these require a paid tier at this
project's scale.

## 10. Transactional consistency (replaces `git_guard`)

### 10.1 Why `git_guard` existed, and why it doesn't survive as designed
`git_guard` is a **detect-and-revert** safety net: because the ingestion
agent had generic, unscoped `Read/Write/Edit` access over the entire
repository, the only way to guarantee source material was never touched
was to check what changed after the fact and revert violations. It's a
patch compensating for coarse tool permissions, not a necessary pattern in
its own right. The actual fix is upstream: §6's scoped, purpose-built
tools make illegal operations impossible by construction (no tool exists
for an agent to write source material at all), which is a strictly better
guarantee than post-hoc detection — and it holds regardless of what
storage technology sits behind the tools.

### 10.2 What replaces it: pending/committed staging
With three separate stores, there is no single ACID transaction spanning
all of them the way one git commit atomically covered the whole repo.
Full distributed-transaction machinery (two-phase commit, saga pattern)
would be disproportionate for a single-user app. Instead:
- Every write from `create_concept`, `add_relationship`, etc. is tagged
  `status=pending, job_id=<current job>` in its respective store.
- `commit_job()` flips every `job_id`-tagged record across both stores
  from `pending` to `committed`, done sequentially (safe specifically
  *because* only one job runs at a time — no concurrent writer to race
  against; see the concurrency tripwire below).
- `rollback_job()` deletes every `job_id`-tagged pending record across
  both stores.
- On backend startup, any job still `running` in SQL triggers a
  reconciliation sweep: delete its orphaned pending records in the other
  two stores, mark it `failed`. This is a direct extension of the
  orphaned-job reconciliation that already exists today for the
  single-repo case, widened from one store to two.

### 10.3 Concurrency tripwire
This staging convention is sufficient *only* because the single-worker,
single-job-at-a-time constraint holds unchanged (§3, non-goals). If
parallel/fan-out job execution is introduced later (the deferred Option 3
"dynamic orchestration" extension), this consistency model must be
revisited — concurrent writers could interleave pending records from
different jobs, which the current design does not handle.

## 11. Engine / model / effort configuration

Generalizes the existing `ChatEngine` Strategy pattern (§14.2,
`chat_engine.py`) — already built for Phase 6/7 — to cover every agent
invocation, not just chat, rather than inventing new machinery.

### 11.1 `AgentEngine` protocol
Two implementations:
- **`ClaudeCodeEngine`** — the existing headless CLI subprocess (`claude
  -p`), subscription-based, no API key required (preserves FR2.2). This
  is the only live path today.
- **`LiteLLMEngine`** — API-key-based, any LiteLLM-supported
  provider/model. Not live yet (no key configured); the mechanism is
  built and ready, opted into per-agent-role once a key exists.

### 11.2 Tool-calling bridge (per engine)
The domain tools in §6 aren't native Claude Code CLI tools the way
`Read/Write/Edit` were. For `ClaudeCodeEngine`, they're exposed via an
**MCP server** that the `claude -p` invocation connects to, replacing
today's `--tools "Read,Write,Edit,Glob,Grep"` flag with an MCP config
scoped to exactly the tool set each agent role is allowed (§6). For
`LiteLLMEngine`, the same tool set is exposed via native function-calling
(which LiteLLM normalizes across providers). The tool *contract* (names,
arguments, semantics) defined in §6 is identical either way — only the
wiring differs.

### 11.3 Per-role configuration
`agent_configs` table (§9.1), one row per role: **Orchestrator, Text
Agent, Graph Agent, Validation Agent, Naming, Chat**. Every row always
carries:
- `engine` — `claude_code | litellm`
- `model` — options enumerated per engine (Claude Code: Sonnet 5, Opus
  5.5, Haiku 4.5, Fable 5.1; LiteLLM: whatever the selected provider
  exposes)
- `effort` — options enumerated per engine (Claude Code: low / medium /
  high / xhigh / max; LiteLLM: provider-specific, e.g. OpenAI's
  `reasoning_effort` scale, which does not necessarily line up 1:1 with
  Claude Code's levels)

Only present when `engine=litellm`: `provider`, `env_key_name`.

### 11.4 Credential handling
`env_key_name` stores a reference (e.g. `"OPENAI_API_KEY"`), never a key
value — the DB never holds a secret, preserving the project's existing
"credentials via env vars only" rule unchanged even though persistence
otherwise moved off the filesystem. At invocation time, `LiteLLMEngine`
reads `os.environ[env_key_name]` fresh on every call, not cached at
config-save time, so rotating a key in `.env` and restarting the backend
requires no DB write.

### 11.5 Save-time validation
Saving a row with `engine=litellm` checks that `env_key_name` resolves to
a currently-set environment variable and rejects the save with a clear
message if not (e.g. `"OPENAI_API_KEY not set — add it to .env and
restart the backend"`), rather than failing silently the first time that
agent actually runs.

### 11.6 Default state
Every role defaults to `engine=claude_code`. Nothing in current runtime
behavior changes until a specific row is deliberately switched to
`litellm` once a key exists — this design is fully built and ready, but
the live path is 100% Claude Code CLI until you opt in per role.

## 12. Summary of what changes vs. `docs/ARCHITECTURE.md`

For the reader cross-referencing the existing architecture doc when this
is implemented:
- §5.1–§5.2 (CLI invocation mechanism) — the invocation shape changes
  (MCP-scoped tools instead of raw filesystem tools; model/effort now
  per-agent-configurable instead of a fixed default), but the core
  "headless `claude -p`, subscription auth, no API key by default"
  property is preserved as today's live path.
- §5.3–§5.5 (single-invocation ingestion flow, git-based safety net) —
  replaced by §4–§8 and §10 of this document.
- §7 (no database) — reversed. Filesystem-as-state is replaced by the
  three-store split in §9. This is a conscious override of a documented
  decision, not an incidental side effect — §7's own rationale (avoiding
  an unnecessary second source of truth for a single-user app) should be
  revised, not silently dropped, when `ARCHITECTURE.md` is updated to
  match this design.
- §14.2 (Strategy pattern for `ChatEngine`) — extended in shape (§11),
  not replaced; the pattern itself was correctly identified in the
  original design and is being reused, not redone.
- §1, §6 (content directory location, repository-pattern *principle*),
  NFR1 (local-only, no auth) — unchanged.

## 13. Open items for implementation-time verification

- The exact Claude Code CLI flag(s) for selecting model and effort level
  need to be verified against the CLI's actual current interface before
  `runner.py` is modified — this design assumes flags exist for both
  (consistent with this session's own `/model` command exposing a
  model + effort choice) but the precise flag names weren't verified
  against CLI documentation during this discussion.
- Concrete Docker images/versions for Postgres, MongoDB (or a
  Docker-friendly alternative if MongoDB's license terms are a concern),
  and Kùzu's deployment shape (embedded within the backend container vs.
  its own container) should be pinned during implementation planning, not
  assumed final from this document.
