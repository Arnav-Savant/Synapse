# Synapse: architecture

How Synapse is built and why. [`REQUIREMENTS.md`](REQUIREMENTS.md) lists what it
must do; [`SETUP.md`](SETUP.md) covers running it.

## 1. Shape of the system

Synapse is an ingestion and authoring engine. Raw input goes in; linked Markdown
notes come out, written into Obsidian vaults that the owner opens separately.

```
Browser (React) ──HTTP──▶ FastAPI backend (host, 127.0.0.1:8000)
                              │  starts workflows, sends decisions, reads state
                              ▼
                    Temporal server (Docker) ◀─gRPC─▶ Temporal worker (inside the backend process)
                              │                            │
                              ▼                            ├─ agent steps: `claude -p` subprocesses
                    Postgres (Docker)                      └─ deterministic steps: commit, delete, reconcile
                    app tables + Temporal's databases
                                                      Vault folders on disk ◀── written only by deterministic code
                                                      Obsidian ───────────────▶ reads the same folders
```

Four principles shape everything below.

1. **Files are the truth.** A note exists because its Markdown file exists. Postgres
   holds a derived index that can be rebuilt by scanning the vaults, plus drafts,
   jobs and settings.
2. **Agents never write files.** An agent returns structured output. Deterministic
   code validates it, assembles the file, and is the only code that writes to a vault.
3. **Code decides control flow.** Workflows are deterministic. No model chooses which
   step runs next; code routes on structured results and on the owner's decisions.
4. **Nothing enters a vault unapproved,** and nothing the owner edited is overwritten.

### Why the backend runs on the host

Agents are `claude -p` subprocesses that rely on the logged-in user's credentials in
their home directory. A container has neither the CLI nor those credentials, so the
backend and the Temporal worker (which lives in the backend process) run on the host.
Only Postgres and the Temporal server run in Docker (`docker-compose.yml`).

## 2. Repository layout

```
backend/
  main.py                  dev entry point (uvicorn)
  alembic/                 database migrations, applied automatically at startup
  app/
    main.py                app construction, startup sequence, exception handlers, route wiring
    core/                  config, logging setup, Postgres connection
    db/                    ORM models, first-run seeding
    schemas/               pydantic models for API payloads and agent output
    repositories/          data access: the only code that touches tables
    services/              business logic that combines repositories, agents and the vault
    vault/                 pure library for note files: titles, paths, wikilinks, frontmatter, assembly, atomic store, locks
    engines/               the `claude -p` wrapper
    agents/                one module per agent role: prompt builder and output schema
    workflows/             Temporal workflows, activities, worker and client
    api/                   thin HTTP routes
frontend/src/
  api/                     typed clients, one per backend area
  design/                  tokens and primitives
  shell/                   sidebar and page frame
  features/                ingest, jobs, outline, drafts, notes, settings
docker-compose.yml         Postgres, Temporal, Temporal UI
```

Layers depend downward only: routes call services; services call repositories, agents
and the vault library; the vault library depends on nothing else in the app.
Workflow activities are thin: they take ids, load state, call a service, and record cost.

## 3. Startup sequence

`app/main.py` runs these in order and logs each:

1. Check that `VAULTS_ROOT` is an absolute, existing, writable directory (otherwise exit).
2. Apply database migrations (`alembic upgrade head`).
3. Seed the eleven agent role rows that do not exist yet.
4. If no domain exists, create the three starter domains and their vault folders.
5. Reconcile every vault with the note index (§10).
6. Connect to Temporal, retrying for about fifteen seconds (otherwise exit with a hint).
7. Start the admission workflow if it is not running (§5.3).
8. Mark any active job whose workflow no longer exists as failed, and release its slot.
9. Start the worker.

A failure in step 5 or 8 is logged and does not stop startup; failures in 1, 2 and 6 do.

## 4. Data model

All tables live in one Postgres instance, which Temporal shares for its own databases.

