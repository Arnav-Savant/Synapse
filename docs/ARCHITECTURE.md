# Synapse: architecture

How Synapse is built and why. [`REQUIREMENTS.md`](REQUIREMENTS.md) lists what it
must do; [`SETUP.md`](SETUP.md) covers running it.

## 1. Shape of the system

Synapse is an ingestion and authoring engine and a study companion. Raw input goes in;
linked Markdown notes come out, written into Obsidian vaults that the owner opens
separately. The owner can then study by chatting with agents that answer from those
notes (§12).

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

Five principles shape everything below.

1. **Files are the truth.** A note exists because its Markdown file exists. Postgres
   holds a derived index that can be rebuilt by scanning the vaults, plus drafts,
   jobs, chats and settings.
2. **Agents never write files.** An agent returns structured output. Deterministic
   code validates it, assembles the file, and is the only code that writes to a vault.
3. **Ingest is deterministic.** The ingest workflow decides control flow in code. No
   model chooses which ingest step runs next; code routes on structured results and on
   the owner's decisions, because a mistake there reaches the vault.
4. **Chat is agentic.** Chat only reads, so its agents decide what happens next: an
   orchestrator agent chooses which subagent to delegate to, when it has enough, and
   when to answer. The chat runtime only carries out the actions the agents choose,
   within fixed limits (§12).
5. **Nothing enters a vault unapproved,** and nothing the owner edited is overwritten.

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
    services/              business logic that combines repositories, agents and the vault;
                           chat_runtime.py runs the chat agents' actions (§12)
    vault/                 pure library for note files: titles, paths, wikilinks, frontmatter, assembly, atomic store, locks
    engines/               the `claude -p` wrapper
    agents/                one module per agent role: prompt builder and output (or action) schema
    workflows/             Temporal workflows, activities, worker and client
    api/                   thin HTTP routes
frontend/src/
  api/                     typed clients, one per backend area
  design/                  tokens and primitives
  shell/                   sidebar and page frame
  features/                ingest, jobs, outline, drafts, notes, chat, settings
