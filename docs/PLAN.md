# Synapse — Phased Development Plan

Prerequisite reading: `REQUIREMENTS.md`, `ARCHITECTURE.md`. Each phase below
produces a working, demonstrable increment. Do not start a phase whose
dependencies aren't done; do not implement ahead of the current phase.

Environment already verified (2026-09-22): Python 3.12.3, Node v22.22.3,
npm 10.9.8, poetry available, Claude Code CLI v2.1.278 installed and logged
in as the local user (`~/.claude/.credentials.json` present). Repo currently
contains only `README.md`.

---

## Phase 0 — Scaffolding

**Objective:** both repos exist with a runnable, empty skeleton. Nothing
functional yet.

**Scope:**
- Create the knowledge repo at `KNOWLEDGE_REPO_PATH` (default
  `~/Personal/Arnav/synapse-knowledge`), `git init`, directory skeleton per
  `ARCHITECTURE.md` §3 (`source/`, `knowledge/`, `assets/`, `.synapse/`),
  empty `CLAUDE.md` placeholder (filled in Phase 2), `.gitignore`
  (`.synapse/logs/`), first commit.
- Backend skeleton: `backend/` with FastAPI app, `app/config.py` reading
  `KNOWLEDGE_REPO_PATH` from `.env`, a single `GET /api/health` route,
  Poetry (or `requirements.txt`) dependency setup, `uvicorn` runs.
- Frontend skeleton: `frontend/` via Vite React-TS template, Tailwind
  configured, one placeholder route that calls `/api/health` and displays
  the result (proves the frontend↔backend wire works).
- Root `.env.example` documenting `KNOWLEDGE_REPO_PATH`.

**Components affected:** new — `backend/`, `frontend/`, knowledge repo.

**Acceptance criteria:**
- `uvicorn app.main:app --reload` serves `/api/health` → `200 OK`.
- `npm run dev` serves a page that fetches `/api/health` and renders its
  response.
- Knowledge repo exists on disk with the documented structure and is its
  own Git repo with one commit.

**Tests:** one backend smoke test (`GET /api/health` → 200). No frontend
tests yet (nothing to test).

**Dependencies:** none.

---

## Phase 1 — Filesystem foundations: sources and knowledge, read + create

**Objective:** the app can read the real filesystem state of the knowledge
repo and let the user create source material, with no Claude Code
involvement yet.

**Scope:**
- Backend `fs/paths.py`: path resolution + traversal guards confined to
  `KNOWLEDGE_REPO_PATH`.
- Backend `fs/source_repo.py`: list source files (recursively, with
  category from path), create/update a text source file at
  `source/<category>/<name>.md`, upload a binary file to
  `source/_uploads/`.
- Backend `fs/knowledge_repo.py`: list `knowledge/*.md`, read one by slug.
- API: `GET /api/sources`, `POST /api/sources`, `POST /api/sources/upload`,
  `GET /api/knowledge`, `GET /api/knowledge/{slug}`.
- Frontend: a source list/create view (form: category, filename, paste
  content → save), and a plain knowledge-file list + raw-markdown viewer
  (no graph, no rendering polish yet — just prove read/write works).
- **Manually author 2–3 seed concept files** in `knowledge/` (e.g. a trivial
  `test-concept.md` with valid frontmatter per the schema) to have
  something real to list/view before Claude Code produces anything.

**Components affected:** `backend/app/fs/*`, `backend/app/api/sources.py`,
`backend/app/api/knowledge.py` (read-only for now), frontend source +
knowledge list views.

**Acceptance criteria:**
- Creating a source file via the UI produces the file on disk under
  `source/<category>/`, correctly named and content-matching.
- The knowledge list shows the seed files; opening one shows its raw
  Markdown.
- Path-traversal attempts (e.g. category `../../etc`) are rejected by the
  API with a 4xx, not written anywhere.

**Tests:** pytest for `paths.py` (traversal rejection), `source_repo.py`
(create/list round-trip against a temp dir fixture), `knowledge_repo.py`
(list/read against the fixture repo).

**Dependencies:** Phase 0.

---

## Phase 2 — Claude Code knowledge-processing engine (core)