| Table | Holds |
|---|---|
| `domains` | slug, name, purpose, vault path, profile (JSON) |
| `agent_configs` | per role: model, effort, `params` (JSON budgets) |
| `jobs` | input kind and text, domain choice, resolved domains, status, current step, awaiting-owner flag, error, total cost, workflow id, profile snapshot, classifier confidence |
| `step_runs` | an audit row per step: step, agent role, attempt, status, cost, error. Prompts and outputs are not kept. |
| `outline_drafts` | one row per job: the outline tree with its hub placement per domain (JSON) and last feedback. Overwritten on every re-plan. |
| `note_drafts` | one row per job, domain and node: assembled file text, title, parents, frontmatter, kind (`new` or `merge`), target path, merge target and base hash, validator flags, dossier, stage (`researched`, `written`, `validated`, `stale`) |
| `notes` | the index: id, domain, title, path (relative to the vault), aliases, summary, content hash, topic id, creating job, `user_modified`, `is_hub`, and a generated full-text vector |
| `note_links` | the index of links between notes: source, destination (if resolved), destination title, kind (`parent`, `related`, `body`) |

Job statuses are `queued`, `running`, `awaiting_owner`, `completed`, `failed`,
`cancelled`. Steps are `classify`, `outline`, `place`, `overlap`, `outline_gate`, `research`,
`write`, `references`, `related`, `validate`, `draft_gate`, `commit`.

`notes` has a full-text GIN index, a trigram index on the title (`pg_trgm`), and a
unique index on `(domain, lower(title))`. Draft rows are overwritten when regenerated
and deleted when the job ends; note text is not stored in Postgres once committed.

## 5. The ingest workflow

One Temporal workflow (`IngestTopicWorkflow`) per job. Its id is the job id; all
workflows use the task queue `synapse-ingest`.

### 5.1 Steps

```
queued ─▶ classify ─▶ outline ─▶ place ─▶ overlap ─▶ OUTLINE GATE ─▶ research* ─▶ write ─▶ references ─▶ related ─▶ validate ─▶ DRAFT GATE ─▶ commit ─▶ completed
                                                │  re-plan ◀┘                       (leaves, parents, top)        └ rewrite failing notes ◀┘    │ feedback ◀┘
* topic jobs only
```

| Step | What happens | Agent |
|---|---|---|
| classify | Choose the domain(s) when the owner picked Auto-detect; skipped when a domain was chosen or only one domain exists | classifier |
| outline | Propose the tree | planner (topic) or structurer (pasted content) |
| place | Per domain, decide the hub path above the topic (none, one or two levels) and which existing top-level notes to attach beside it | placer |
| overlap | Per node and domain, find candidate existing notes and judge same, partial or distinct | linker |
| outline_gate | Wait for the owner | none |
| research | Per leaf, in parallel: facts and sources | researcher |
| write | Leaves in parallel, then parents by height, then the top note | writer, synthesizer |
| references | Per leaf: ranked, verified links | reference finder |
| related | Per draft: cross-links to existing and sibling notes | linker |
| validate | Rule checks, then the reviewer agent; failing notes are rewritten, at most twice | validator |
| draft_gate | Wait for the owner | none |
| commit | Write the approved drafts to the vault and update the index | none |

### 5.2 Gates and signals

The workflow receives `outline_decision`, `draft_decision`, `cancel` and
`slot_granted` signals and answers a `status` query. At the outline gate the owner can
approve an edited tree or ask for a re-plan with feedback. An invalid edit does not
fail the job: the workflow stays at the gate and records why. At the draft gate the
owner can approve a set of drafts, or send feedback scoped to a section, a note or the
topic. Feedback rewrites only the targeted drafts in place, children before parents,
optionally re-researching first, then validates them once and returns to the gate. An
approve commits the chosen drafts and discards the rest. Drafts the commit could not
write (a stale merge, a refused title) return to the gate.

### 5.3 Admission control