docker-compose.yml         Postgres, Temporal, Temporal UI
```

Layers depend downward only: routes call services; services call repositories, agents
and the vault library; the vault library depends on nothing else in the app.
Workflow activities are thin: they take ids, load state, call a service, and record cost.

## 3. Startup sequence

`app/main.py` runs these in order and logs each:

1. Check that `VAULTS_ROOT` is an absolute, existing, writable directory (otherwise exit).
2. Apply database migrations (`alembic upgrade head`).
3. Seed the seventeen agent role rows that do not exist yet.
4. If no domain exists, create the three starter domains and their vault folders.
5. Reconcile every vault with the note index (§10), and mark any chat answer that was
   still being worked on as failed (§12.6).
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
| `outline_drafts` | one row per job: the outline tree with its parent placement per domain (JSON) and last feedback. Overwritten on every re-plan. |
| `note_drafts` | one row per job, domain and node: assembled file text, title, parents, frontmatter, kind (`new` or `merge`), target path, merge target and base hash, validator flags, dossier, stage (`researched`, `written`, `validated`, `stale`) |
| `notes` | the index: id, domain, title, path (relative to the vault), aliases, summary, content hash, topic id, creating job, `user_modified`, and a generated full-text vector |
| `note_links` | the index of links between notes: source, destination (if resolved), destination title, kind (`parent`, `related`, `body`) |
| `chat_sessions` | one row per chat: title, the domains it reads, the running summary of older messages and the position it covers |
| `chat_messages` | the messages of a chat in order: role (`owner` or `assistant`), text, status (`pending`, `answered`, `failed`), current step, citations, gaps, verifier flags, error, cost |
| `chat_evidence` | the passages fetched during a chat: a per-chat reference number, domain, note id and title, section heading, the excerpt, and the message that fetched it |

Job statuses are `queued`, `running`, `awaiting_owner`, `completed`, `failed`,
`cancelled`. Steps are `classify`, `outline`, `place`, `overlap`, `outline_gate`, `research`,
`write`, `references`, `related`, `validate`, `draft_gate`, `commit`.

`notes` has a full-text GIN index, a trigram index on the title (`pg_trgm`), and a
unique index on `(domain, lower(title))`. Draft rows are overwritten when regenerated
and deleted when the job ends; note text is not stored in Postgres once committed.
The one exception is `chat_evidence`: the excerpts an answer was built from belong to
the chat, so a chat can still show its sources later. They are deleted with the chat
and are never read back as notes.

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
| place | Per domain, decide the parent notes above the topic (none, one or two levels) and which existing top-level notes to attach beside it | placer |
| overlap | Per node and domain, find candidate existing notes and judge same, partial or distinct | linker |
| outline_gate | Wait for the owner | none |
| research | Per leaf, in parallel: facts and sources | researcher |
| write | Leaves in parallel, then parents by height, then the top note | writer, synthesizer |
| references | Per leaf: ranked, verified links; skipped when the job has the reference search switched off | reference finder |
| related | Per draft: justified cross-links to notes outside its own ancestors and descendants | linker |
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
| `writer` | Write leaf notes, domain versions and merges | none | Sonnet, high |
| `synthesizer` | Write parent and top notes; the shared core of cross-domain notes | none | Sonnet, medium |
| `reference_finder` | Rank and annotate references | web | Haiku, low |
| `validator` | Judge scope, depth and accuracy | none | Sonnet, medium |
| `profile_builder` | Draft a domain profile | none | Sonnet, medium |
| `link_pruner` | Of one note's Related entries, keep only the prerequisites and contrasts | none | Haiku, low |
| `placer` | Choose the parent notes above a topic and which existing notes join it | none | Sonnet, low |
| `chat_orchestrator` | Lead a chat turn: delegate, judge the evidence, write the answer | none (chat actions, §12) | Sonnet, medium |
| `navigator` | Find the notes that could answer a question, from the vault map | none (chat tools, §12) | Sonnet, medium |
| `reader` | Extract the passages that matter from the chosen notes | none (chat tools, §12) | Haiku, low |
| `answer_verifier` | Check a draft answer against its evidence | none | Sonnet, medium |
| `chat_summarizer` | Fold a chat's older messages into its running summary | none | Haiku, low |

"Web" means `WebSearch` and `WebFetch`, and nothing else. The chat agents get no built-in
tools at all: their tools are functions in the backend that the chat runtime runs when an
agent asks for them (§12.3).

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
   note), `partial` (write a new note, with the existing one offered to it as a possible cross-link; the existing
   note is not edited), or `distinct`. With no candidates the answer is `distinct` and the
   agent is not called.

Verdicts are per node and per domain, so one node can merge in one vault and be new in
another. The owner can override any verdict at the outline gate.

### 8.2 Merging

A **merge** draft starts from the file as it is on disk now, including the owner's edits.
The writer returns an updated body; code replaces only the body, leaves the frontmatter, the
`Up:` line and the link lists in place, and adds new parents, subtopics, aliases, related
links and references without removing anything.

### 8.3 Parent notes and placement

A topic can sit under a **parent note**, a short overview that groups related topics, such as *Database
internals* above *Buffer pool management* and *Write-ahead logging*. A parent is an ordinary note: it has
`parents` and children like any other and has no marker, flag or folder of its own. Any existing note
that has children can serve as one. A topic's notes live in a folder named after its top note; a new
parent starts a folder named after itself and the notes beneath it share that folder, while a topic
placed under an existing parent starts its own folder, because the existing parent's folder belongs to
its other topics.

After the outline is drafted, the **placer** receives the domain, the topic and its subtopics, the
existing notes that have children (as a tree with their summaries) and the existing top-level notes. It
returns a chain of parents above the topic, outermost first, and the existing notes to attach beside it.
The rules are enforced in code, and a violation becomes a specific re-ask:

- at most two levels, and zero or one are fine; an existing parent must be copied exactly from the list,
  and an existing parent can sit only under another existing parent that really is its parent;
- a new parent needs a title and a one-line summary and may not duplicate a note that is already in the
  vault;
- attached notes must come from the list, must not be one of the parents, and need a parent to go under
  (at most eight).

The result is stored on the outline per domain (`ancestors`, `adopt`), shown at the outline gate, and
editable there. Edits go through the same checks, including a re-check when the owner approves. A re-plan
keeps the owner's placement.

When drafts are built, the chain is expanded into extra nodes above the topic's top note. A **new** parent
is written as a short orientation with no research, because it has no source passages (the node is marked
`placed`). An **existing** parent, and each attached note, is a `reuse` node: it supplies its title and is
never rewritten. Committing then does only single-line work on existing files:

- the topic's top note is added to an existing parent's `## Subtopics` by one inserted line (as is each
  attached note);
