# Using Synapse

A tour of the app, in the order you will meet it. To install and start it see
[`SETUP.md`](SETUP.md).

## The idea in one paragraph

You submit a topic or some pasted material. Synapse works out which domain it
belongs to and proposes an outline: a tree of notes. You approve (or change)
the outline. Agents then research and write the notes, and Synapse shows you the
drafts. You approve the drafts, and only then are files written into your
Obsidian vault.

## Ingest

Open **Ingest** and choose what you are submitting.

- **Topic only.** Type a topic name, such as *database isolation levels*.
  Synapse does a light web scan to understand the topic, proposes an outline,
  and after you approve it researches each subtopic before writing.
- **Paste material.** Paste notes, an article or a transcript. Synapse works out
  the topic and splits your text into a tree of notes, using what you pasted as
  the source. Nothing is researched on the web. Up to 200,000 characters; longer
  input is rejected with a message and never cut off.

Then pick a **domain**, or leave **Auto-detect**. Auto-detect reads the start of
your input and chooses the vault; you see its choice and how sure it was at the
next step. Press **Start**.

## Jobs

**Jobs** lists everything you have submitted, in four groups: **Needs you**,
**Running**, **Queued** and **Finished**. The number beside Jobs in the sidebar
is how many jobs are waiting for a decision from you.

Each job shows a seven-stage trail:

| Stage | What is happening |
|---|---|
| Classify | Working out which domain the input belongs to |
| Outline | Drafting the outline, choosing where the topic sits, and checking for notes you already have |
| Research | Researching each subtopic (skipped for pasted material) |
| Write | Writing notes, then finding references and related links |
| Check | A reviewer agent checks every draft |
| Review | Waiting for you to approve the drafts |
| Save | Writing the approved notes to the vault |

Finished stages are filled, the running stage pulses, and a stage waiting for you
is amber. At most two jobs run at once; others show as **Queued**. A job that is
waiting for your approval does not block the queue.

Click a job to open it. A job waiting for you opens its approval screen. Any
other job opens a detail view with every step that has run, which agent did it,
what it cost, and why it stopped if it failed. You can **Cancel job** from there
while it is active.

## Approving the outline

When a job reaches **Needs you** at the Outline stage, open it. You see the
proposed notes as an indented tree, with the domain Synapse chose.

- **Where the topic sits.** Above the tree, Synapse shows which hub(s) the topic goes under, for
  example *Database internals* above *Buffer pool management*. A hub is a short overview note
  that groups related topics. It is marked **Existing hub** when it is already in your vault, or
  **New hub** when Synapse proposes to create it. It uses as few levels as make sense (none, one or
  two) and reuses a hub you already have whenever one fits. You can pick a different hub, write the
  title and one-line summary of a new one, add or remove a level, or leave the topic with no hub.
  When a hub is chosen, the notes you already have that sit at the top level appear as a checklist:
  tick the ones that belong in the same area to attach them under the hub. Only their parent link
  changes; their text is not touched.
- **Untick a note** to leave it out together with everything beneath it. Tick it
  again to bring it back. The overview note at the top is always written.
- **Add subtopic** under any note to add a note of your own.
- **Overlap badges.** Next to each note, Synapse says how it relates to notes you
  already have: *New note*, *Merges into [[Existing]]*, or *New note, links to
  [[Existing]]*. When there is an existing note it matches, the badge is a menu
  and you can choose a different outcome.
- **Domains.** When a topic belongs to more than one domain, each note has a chip
  per domain; untick a chip to skip that vault for that note.
- **A low-confidence warning** appears when the domain was a close call. If it
  is wrong, cancel the job and submit it again with the domain chosen.

The bar at the bottom shows how many notes will be written. Press
**Approve & write notes** to continue. Or write feedback in the box
(*"fewer notes, and skip implementation details"*) and press
**Re-plan with feedback**: Synapse produces a new outline that keeps your edits
and follows the feedback. You can re-plan as often as you like.

## Reviewing the drafts

When the notes are written and checked, the job needs you again, at the Review
stage. Open it.

The left side lists the drafts as the topic's tree, grouped by vault. Click one
to read it on the right:

- **Preview** shows the note as it will read in Obsidian.
- **Markdown** shows the raw file.
- **Changes** appears for a draft that merges into a note you already have, and
  shows exactly what would change in that file as it is on disk right now.
- A **To check before approving** box lists anything the reviewer agent or the
  automatic checks found: scope creep, a missing section, a claim with no
  support, a link to a note that does not exist, and so on. Notes with something
  to check carry a chip in the list.