A separate long-lived workflow (`pipeline-admission`) limits how many pipelines
execute at once (two). A job signals `acquire` and waits for `slot_granted`; it signals
`release` when done, cancelled, failed, or before waiting at a gate. Slots are granted
first in, first out. Duplicate acquires and releases are ignored, and a waiter that
disappears is skipped. The workflow restarts itself after 500 signals to keep its
history small.

### 5.4 Reliability layers

| Layer | Handles | Policy |
|---|---|---|
| Output shape | An agent reply that is not valid for its schema | Re-ask with the error and the rejected reply, at most twice |
| Quality loop | A draft the reviewer rejects | Rewrite only the failing notes with the issues attached, at most two rounds, stop early when the same issues recur, then send them to the owner flagged |
| Temporal retries | Timeouts, crashes, rate limits | Three attempts with exponential backoff (5 s to 2 min); output-shape failures are not retried |
| The owner | Anything else | Unlimited re-plans and feedback rounds |

Every agent activity heartbeats from a background task while its subprocess runs (every
15 s, 60 s timeout), so Temporal can tell a long call from a dead worker and can cancel it.
Each activity can be re-run safely: drafts are overwritten and commits are idempotent.

### 5.5 Parallelism

The workflow itself limits fan-out to `MAX_CLAUDE_PROCESSES`, so an activity's timeout
never includes time spent waiting for a process slot. The engine independently caps
concurrent `claude` subprocesses at the same number. Worker activity slots are four times
larger, so quick database activities never queue behind long agent calls. When one
parallel activity fails or the owner cancels, the rest are cancelled, so nothing keeps
spending for a job that has ended.

### 5.6 Failure and cancellation

A failed step ends only its own job: the job becomes `failed` with a plain-language
reason, its drafts are deleted, its slot is released, and the backend keeps serving.
Cancel works the same way with status `cancelled`. If a workflow disappears (for example
it was terminated) the startup check marks the job failed.

## 6. Agents

Each role is a separate `claude -p` invocation with its own model and effort, editable
in Settings. The defaults:

| Role | Job | Tools | Model, effort |
|---|---|---|---|
| `classifier` | Pick the domain(s) and a confidence | none | Haiku, low |
| `planner` | Light web scan, propose the outline | web | Sonnet, medium |
| `structurer` | Split pasted content into the outline, one slice per node | none | Sonnet, medium |
| `researcher` | Research one leaf into a dossier | web | Sonnet, medium |
| `linker` | Overlap verdicts; related links | none | Sonnet, low |
| `writer` | Write leaf notes, domain versions and merges | none | Opus, high |
| `synthesizer` | Write parent and top notes; the shared core of cross-domain notes | none | Sonnet, medium |
| `reference_finder` | Rank and annotate references | web | Haiku, low |
| `validator` | Judge scope, depth and accuracy | none | Sonnet, high |
| `profile_builder` | Draft a domain profile | none | Sonnet, medium |
| `placer` | Choose the hub path above a topic and which existing notes join it | none | Sonnet, low |

"Web" means `WebSearch` and `WebFetch`, and nothing else.

The models a role may use are a fixed list in `agent_config_service`: four pinned versions (Fable 5.1,
Opus 5.5, Sonnet 5.5, Haiku 5.5) and the four aliases that track the newest release (`fable`, `opus`,
`sonnet`, `haiku`). The CLI has no command that lists models, so the list follows Claude Code's model
documentation; the settings screen reads it from `GET /agent-configs/models`, and an update with any other
value is rejected. All of them support the five effort levels.

### 6.1 The engine

`ClaudeCodeEngine` runs one invocation: it resolves the role's model and effort from
`agent_configs`, then starts `claude -p` with `--restricted`, `--tools` and
`--allowedTools` set to exactly the role's tool list (an empty list disables every tool),
`--permission-prompts none`, `--output-format stream-json`, and `--no-session-persistence`.
It reads the event stream to get the final result and cost, and to collect the URLs the
session retrieved: `WebFetch` targets and `WebSearch` hits. A process-wide semaphore
bounds concurrent subprocesses. A timeout or cancellation kills the subprocess.