**Objective:** the central workflow — new source material becomes
deduplicated, related knowledge files, with no API key required.

**Scope:**
- Write the real `CLAUDE.md` in the knowledge repo (dedup contract,
  frontmatter schema, relationship taxonomy, "never touch `source/`",
  preserve-human-edits note — content specified in `ARCHITECTURE.md` §5.3).
- `claude_runner/runner.py`: async subprocess wrapper implementing the
  invocation in `ARCHITECTURE.md` §5.2. **Spike first**: run the exact
  command by hand against a disposable test knowledge repo to confirm
  `--permission-mode acceptEdits --permission-prompts none` behaves as
  expected (no hangs, edits actually land, JSON output shape matches what's
  assumed) before wiring it into the backend. Record findings as comments in
  `runner.py` if any flag behaved differently than documented.
- `claude_runner/git_guard.py`: clean-tree precheck, post-run diff,
  revert-if-`source/`-touched, commit-if-`knowledge/`-only-touched.
- `jobs/queue.py` + `jobs/store.py`: single-worker async queue, job records
  in `.synapse/jobs/*.json` (states: queued/running/succeeded/failed),
  reconcile orphaned "running" jobs to "failed" on backend startup.
- API: `POST /api/jobs/process` (body: source file path) → 202 + job id;
  `GET /api/jobs/{id}`; `GET /api/jobs` (recent history).
- Frontend: "Process" action on a source file; job status indicator that
  polls until terminal state and shows a summary (files changed) or error.

**Components affected:** `backend/app/claude_runner/*`,
`backend/app/jobs/*`, `backend/app/api/jobs.py`, knowledge repo `CLAUDE.md`,
frontend source view + new jobs UI.

**Acceptance criteria (functional):**
- Submitting a real ChatGPT/Claude conversation export (the user's own
  material) as a source file and triggering processing produces sensible
  `knowledge/*.md` files with correct frontmatter and at least one
  meaningful relationship.
- Submitting a second source file that discusses a concept already created
  by the first run **updates** the existing concept file (verified by file
  count not growing and `sources:`/content reflecting both inputs) instead
  of creating a near-duplicate — this is a **manual review** acceptance
  criterion using real content, not just a fixture assertion (see
  `ARCHITECTURE.md` §12).