- **Also changes existing notes** lists the small additions that approving will make in notes
  you already have: a link added to a hub's Subtopics, and existing notes attached under a hub.

To ask for changes, use the form under the note: choose whether the change
applies to **one section**, **this whole note** or **the whole topic**, say what
should change, and optionally tick **Research again before rewriting** when the
facts themselves are wrong. **Send feedback** rewrites only what you named and
brings you back here. You can do this as often as you like.

Tick the drafts you want and press **Approve selected**. Drafts you leave
unticked are discarded. Synapse writes the notes, and the job finishes. If a note
you merged into was edited in Obsidian after the draft was made, that note is not
overwritten: it is rebuilt from the file as it is now and shown to you again.

**Cancel job** discards all the drafts.

## What a note looks like

Each note is a Markdown file in a folder named after its topic:

```
~/synapse-vaults/system-design/Isolation levels/Dirty reads.md
```

```markdown
---
synapse_id: 5b0c…
domain: system-design
parents: ['[[Anomalies]]']
aliases: [Dirty read]
summary: Reading another transaction's uncommitted writes.
job_id: 8d2f…
created: 2026-10-22
---

Up: [[Anomalies]]

## Foundations
…

## Subtopics
- [[Child note]]: one-line pointer

## Related
- [[Phantom reads]]: how the two anomalies differ

## References
- [PostgreSQL: Transaction Isolation](https://…): the official description
```

- The **file name is the note title**, and titles are unique within a vault. Hubs sit together in a
  `Hubs` folder and have `hub: true` in their frontmatter; a topic's notes sit in a folder named
  after its top note.
- **Up** links to the note's parent; **Subtopics** lists its children;
  **Related** holds cross-links that make the graph dense; **References** lists
  credible sources, official documentation first.
- Overview and parent notes compare their children instead of repeating them.
  Detailed notes follow the section headings of their domain's profile.
- A topic that belongs to more than one domain is written once per vault, each
  version through that domain's lens, and the copies are not linked to each other.

## Notes

**Notes** lists what Synapse has written to a vault, with a search box. A hub is
marked **Hub**. A note
you changed in Obsidian after Synapse wrote it is marked **Edited by you**; one
that also exists in another vault shows **Also in …**.

**Delete** on a row offers *This note*, *Whole topic* and *Everything from its
job* (and, for notes that exist in two vaults, *This vault only* or *Every
vault*). Before anything is removed a window shows what will change:

- the files that will be deleted,
- which other notes have links to them removed, so nothing dangles,
- which notes beneath them move up to take their place.

A note you edited in Obsidian needs an extra tick before it can be deleted.

**Check vaults for changes** rescans every vault. Use it after adding, renaming
or deleting files in Obsidian. A file you create gets an id so Synapse can track
it, a note you edited is marked, a moved file is followed, and a deleted file has
its links cleaned up. This also runs every time the backend starts.

## Settings

**Domains.** Add a domain to create a new vault folder. Each domain has:

- a **name** and a one-line **purpose** (auto-detect uses the purpose),
- an **objective**: what the notes are for and how deep they go,
- the **sections** a detailed note has, in order,
- what is **in scope** and what gets **a one-line mention only**,
- a **style** for tone and writing rules.

**Draft with Claude** fills these in from whatever you have typed, or from a study
prompt you paste (anything about quizzes or tutoring is dropped). Nothing is saved
until you press **Save**. Changing a profile affects future notes only, and
renaming a domain does not rename its folder. Deleting a domain removes its
settings but never its notes or folder, and is refused while a job is using it.

**Models.** Each agent role has its own Claude model and effort level, listed
with what it does. The model is chosen from a dropdown of what Claude Code
offers: pinned versions such as *Opus 5.5*, or *latest* options such as *Opus
(latest)* that follow the newest release. The researcher and the outline planner also have budgets for
web searches. Changes apply to jobs from then on.

## Good to know

- **Cost.** Every job shows what it has cost. As a rough guide, a detailed note
  costs a few tenths of a dollar to write and about a tenth to research, and a
  topic of five notes typically costs between two and four dollars. Writing is the
  largest part, so the note writer's model and effort matter most.
- **Failures are visible.** A job that cannot continue ends as **Failed** with a
  plain-language reason, and its drafts are discarded. Submit it again.
- **Restarting is safe.** If the backend stops, every job resumes where it was
  when it starts again.
- **Obsidian does the viewing.** Use its graph view, search and editor. Synapse
  does not show graphs or edit notes itself.