### 6.2 Structured output

`run_structured` appends the pydantic model's JSON Schema to the prompt, extracts the
JSON object from the reply (tolerating prose around it), validates it, and on failure
re-asks. Costs of all attempts are summed and carried on the error if it finally fails.
Agent-facing models carry their own structural rules (for example, an outline must have
one root and no cycles) as validators, so a structural error becomes a re-ask with a
specific message.

### 6.3 What agents are given

- Prompts embed the domain profile's objective, scope rules and style. Adjacent
  technologies are mention-only. Outline size follows topic size.
- Web content is described to the agent as untrusted data.
- A writer receives the dossier (or the node's content slice), the shared core for
  cross-domain notes, and for a merge the current file text and the instruction to keep
  the owner's edits. It returns body sections only: reserved headings (`Up`, `Subtopics`,
  `Related`, `References`) are stripped from its output.
- The validator sees the note's prose only. The generated link lists are checked by code.

### 6.4 Source integrity

A reference is kept only if its URL was retrieved during the session and passes a live
check. The check treats a 2xx, 3xx, 401, 403 or 429 response as live (many official sites
refuse scripts but the page exists), and refuses non-HTTP, local and private addresses.

## 7. The vault

### 7.1 Files and folders

`$VAULTS_ROOT/<domain slug>/<Topic folder>/<Note title>.md`. All notes of a topic sit in
one folder named after the topic's top note, so the hierarchy is carried by links and
frontmatter, not by nesting. A new node under an existing tree goes in that tree's folder.

### 7.2 Titles and paths

A title becomes a file name, so `\ / : * ? " < > | # ^ [ ]` are removed, whitespace is
collapsed, leading and trailing dots and spaces are stripped, and the result is capped at
120 characters. Titles are compared case-insensitively on their Unicode-normalised
form. Every path is resolved (following symlinks) and must stay inside its domain's
folder, or the operation is refused.

### 7.3 Note anatomy

```
---                                  frontmatter: synapse_id, topic_id (cross-domain copies only), domain,
synapse_id: …                        parents, aliases, summary, job_id, created
…
---

Up: [[Parent]], [[Other parent]]     omitted on a topic's top note

<body>                               leaf notes follow the profile's sections; parents compare their children

## Subtopics                         generated from the outline
- [[Child]]: one-line pointer
## Related                           chosen by the linker; additive
- [[Note]]: why
## References                        verified links, official sources first; additive
- [title](url): annotation
```

Agents supply only the body. Code assembles the rest, so a malformed file cannot be
produced. Empty sections are left out, and a body line that is only `---` is escaped so
the frontmatter stays unambiguous. There is no `type` field: a note's role (leaf, parent,
top) is derived from its links, because it changes as the graph grows.

### 7.4 Wikilinks

A small scanner (not regular expressions) finds `[[X]]`, `[[X|alias]]`, `[[X#heading]]`
and `[[X#^block]]`, understands the escaped pipe used in tables, and skips fenced code and
inline code. Removing links to a note deletes a list entry that is only that link and turns
an inline link into its alias or target as plain text.

### 7.5 Writing

`write_note_atomic` writes to a temporary file in the same folder, fsyncs, sets the mode
(an existing file keeps its mode; a new one is 0644), and renames it into place, so a crash
never leaves a half-written note. It returns the SHA-256 of what was written. Operations on
one vault run under a per-domain lock.

### 7.6 The index

`notes` and `note_links` mirror the vault. Links are classified as parent (frontmatter
`parents`), related (inside `## Related`) or body (everything else except the `Up:` line).
`content_hash` is the hash of the file as Synapse last wrote it; a different hash on disk
means the owner edited it. The index repository flushes but never commits, so a commit can
update notes and links in one transaction.