- each attached note gets the parent added to its `parents` and its `Up:` line, and nothing else changes in it.

Both are listed at the draft gate before anything is approved. A new parent's own `## Subtopics` is
generated like any parent note's, and includes the attached notes. Later topics see it as an existing note
and attach to it the same way. A note that already has children is not offered as a merge target in the
overlap check, since it groups other notes.

### 8.4 Related links

The hierarchy carries the structure, so `## Related` is kept sparse and holds cross-links only.

**What the linker may offer.** The hierarchy already links a note to its ancestors and descendants, so
they are never offered. The code builds that family at any depth from the `parents` of the vault's indexed
notes, the job's own drafts and the notes being attached, and removes it from the candidates. Siblings,
cousins and notes in other branches stay eligible.

**What the linker may choose.** A link needs one of two reasons, recorded as `kind`: a *prerequisite* (the
reader must understand the other note first) or a *contrast* (its direct alternative or counterpart).
Sharing a topic or a parent is not a reason, because notes under one parent are one click apart through
it. The prompt says to leave a link out when in doubt and that none is the expected answer for most notes.
There is no numeric cap: a parent may have a hundred children and a note several parents. Each entry is
written as `Prerequisite: ...` or `Contrast: ...`. Code drops any title that was not offered and any entry
whose reason is empty or only says the notes are "related".

**After the linker.** Two rules run in code (`related_links.py`):

- *Link a cluster once.* When two or more chosen notes share a parent outside this note's own family, the
  note links that parent once instead of each of them.
- *One side per pair.* When two drafts in a job list each other, the pair stays on one note: the one whose
  entry is a prerequisite, else the alphabetically first. A note a new one partly overlaps is not edited
  at commit; Obsidian's backlinks show the other direction.

**Notes written earlier.** The link-tidy service reads the files on disk. Its rule-based plan
(`GET /notes/tidy-preview`) lists the entries that point at an ancestor or descendant and the second copy
of each mutual pair. An optional review (`POST /notes/tidy-review`) asks the `link_pruner` agent, one call
per note, which of the remaining entries are a prerequisite or a contrast; the rest are proposed for
removal. The owner sees the proposal before anything changes. `POST /notes/tidy` then removes the
rule-based entries and the reviewed ones the owner confirmed, only the `## Related` lines, under the vault
lock. It leaves `user_modified` alone and removes the heading when the section ends up empty.

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

## 12. Study chat

The owner studies by asking questions in a chat: "explain Raft", "what do I need before
consistent hashing?", or a scenario such as "how does Gmail's sign-up check usernames?",
where the answer lives in notes the question never names (Bloom filters). Chat is
retrieval-augmented generation without vectors. Agents reason over the vault map to find
the right notes, read them, and answer from them with citations.

### 12.1 Agents and the runtime

| Agent | Thinks about | Acts by returning |
|---|---|---|
| `chat_orchestrator` | What is being asked, which subagent to send, whether the evidence is enough | `delegate_navigator`, `delegate_readers`, `recall`, `ask_owner` or `answer` |
| `navigator` | Which notes in which clusters could hold the answer | `search_vault` or `finish` (notes to read, each with a reason, plus concepts the vaults do not cover) |
| `reader` | Which passages of the given notes matter for the goal | `read_note` or `finish` (verbatim excerpts with note and heading) |
| `answer_verifier` | Whether every claim in a draft answer is supported and the question is answered | `pass`, or `revise` with specific issues |
| `chat_summarizer` | How to fold older messages into the running summary | the new summary |

Each agent is one `claude -p` call through the existing engine, with its own model and
effort in Settings, and each reply is validated by `run_structured` (§6.2). The **chat
runtime** (`services/chat_runtime.py`) is the agents' hands. It calls an agent, carries
out the action or tool call the agent returned, gives the result back as an observation,
and calls the agent again. It decides nothing about relevance or routing. Subagents never
talk to each other: every handover goes through the orchestrator, which may drop picks,
add its own, re-send the navigator, or skip reading entirely.

### 12.2 A turn

