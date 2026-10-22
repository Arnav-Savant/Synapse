# Synapse: requirements

What Synapse must do. [`ARCHITECTURE.md`](ARCHITECTURE.md) describes how each
requirement is met.

## 1. Purpose

Synapse is a personal, single-user, local-first tool for studying technical
subjects. It turns raw input, either pasted material or a bare topic name, into
a tree of well-structured notes and writes them into Obsidian vaults, one vault
per domain. Obsidian is the viewer and editor; Synapse is the ingestion and
authoring engine.

## 2. Scope

**In scope**
- Turning pasted content or a topic name into linked notes in the right vault(s).
- Building a dense, deduplicated graph: overlapping material is merged or linked.
- Keeping the owner in control through an outline approval and a draft approval.
- Running several jobs asynchronously, surviving restarts, and showing progress.
- Per-agent model and effort configuration, and owner-defined domains.

**Out of scope**
- Viewing or editing notes, graph visualisation, or chat (Obsidian does these).
- Any use of git by the application. Vault contents are never committed.
- Version history of notes or drafts beyond the current draft.
- LLM providers other than Claude Code.
- Authentication, multiple users, or hosting.
- Embeddings or vector search.

## 3. Functional requirements

### FR1: Domains
- FR1.1 A domain has a name, a one-line purpose, a vault folder and a profile
  (objective, ordered detailed-note sections, in-scope rules, mention-only rules,
  style).
- FR1.2 The owner can add, edit and delete domains in the app. Three starter
  domains (System Design, DSA, AI) exist on first run.
- FR1.3 Saving a domain creates its vault folder under `VAULTS_ROOT`. An existing
  folder is reused. Renaming a domain does not move its folder.
- FR1.4 Deleting a domain removes its settings and its index rows and never
  touches vault files. It is refused while a job for that domain is active.
- FR1.5 A job uses the profile as it was when the job started; later edits to a
  profile do not affect a job in progress.
- FR1.6 An optional "Draft with Claude" action fills a profile from the form
  answers or a pasted study prompt, without saving it.

### FR2: Ingest
- FR2.1 The owner can submit pasted content or a topic name, with a domain chosen
  or auto-detected.
- FR2.2 Empty or whitespace-only input is rejected. Input over 200,000 characters
  is rejected with an explanatory message and is never silently truncated.
- FR2.3 Auto-detect may return more than one domain, with a confidence. A
  confidence below 0.7 is flagged at the outline step.
- FR2.4 Submitting returns immediately; all work happens in the background.

### FR3: Outline
- FR3.1 For a topic, a planner agent does a light web scan and proposes an outline
  tree. For pasted content, a structurer agent identifies the topic and splits the
  content into the same tree, giving each node the passages that belong to it.
- FR3.2 An outline has exactly one root, no cycles, unique titles, at most 40
  nodes and at most five levels. A malformed outline is re-requested from the
  agent, and the job fails with a readable reason if it stays malformed.
- FR3.3 Each node is compared with the notes already in each target vault and
  given a verdict per domain: same subject (merge), partial overlap (new note
  that links to the existing one), or distinct.
- FR3.4 The owner approves the outline before any research or writing. They can
  untick nodes (with their subtrees), add subtopics, switch a node's domains,
  override overlap verdicts, or ask for a new plan with written feedback, as many
  times as they like.
- FR3.5 An outline edit that makes the tree invalid is refused with the reason
  and the job stays at this step.
- FR3.6 Each topic is placed, per domain, under zero, one or two hub levels. A hub is a
  short overview note that groups related topics. A placement agent proposes the fewest
  levels that make sense and reuses an existing hub whenever one fits; it proposes a new hub
  only when none fits and the area would hold several topics. More than two levels are never
  allowed.
- FR3.7 The proposed hub path is shown at the outline approval, marked as existing or new, and
  the owner can pick a different hub, rename or describe a new one, add or remove a level, or
  leave the topic with no hub.
- FR3.8 Existing top-level notes that belong beside the topic can be attached under the innermost
  hub. Attaching changes only a note's parent link, never its text.
- FR3.9 A new hub is written like an overview note (short, no research). An existing hub is not
  rewritten: the new topic is added to its Subtopics list by one inserted line.

### FR4: Research and writing
- FR4.1 For a topic, each leaf is researched on the web into a dossier of facts
  with sources. Pasted content is not researched; the pasted text is the source.
- FR4.2 Only sources the agent actually retrieved and that are still reachable
  are kept as references.
- FR4.3 Notes are written leaves first, then parents, then the top note, so each
  parent summarises what was actually written. Parent notes compare their
  children and do not repeat them.
- FR4.4 A leaf note follows the domain profile's sections and scope rules.
  Adjacent technologies are mentioned in a line at most and never get their own
  notes.
- FR4.5 A topic in several domains is written once per domain from one shared
  outline and one shared core statement, each through that domain's lens. The
  copies share a topic id and are never linked to each other.
- FR4.6 Agents return structured output and never write files.

### FR5: Quality checking
- FR5.1 Every draft goes through deterministic checks (valid header, links that
  resolve, no empty sections, size limit, safe link targets) and a reviewer agent
  that judges scope creep, missing depth and unsupported claims.