## 8. Overlap, merging and placement

### 8.1 Overlap

Overlap is judged on meaning, in two stages.

1. **Candidate retrieval** (deterministic, within one domain): an exact match on title or
   alias first, then full-text rank over title, aliases and summary, then trigram
   similarity of the titles. At most eight candidates.
2. **Judgement** (linker agent): per node and domain, `same` (merge into the existing
   note), `partial` (write a new note that links to the existing one, and give the existing
   note a back-link), or `distinct`. With no candidates the answer is `distinct` and the
   agent is not called.

Verdicts are per node and per domain, so one node can merge in one vault and be new in
another. The owner can override any verdict at the outline gate.

### 8.2 Merging

A **merge** draft starts from the file as it is on disk now, including the owner's edits.
The writer returns an updated body; code replaces only the body, leaves the frontmatter, the
`Up:` line and the link lists in place, and adds new parents, subtopics, aliases, related
links and references without removing anything.

### 8.3 Hubs and placement

A **hub** is a short overview note that groups related topics, such as *Database internals* above
*Buffer pool management* and *Write-ahead logging*. It is an ordinary note with `hub: true` in its
frontmatter (indexed as `notes.is_hub`) and lives in the vault's `Hubs` folder. A topic's notes live in
a folder of their own, named after its top note.

After the outline is drafted, the **placer** receives the domain, the topic and its subtopics, the
hubs that already exist (as a tree with their summaries) and the existing top-level notes that are not
under any hub. It returns a path of hubs above the topic, outermost first, and the existing notes to
attach beside it. The rules are enforced in code, and a violation becomes a specific re-ask:

- at most two levels, and zero or one are fine; an existing hub must be copied exactly from the list,
  and an existing hub can sit only under another existing hub that really is its parent;
- a new hub needs a title and a one-line summary and may not duplicate a hub, or a note of any kind, that
  is already in the vault;
- attached notes must come from the list and need a hub to go under (at most eight).

The result is stored on the outline per domain (`ancestors`, `adopt`), shown at the outline gate, and
editable there. Edits go through the same checks, including a re-check when the owner approves. A re-plan
keeps the owner's placement.

When drafts are built, the path is expanded into extra nodes above the topic's top note. A **new** hub is
written like any overview note, with no research. An **existing** hub, and each attached note, is a
`reuse` node: it supplies its title and is never rewritten. Committing then does only single-line work on
existing files:

- the topic's top note is added to an existing hub's `## Subtopics` by one inserted line (as is each
  attached note);
- each attached note gets the hub added to its `parents` and its `Up:` line, and nothing else changes in it.

Both are listed at the draft gate before anything is approved. A new hub's own `## Subtopics` is generated
like any parent note's, and includes the attached notes. Later topics see the hub as an existing one and
attach to it the same way.

## 9. Commit

`commit_drafts` works per vault under its lock:

- A **merge** is written only if the file's hash still equals the hash recorded when the
  draft was made. If not, nothing is written, the draft is marked stale, and the workflow
  rebuilds it from the current file and shows it again. A merge whose target file is gone is
  refused, never created over.
- A **new** note is refused if its title exists in the vault (under a different id) or a file
  already exists at its path.
- A file that already holds exactly the draft's text is indexed without being rewritten, so
  re-running after an interruption completes cleanly.
- Notes are written first; links are indexed after every note in the vault is in the index,
  so they resolve. Back-links for `partial` verdicts are single-line insertions into
  the existing note; every other line stays byte-identical and `user_modified` is unchanged.
- The index row of a committed note starts with `user_modified = false`, since the new
  version began from the file on disk.

## 10. Deleting notes and reconciling

**Delete** (`note_delete_service`) is deterministic: no agent is involved.

- A *plan* is built without side effects. It reads the vault's files, not the index, because
  the owner edits notes in Obsidian and the index can lag. It lists the notes to delete, the
  files whose links to them will be stripped, the children to re-attach, and the notes that
  need an extra confirmation because the owner edited them.