- Deliberately crafted adversarial content that asks Claude Code (in the
  source text) to "also delete everything in source/" does not result in
  any `source/` change (git guard catches/reverts it if the tool-restriction
  somehow didn't).
- Backend restart while a job is "running" leaves it recorded as "failed",
  not stuck.

**Tests:** unit tests for `git_guard.py` against a throwaway temp Git repo
(simulate a diff touching `source/`, assert revert; simulate a diff touching
only `knowledge/`, assert commit). `runner.py` unit-tested with the
subprocess call mocked. One opt-in real-invocation smoke test (not in
default CI run) per `ARCHITECTURE.md` §12.

**Dependencies:** Phase 1.

---

## Phase 3 — Graph derivation

**Objective:** turn the canonical Markdown into the derived graph JSON.

**Scope:**
- `knowledge/frontmatter.py`: parse/write YAML frontmatter + body.
- `knowledge/wikilinks.py`: extract `[[...]]` links from body text.
- `knowledge/graph.py`: build `{nodes, edges}` from all `knowledge/*.md` —
  nodes carry `id, title, domains, status`; edges carry `source, target,
  type`; frontmatter relationships + deduplicated implicit wikilink edges
  per `ARCHITECTURE.md` §4.1; derive/attach inverse relationship labels for
  display without storing them.
- Validation pass: detect relationships whose `target` doesn't correspond to
  any existing concept file; surface as warnings in the API response rather
  than failing.
- `GET /api/graph` with an in-memory cache invalidated on job completion
  (Phase 2) and on knowledge-file save (Phase 5).

**Components affected:** `backend/app/knowledge/*`, `backend/app/api/graph.py`.

**Acceptance criteria:**
- `GET /api/graph` against the seed files (Phase 1) plus anything Phase 2
  produced returns correct nodes/edges, including an edge derived purely
  from a `[[wikilink]]` not present in frontmatter.
- A relationship pointing at a nonexistent slug appears as a `warnings`
  entry, not a crash.
- Adding a new concept file (manually) and re-requesting the graph reflects
  it without a backend restart.

**Tests:** pytest fixture knowledge repo with a handful of concept files
covering: multi-parent `subtopic-of`, a `contrasts-with` symmetric edge, a
wikilink-only implicit edge, and one broken relationship target. Assert
exact node/edge output and the warning.

**Dependencies:** Phase 1 (Phase 2 not strictly required to build this, but
Phase 2's real output is what makes the acceptance review meaningful).

---

## Phase 4 — Graph visualization and navigation (frontend)

**Objective:** the graph becomes the primary navigation surface.

**Scope:**
- Integrate Cytoscape.js (`react-cytoscapejs`) + `fcose`/`cose-bilkent`
  layout.
- Render `/api/graph` output; click-to-select a node.
- Search box (fuzzy match title/aliases) that highlights/centers a match.
- Domain/status filter controls (view-level filter, not a separate data
  fetch).
- Focus/ego view: selecting a node offers a "neighborhood" view (1–2 hop
  filter) with a way back to the global view.
- Current-selection breadcrumb/indicator.

**Components affected:** `frontend/src/components/graph/*`, a new graph
route as the app's default/home view.

**Acceptance criteria:**
- Load a synthetic fixture graph of 150+ nodes (generated for this test,
  not hand-written) and confirm: initial layout renders without freezing
  the tab, search finds and centers a node, applying a domain filter visibly
  reduces node count, focus view on a node shows only its neighborhood,
  "back to global" restores the full graph. This is a manual browser
  verification per the project's testing approach for interaction feel.
- Selecting a node fires a selection event (wired to nothing yet but
  observable) — becomes real navigation in Phase 5.

**Tests:** Vitest/RTL tests for the search/filter logic (pure functions
over a fixture node/edge list) and for the focus-view neighborhood
computation. No automated test for layout rendering itself.

**Dependencies:** Phase 3.

---

## Phase 5 — Knowledge viewer and editor

**Objective:** selecting a graph node shows real, editable, navigable
synthesized knowledge — closing the loop from graph → content → graph.

**Scope:**
- Markdown viewer (`react-markdown`) rendering a concept's body, with
  `[[wikilink]]` rendered as an in-app link that selects/opens that concept
  (updates graph focus too).
- Edit mode: textarea/markdown editor, `PUT /api/knowledge/{slug}` writes
  back frontmatter + body, preserving fields the editor doesn't touch.
- "View sources" affordance: list the concept's `sources:` files, open one
  read-only (clearly labeled as raw material, distinct styling from
  generated knowledge per FR4.1).
- Wire graph node selection (Phase 4) to actually open this viewer.
- Graph cache invalidation on save (ties into Phase 3's cache).

**Components affected:** `backend/app/api/knowledge.py` (add `PUT`),
`frontend/src/components/knowledge/*`, `frontend/src/components/source/*`
(read-only raw viewer).

**Acceptance criteria:**
- Clicking a node in the graph opens its generated notes, not raw source.
- Clicking a `[[wikilink]]` inside those notes navigates to the linked
  concept in both the viewer and the graph selection.
- Editing and saving a concept's Markdown persists to disk and is reflected
  in a subsequent `GET`.
- Opening "sources" for a concept shows the original raw material,
  unmistakably labeled as raw/unedited.

**Tests:** backend test for `PUT /api/knowledge/{slug}` round-trip
(including frontmatter preservation). Frontend RTL test for wikilink
rendering→navigation.

**Dependencies:** Phase 3, Phase 4.

---

## Phase 6 — Chat interface (Claude Code engine, read-only)

**Objective:** a chat surface answering questions from the knowledge base,
with no API key required.

**Scope:**
- `claude_runner`: a read-only invocation variant (`--tools "Read,Glob,Grep"`,
  no `Write`/`Edit`), reusing the same subprocess mechanism.
- `POST /api/chat` (message, optional `concept` context) → runs the
  read-only invocation scoped to the knowledge repo, returns the response.
  Single "engine" for now (Claude Code); the provider-selection layer is
  Phase 7.
- Frontend chat panel: global chat, plus an "ask about this concept" entry
  point from the concept viewer that pre-fills context.

**Components affected:** `backend/app/claude_runner/*` (new prompt
template), `backend/app/api/chat.py`, `frontend/src/components/chat/*`.

**Acceptance criteria:**
- Asking a question answerable from existing `knowledge/*.md` content
  returns a relevant answer.
- After a chat interaction, `git status` in the knowledge repo shows no
  changes (proves the read-only restriction actually holds) — checked as
  part of this phase's test, not just assumed from the flag.
- Chat works with zero LLM provider configured (proves FR6.4 — chat doesn't
  secretly require a key).

**Tests:** backend test asserting the read-only invocation's `--tools`
argument never includes `Write`/`Edit`; a smoke test confirming no repo
diff after a chat call (against a temp repo).

**Dependencies:** Phase 2 (runner infra), Phase 5 (concept-context entry
point).

---

## Phase 7 — LLM provider configuration (LiteLLM)

**Objective:** optional external providers become configurable and usable
for chat, without touching the core processing workflow.

**Scope:**
- `.synapse/config.yaml` schema: list of provider/model entries, credential
  values referenced via `${ENV_VAR}` (never literal keys in the file).
- `llm/settings.py`: load config, resolve env vars, expose
  provider name + `configured: bool` (never the key itself).
- `llm/litellm_adapter.py`: `litellm.completion(...)` call given
  provider/model + assembled context (current concept content, or a small
  keyword-matched set of concepts — no embeddings, per the RAG non-goal).
- API: `GET /api/settings/llm` (list providers + status), `PUT
  /api/settings/llm/active` (select active engine/model for chat).
- `POST /api/chat` extended to route to the selected engine (Claude Code vs.
  a configured LiteLLM provider).
- Frontend Settings screen: list engines, show configured/not-configured,
  select active engine + model.

**Components affected:** `backend/app/llm/*`, `backend/app/api/chat.py`
(routing), `backend/app/api/settings.py`, `frontend/src/components/settings/*`.

**Acceptance criteria:**
- With no provider configured, Settings shows only "Claude Code" as
  available and active.
- Adding an API key via env var + a provider entry in `config.yaml` and
  restarting the backend makes that provider appear as configured; selecting
  it in Settings routes subsequent chat calls through LiteLLM.
- `GET /api/settings/llm` response never contains a raw key value (grep the
  response body in the test).
- Removing/unsetting the env var makes the provider show as not-configured
  again without a code change.

**Tests:** backend tests for config loading/env-resolution (including the
never-leak-the-key assertion), and for chat routing choosing the correct
engine based on active-engine setting. LiteLLM call itself mocked in tests
(no real API spend in the test suite).

**Dependencies:** Phase 6.

---

## Phase 8 — Hardening, docs, polish

**Objective:** the app is coherent, documented, and safe to use day-to-day.

**Scope:**
- Error/empty/loading states across all frontend views.
- Finish `README.md`, `SETUP.md`, `USAGE.md` with real, verified instructions
  (superseding the placeholders from earlier phases).
- Review `.gitignore` in both repos; confirm the knowledge repo's history is
  a legible audit trail after several real processing runs.
- Concurrency test: two processing requests submitted back-to-back are
  serialized correctly (second waits, doesn't corrupt the first's edit).
- Basic backend logging (`claude_runner` invocations, job lifecycle) to
  `.synapse/logs/`.

**Components affected:** cross-cutting; root docs.

**Acceptance criteria:**
- A fresh clone of both repos + the documented setup steps in `SETUP.md`
  results in a working app with no undocumented manual steps.
- The full pytest suite and frontend test suite pass.
- Submitting two source files for processing in quick succession completes
  both correctly, in order, with two distinct, correct Git commits in the
  knowledge repo.

**Tests:** the concurrency scenario above as an integration test (real
queue, mocked `claude_runner` subprocess to keep it fast); full suite run.

**Dependencies:** all prior phases.

---

## Explicitly out of scope for this plan

Per `REQUIREMENTS.md` §5: RAG/embeddings, OCR/PDF parsing pipeline, auth/
multi-user, mobile/offline sync, real-time collaboration. None of these are
phases here; if wanted later they'd each need their own requirements pass
first.