```
owner message ─▶ ORCHESTRATOR ◀──────────────────── observations ────────────────────┐
                   │ action                                                           │
                   ├─ delegate_navigator(task) ─▶ NAVIGATOR (map in its prompt) ──────┤
                   ├─ delegate_readers(tasks)  ─▶ READER ×1–4 in parallel             │
                   │                               (note text in its prompt) ─────────┤
                   ├─ recall(refs)             ─▶ older evidence text ────────────────┤
                   ├─ ask_owner(question)      ─▶ the owner (end of turn)             │
                   └─ answer(draft)            ─▶ VERIFIER ─ pass ─▶ the owner         │
                                                     └ revise(issues) ────────────────┘
```

A typical scenario question takes six calls: orchestrator, navigator, orchestrator,
reader, orchestrator (draft), verifier. A follow-up answered from evidence the chat
already holds takes two calls: orchestrator (draft) and verifier.

### 12.3 Actions and tools

Agents have no built-in tools. An agent acts by returning one JSON object naming an
action or tool and its arguments. The runtime validates the object against the agent's
schema (a discriminated union on `action`), runs the action, and appends
`{action, arguments, result}` to the agent's log, which is resent on the next call
because calls do not keep sessions. Each agent run ends when the agent returns its
final action (`answer`, `ask_owner`, `finish`, or the verifier's verdict) or reaches its
step limit.

| Agent | Action | What the runtime does |
|---|---|---|
| orchestrator | `delegate_navigator(task)` | Runs a navigator with a task that stands on its own (pronouns resolved from the conversation) |
| orchestrator | `delegate_readers([{notes, goal}])` | Runs one reader per task, at most four, in parallel |
| orchestrator | `recall(refs)` | Puts the full text of earlier evidence back into the orchestrator's prompt |
| orchestrator | `ask_owner(question)` | Ends the turn with a clarifying question |
| orchestrator | `answer(text, gaps)` | Sends the draft to the verifier |
| navigator | `search_vault(terms)` | Scans the chat's vault files for the terms, case-insensitively, and returns up to 20 hits (domain, title, heading, a 300-character snippet) |
| navigator | `finish(picks, missing)` | Returns at most 12 notes `{domain, title, reason}` and the concepts no note covers |
| reader | `read_note(domain, title)` | Adds one more note's text, for a `[[link]]` worth following |
| reader | `finish(passages)` | Returns `{domain, title, heading, excerpt}` items; each becomes evidence |

Code enforces these rules, and a violation becomes a re-ask through `run_structured`,
like the placer's checks (§8.3):

- a navigator pick must be a note in the map, matched by title key within its domain;
- a reader excerpt must occur in that note's text, compared after collapsing whitespace,
  so evidence is quoted, never paraphrased;
- every `[E#]` reference in a draft answer must be evidence the chat holds.

### 12.4 The vault map and reading notes

**The map** is built from `notes` and `note_links` when the navigator is called, so it is
never stale and is not stored. For each domain of the chat it lists every note once, as a
tree under its first parent, with its summary and its related titles:

```
# system-design
- Probabilistic Data Structures: space-efficient approximate structures
  - Bloom Filter: set membership with false positives, never false negatives  [related: Cuckoo Filter, Hashing]
- Caching Strategies: …
```

A note with several parents also shows `(also under X)`. A note the owner wrote in
Obsidian has no summary, so it appears by title only. The navigator sees the whole map
at once, so it usually finishes in one step. Exploring a very large map in parts is not
built yet.

**Reading** never goes through an agent's own tools. A reader is given notes as
`(domain, title)`. The runtime looks each one up in the index, resolves its path with
`resolve_in_vault`, reads the file read-only, and drops the frontmatter. The text is
always the file as it is now, including the owner's latest edits. A note that is missing
from the index or from disk becomes an observation ("not found; a rescan may help"), not
a failure. `search_vault` scans the `.md` files of the chat's vaults directly and skips
dot-folders, as reconcile does.

### 12.5 Conversation memory

Memory lives within one chat only; chats never share anything. On each turn the
orchestrator receives:

- the chat's running summary, which covers everything older than the recent messages;
- the last six messages, word for word;
- the evidence the chat holds: the full text of the most recent excerpts up to 40,000
  characters, and older ones by reference, title and heading only, which `recall` can
  bring back;
- the new message and the log of this turn's actions.

Subagents never see the conversation. The orchestrator writes each task so it stands on
its own. After an answer is stored, if more than twelve messages are not covered by the
summary, the summarizer folds all but the last six into it. This happens after the owner
already has the answer, so it never delays one.

### 12.6 Running a turn

A turn is interactive and short-lived, so it runs as a background task in the backend
process, not as a Temporal workflow. `POST /chats/{id}/messages` stores the owner's
message and a `pending` assistant message, starts the task, and returns at once. The
frontend polls the chat while a message is pending and shows its `step` ("Thinking",
"Finding notes", "Reading notes", "Checking the answer"). A chat has at most one pending
turn; another message while one is pending is refused with 409.

The task catches every error at its top level. It logs the traceback, marks the message
`failed` with a plain-language reason, and leaves the backend serving. At startup, any
message still `pending` was interrupted by a restart and is marked `failed` ("interrupted
by a restart; ask again"). The cost of every agent call in a turn is summed onto the
assistant message.

### 12.7 Verification loop

Every draft goes to the verifier; the orchestrator cannot skip it. The verifier receives
the question, the draft and the evidence the draft cites. It checks that:

- each claim drawn from the notes is supported by the excerpt it cites;
- material that is not from the notes is labelled as general knowledge;
- the question is fully answered.

On `revise`, the issues return to the orchestrator as an observation, and the orchestrator
decides the fix: fetch more, or rewrite. There are at most two revise rounds, ending early
when the same issues come back. A draft that still fails reaches the owner with the
verifier's flags shown, never hidden. An answer shows its citations as note title and
section, and lists its gaps (concepts the vaults do not cover) so the owner can ingest
them.

### 12.8 Limits and safety

- **Step limits:** the orchestrator has 8 actions per turn; a navigator or reader has 3
  steps; the verifier has 2 revise rounds; each turn has a spending cap of $1.00. These
  values sit in the roles' `params` and can be edited in Settings. When a limit is
  reached, the orchestrator gets one final call in which only `answer` and `ask_owner`
  are allowed.
- **Size limits:** a message is at most 8,000 characters; one reader task is given at
  most 120,000 characters of note text, and a larger task is refused with an observation
  asking the orchestrator to split it.
- **Note text is untrusted.** Notes contain material researched from the web. Every chat
  prompt marks note text and excerpts as data, not instructions. No chat agent has any
  built-in tool, so a chat agent can read the owner's notes but has no way to send
  anything out, and the agents that browse the web never see chat data.
- **Read-only.** Chat never writes a vault file or an index row.
- **Logging** records turn start and end, each action with its agent, counts and
  duration, and the turn's cost. Questions, answers and note text are never logged.

Not built yet: a SQL agent for questions about the notes as data ("what did I add last
week?"), vector search, and exploring a large map in parts.

## 13. HTTP API

All routes are under `/api`.

| Route | Purpose |
|---|---|
| `GET /health` | Liveness |
| `GET /domains`, `POST /domains`, `PUT /domains/{slug}`, `DELETE /domains/{slug}` | Domain management |
| `POST /domains/draft-profile` | Draft a profile with Claude; saves nothing |
| `GET /agent-configs`, `PUT /agent-configs/{role}` | Per-role model, effort and budgets; a model outside the allowed list is refused |
| `GET /agent-configs/models` | The models a role can be set to |
| `POST /jobs`, `GET /jobs`, `GET /jobs/{id}` | Submit a job, list jobs, one job with its steps |
| `GET /jobs/{id}/outline`, `POST /jobs/{id}/outline-decision` | The outline gate; the view includes, per domain, the parent notes and top-level notes the topic can be placed with |
| `GET /jobs/{id}/drafts`, `POST /jobs/{id}/draft-decision` | The draft gate |
| `POST /jobs/{id}/cancel` | Cancel a job |
| `GET /notes?domain=&q=` | List and search notes |
| `POST /notes/delete-preview`, `POST /notes/delete` | Preview and perform a delete |
| `GET /notes/tidy-preview?domain=`, `POST /notes/tidy-review?domain=`, `POST /notes/tidy` | Preview, optionally review with the link pruner, and remove Related links that are redundant |
| `POST /notes/reconcile` | Rescan the vaults |
| `GET /chats`, `POST /chats`, `GET /chats/{id}`, `DELETE /chats/{id}` | List, start (with the domains to read), open with its messages and citations, and delete a chat |
| `POST /chats/{id}/messages` | Ask a question; returns the pending assistant message at once (409 while a turn is pending, 413 over 8,000 characters) |

Submitting a job records it and asks Temporal to start its workflow, then returns; no work
runs inside a request. Asking in a chat likewise stores the message, starts a background task
(§12.6) and returns. Errors use specific statuses with a readable `detail`: 400 invalid
input, 404 not found, 409 conflict or wrong state, 413 input too large, 422 malformed payload,
502 agent failure, 503 workflow could not start, and 500 for anything unexpected.

## 14. Frontend

React with TypeScript, Vite and Tailwind, with TanStack Query for server state and no router
(five top-level views held in state; the two approval screens open from inside Jobs).

- `design/` holds the tokens (a cool grey-green neutral palette and one verdigris accent, with
  light and dark values that follow the OS) and the primitives (button, chip, card, form fields,
  empty state, spinner). Status colours are functional only.
- `shell/` holds the sidebar, with the live "needs you" count, and the page frame with its sticky
  action bar.
- `features/` has one folder per screen. Pure logic (outline edits, status mapping, decision
  building, markdown preparation) lives in plain modules beside the components.
- The job list polls every three seconds and the sidebar count shares that one query.
- `features/chat/` holds the chat screen: the list of chats, the conversation with each
  answer's citations, gaps and verifier flags, and the composer. It polls the open chat every
  1.5 seconds while an answer is pending and shows the current step.
- Fonts are self-hosted: Instrument Sans for the interface, Newsreader for rendered note
  previews, JetBrains Mono for ids and paths.

## 15. Error handling and logging

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

## 16. Security boundaries

- The backend binds to `127.0.0.1`, has no authentication, and accepts only the configured
  frontend origin. Temporal and Postgres are published on `127.0.0.1` only.
- Agents have no file tools, and tools are an explicit allow-list per call. Only three roles may
  browse, and what they read is treated as untrusted data.
- Chat agents have no built-in tools at all. The chat runtime reads notes for them, read-only,
  by `(domain, title)` through the index and `resolve_in_vault`, never by a path an agent
  supplies. No agent both reads chat data and browses the web (§12.8).
- Every write path is checked to resolve inside its vault, after following symlinks.
- Cited URLs are verified, and the liveness check refuses local and private addresses.
- Vault contents and `VAULTS_ROOT` are never committed, and the application never runs git.

## 17. Limits and defaults

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
| Parent levels above a topic | 0 to 2 |
| Existing notes attached under a parent at once | 8 |
| References per note | at most 8 |
| Note title length | 120 characters |
| Chat message | 8,000 characters |
| Chat orchestrator actions per turn | 8, then one final call that must answer |
| Navigator and reader steps per run | 3 |
| Readers in parallel per delegation | 4 |
| Note text given to one reader | 120,000 characters |
| Notes a navigator may pick | 12 |
| `search_vault` hits | 20 |
| Chat verifier revise rounds | 2 |
| Spending cap per chat turn | $1.00 |
| Recent chat messages sent word for word | 6; the summary is refreshed beyond 12 |
| Evidence text in the orchestrator's prompt | 40,000 characters |

## 18. Engineering standards

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
- **Logging as described in §15**, with meaningful lines and not per-function chatter.
- **Files live in the folder their responsibility maps to.** No catch-all `utils` module.
- **Naming says what a thing is**; no single-letter names outside a tight local scope.
- **Workflow code stays deterministic.** It routes on results; anything with I/O or randomness is an
  activity, and every activity is safe to re-run.

## 19. Verifying a change

The repository has no automated test suite. A change is checked by running it:

- Backend: start the services and the backend, then exercise the affected route or workflow with
  `curl` or the UI, including at least one provoked failure that should produce a clean error and a
  log line. The Temporal UI at `http://127.0.0.1:8233` shows workflow progress.
- Pure modules (`app/vault`, outline validation, wikilinks) can be exercised from a short Python
  snippet against temporary folders.
- Frontend: `npm run build` and `npm run lint` must pass, and the affected screen is checked in a
  browser in both themes.
- Anything that calls agents costs money; prefer a small topic and a trimmed outline.