- Selection is by note ids, by topic folder, or by creating job (across vaults). For notes
  that exist in two vaults, deletion can cover this vault only or every vault.
- *Applying* the plan re-reads every file under the vault lock, rewrites the other notes
  first (a child's `parents` and `Up:` line take the deleted note's own parents, or none; links
  are stripped; sections left empty are dropped), then removes files and index rows, and finally
  removes an emptied topic folder. It can be run twice safely, and a crash can leave an extra
  file but never a dangling link.

**Reconcile** compares each vault with the index, at startup and on demand:

- a file with no `synapse_id` is the owner's own note: it is indexed and given an id,
- a known id at a new path is a move,
- a changed hash marks the note edited by the owner,
- a copied file that repeats another note's id gets a new id,
- an indexed file that is gone gets the delete cleanup,
- a file that still exists but cannot be read (for example, invalid frontmatter mid-edit) is
  skipped and never treated as deleted,
- `.obsidian/` and other dot-folders are never read or written.

## 11. Cross-domain topics

When the classifier returns several domains, the topic is written into each vault. There is one
outline and one dossier. A short domain-neutral core is written once per leaf and given to every
domain's writer as the invariant, and each writer produces the note through its own profile,
briefly naming the other domains' concerns. The copies share a `topic_id` and are never linked
across vaults.

## 12. HTTP API

All routes are under `/api`.

| Route | Purpose |
|---|---|
| `GET /health` | Liveness |
| `GET /domains`, `POST /domains`, `PUT /domains/{slug}`, `DELETE /domains/{slug}` | Domain management |
| `POST /domains/draft-profile` | Draft a profile with Claude; saves nothing |
| `GET /agent-configs`, `PUT /agent-configs/{role}` | Per-role model, effort and budgets; a model outside the allowed list is refused |
| `GET /agent-configs/models` | The models a role can be set to |
| `POST /jobs`, `GET /jobs`, `GET /jobs/{id}` | Submit a job, list jobs, one job with its steps |
| `GET /jobs/{id}/outline`, `POST /jobs/{id}/outline-decision` | The outline gate; the view includes, per domain, the hubs and top-level notes the topic can be placed with |
| `GET /jobs/{id}/drafts`, `POST /jobs/{id}/draft-decision` | The draft gate |
| `POST /jobs/{id}/cancel` | Cancel a job |
| `GET /notes?domain=&q=` | List and search notes |
| `POST /notes/delete-preview`, `POST /notes/delete` | Preview and perform a delete |
| `POST /notes/reconcile` | Rescan the vaults |

Submitting a job records it and asks Temporal to start its workflow, then returns; no work
runs inside a request. Errors use specific statuses with a readable `detail`: 400 invalid
input, 404 not found, 409 conflict or wrong state, 413 input too large, 422 malformed payload,
502 agent failure, 503 workflow could not start, and 500 for anything unexpected.

## 13. Frontend

React with TypeScript, Vite and Tailwind, with TanStack Query for server state and no router
(four top-level views held in state; the two approval screens open from inside Jobs).

- `design/` holds the tokens (a cool grey-green neutral palette and one verdigris accent, with
  light and dark values that follow the OS) and the primitives (button, chip, card, form fields,
  empty state, spinner). Status colours are functional only.
- `shell/` holds the sidebar, with the live "needs you" count, and the page frame with its sticky
  action bar.
- `features/` has one folder per screen. Pure logic (outline edits, status mapping, decision
  building, markdown preparation) lives in plain modules beside the components.
- The job list polls every three seconds and the sidebar count shares that one query.
- Fonts are self-hosted: Instrument Sans for the interface, Newsreader for rendered note
  previews, JetBrains Mono for ids and paths.

## 14. Error handling and logging