- FR5.2 Drafts that fail are rewritten, only the failing ones, with the issues
  attached, up to two rounds, stopping early when the same issues recur.
  Whatever still fails goes to the owner with its flags and is never discarded.

### FR6: Draft review and commit
- FR6.1 The owner reviews drafts as a tree grouped by vault, with a rendered
  preview, the raw Markdown, validator flags, and, for merges, a diff against the
  file on disk now.
- FR6.2 The owner can approve a chosen set of drafts, or give feedback at the
  scope of one section, one note or the whole topic, optionally asking for new
  research. Feedback rewrites only what was named and returns to review.
- FR6.3 Approving writes the chosen drafts and discards the others. Nothing
  reaches a vault before approval.
- FR6.4 A merge is written only if the target file is unchanged since the draft
  was made. Otherwise nothing is written, and the merge is rebuilt from the current
  file and shown again.
- FR6.5 A new note is refused if its title already exists in the vault, or a
  file already exists at its path. A refused draft stays in review with the reason.
- FR6.6 Committing is repeatable: running it again after an interruption completes
  the work without duplicating or overwriting anything.
- FR6.7 Approving a note that partly overlaps an existing one adds a back-link
  line to that note, changing nothing else in it.

### FR7: Note format
- FR7.1 One Markdown file per note, named after its title, in one folder per
  top-level topic. Titles are unique per vault, compared case-insensitively.
- FR7.2 A note has frontmatter (`synapse_id`, `topic_id` for cross-domain copies,
  `domain`, `parents`, `aliases`, `summary`, `job_id`, `created`), an `Up:` line,
  a body, and `Subtopics`, `Related` and `References` lists. Links are Obsidian
  wikilinks.
- FR7.3 No note is ever linked across vaults.
- FR7.5 A hub carries `hub: true` in its frontmatter and lives in the vault's `Hubs` folder. An owner can
  make any note a hub by adding `hub: true`.
- FR7.4 Every file path is verified to be inside its domain's vault before it is
  written.

### FR8: Jobs
- FR8.1 Every job shows its status, current step, domains, cost and, if it
  stopped, a plain-language reason.
- FR8.2 At most two jobs execute at once; further jobs wait as queued. A job
  waiting for the owner does not occupy a slot.
- FR8.3 After a backend restart, every job still shows where it is and continues.
  A job whose workflow no longer exists is marked failed.
- FR8.4 The owner can cancel any active job.

### FR9: Notes management
- FR9.1 The owner can list and search the notes in each vault.
- FR9.2 Deleting a note, a whole topic, one vault's copy of a note, or everything
  one job created shows a preview first and requires confirmation. A note the
  owner edited in Obsidian needs an extra confirmation.
- FR9.3 Deleting removes the files and index rows, strips links to them from other
  notes (including aliased, heading and table-row links, and leaving code untouched)
  so no ghost nodes remain, and re-attaches each child to the deleted note's own
  parents, or makes it top-level.
- FR9.4 A rescan, run on demand and at startup, keeps the index in line with the
  vaults: a deleted file's links are cleaned up, a new file is given an id, an
  edited file is marked as edited by the owner, a moved file is followed.
- FR9.5 Synapse never overwrites a note the owner edited. Any regeneration of it
  is a merge against the file on disk.

### FR10: Settings
- FR10.1 Each of the eleven agent roles has its own model and effort, editable in the
  app. The model is chosen from the list Claude Code accepts (pinned versions and
  "latest" aliases); any other value is refused. The researcher and planner also expose their web-search budgets.
- FR10.2 Domain management as in FR1.

## 4. Non-functional requirements

- **NFR1 Local and private.** The backend listens on `127.0.0.1` only and has no
  authentication. Nothing is sent anywhere except the agents' own requests to
  Claude and the web pages they read.
- **NFR2 No API key.** Agents run through the `claude` CLI under the owner's
  subscription.
- **NFR3 Untrusted web content.** Text an agent reads from the web is treated as
  data. Only the planner, researcher and reference finder have web tools, and no
  agent has file tools.
- **NFR4 Durable.** Work survives crashes and restarts. Infrastructure failures
  are retried with backoff; shape errors in agent output are re-asked at most twice.
- **NFR5 Files are the truth.** The notes on disk are the source of truth. The
  database holds drafts, jobs, settings and a note index that can be rebuilt from
  the vaults at any time.
- **NFR6 Safe writes.** Files are written atomically, so a crash never leaves a
  half-written note, and under a per-vault lock so writers never interleave.
- **NFR7 Observable.** Each significant event is logged as a readable sentence with
  the ids needed to trace it. Errors reach the owner as specific messages.
- **NFR8 Never crash on a request.** After startup, no unexpected error may stop
  the backend; it is logged with its traceback and the request or job fails alone.
- **NFR9 Cost transparency.** Cost is recorded per step and totalled per job.
- **NFR10 Responsive UI.** Light and dark themes follow the operating system, every
  screen has loading, empty and error states, and the layout works down to phone width.