**Errors.** Each layer raises its own typed exceptions (repositories: not found or already
exists; services: invalid input, wrong state, in use, storage; agents: unusable output;
engine: failed invocation). `app/main.py` maps each to a specific HTTP status. A catch-all
handler logs the full traceback and returns a generic 500, so after startup no unexpected
error can stop the process. Database uniqueness races and file-system failures are caught and
turned into the same typed errors. Background work catches at its top level, logs the
traceback, records a plain-language reason on the job, and fails only that job.

**Logging.** Each module has a `logging.getLogger(__name__)` logger, and logs are a readable
account of what the system did: one sentence per real event, carrying the ids needed to trace
it and the reason when it is not obvious, written once by the layer that owns the event.

- INFO: state changes, side effects, agent calls with model and cost.
- WARNING: something was refused, degraded or retried.
- ERROR: a failure, with its cause.
- CRITICAL: startup cannot continue.
- DEBUG: detail useful only when chasing a bug.

Note bodies, prompts, fetched web content and secrets are never logged; sizes and counts are.

## 15. Security boundaries

- The backend binds to `127.0.0.1`, has no authentication, and accepts only the configured
  frontend origin. Temporal and Postgres are published on `127.0.0.1` only.
- Agents have no file tools, and tools are an explicit allow-list per call. Only three roles may
  browse, and what they read is treated as untrusted data.
- Every write path is checked to resolve inside its vault, after following symlinks.
- Cited URLs are verified, and the liveness check refuses local and private addresses.
- Vault contents and `VAULTS_ROOT` are never committed, and the application never runs git.

## 16. Limits and defaults

| Setting | Value |
|---|---|
| Pipelines running at once | 2 |
| `claude` subprocesses at once | `MAX_CLAUDE_PROCESSES`, default 4 |
| Input size | 200,000 characters |
| Outline | one root, at most 40 nodes, at most 5 levels |
| Classifier confidence flagged below | 0.7 |
| Output-shape re-asks per agent call | 2 |
| Quality rewrite rounds | 2 |
| Temporal attempts per activity | 3 |
| Overlap candidates per node | 8 |
| Hub levels above a topic | 0 to 2 |
| Existing notes attached under a hub at once | 8 |
| References per note | at most 8 |
| Note title length | 120 characters |

## 17. Engineering standards

These apply to every change.

- **One responsibility per module.** A repository does data access and nothing else; an agent
  module builds one prompt and defines one output schema; a route validates input and delegates;
  a service combines the pieces. If a module starts doing two of these, split it. Files that grow
  past a few hundred lines are a prompt to extract, not a limit to reach.
- **Use patterns where the design needs them.** The repository/service/route layering is
  deliberate; an interface exists only where there are really two implementations. No speculative
  abstraction.
- **Pure functions for analysis**: title handling, wikilink parsing, assembly, outline validation and
  status mapping take data in and return data out, with no I/O.
- **Typed exceptions, handled where they can be acted on**, and mapped centrally to HTTP responses.
  Never swallowed, never left as a raw traceback to the caller, no bare `except`.
- **Logging as described in §14**, with meaningful lines and not per-function chatter.
- **Files live in the folder their responsibility maps to.** No catch-all `utils` module.
- **Naming says what a thing is**; no single-letter names outside a tight local scope.
- **Workflow code stays deterministic.** It routes on results; anything with I/O or randomness is an
  activity, and every activity is safe to re-run.

## 18. Verifying a change

The repository has no automated test suite. A change is checked by running it:

- Backend: start the services and the backend, then exercise the affected route or workflow with
  `curl` or the UI, including at least one provoked failure that should produce a clean error and a
  log line. The Temporal UI at `http://127.0.0.1:8233` shows workflow progress.
- Pure modules (`app/vault`, outline validation, wikilinks) can be exercised from a short Python
  snippet against temporary folders.
- Frontend: `npm run build` and `npm run lint` must pass, and the affected screen is checked in a
  browser in both themes.
- Anything that calls agents costs money; prefer a small topic and a trimmed outline.
