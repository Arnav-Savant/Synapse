import { useMutation, useQuery } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";

import { ApiError } from "../../api/client";
import { listDomains } from "../../api/domains";
import { listNotes, reconcile, type DeleteResult, type Note, type ReconcileReport } from "../../api/notes";
import { Button } from "../../design/Button";
import { Card } from "../../design/Card";
import { Chip } from "../../design/Chip";
import { EmptyState } from "../../design/EmptyState";
import { SelectInput, TextInput } from "../../design/Field";
import { LoadingBlock } from "../../design/Spinner";
import { PageFrame } from "../../shell/PageFrame";
import { DeleteDialog, type DeleteRequestInfo } from "./DeleteDialog";

const topicFolder = (note: Note) => (note.path.includes("/") ? note.path.split("/")[0] : null);

function deleteOptions(note: Note): DeleteRequestInfo[] {
  const base = { domain: note.domain_slug };
  const options: DeleteRequestInfo[] = [];
  if (note.twin_domains.length > 0) {
    options.push({ label: "This vault only", title: `Delete “${note.title}” from ${note.domain_slug} only`, selector: { ...base, note_ids: [note.synapse_id], twin_scope: "this" } });
    options.push({ label: "Every vault", title: `Delete “${note.title}” from every vault`, selector: { ...base, note_ids: [note.synapse_id], twin_scope: "all" } });
  } else {
    options.push({ label: "This note", title: `Delete “${note.title}”`, selector: { ...base, note_ids: [note.synapse_id] } });
  }
  const folder = topicFolder(note);
  if (folder) options.push({ label: "Whole topic", title: `Delete the whole topic “${folder}”`, selector: { ...base, topic_folder: folder, twin_scope: "this" } });
  if (note.job_id) options.push({ label: "Everything from its job", title: `Delete everything the job that made “${note.title}” created`, selector: { ...base, job_id: note.job_id } });
  return options;
}

export function NotesPage() {
  const domains = useQuery({ queryKey: ["domains"], queryFn: listDomains });
  const [slug, setSlug] = useState("");
  const [q, setQ] = useState("");
  const search = useDeferredValue(q);
  const active = slug || domains.data?.[0]?.slug || "";

  const notes = useQuery({ queryKey: ["notes", active, search], queryFn: () => listNotes(active, search), enabled: Boolean(active) });
  const [dialog, setDialog] = useState<DeleteRequestInfo | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const scan = useMutation({ mutationFn: reconcile });
  const names = Object.fromEntries((domains.data ?? []).map((d) => [d.slug, d.name]));

  return (
    <PageFrame
      title="Notes"
      description="What Synapse has written to each vault. Deleting here also cleans up the links, so Obsidian never shows a ghost note."
      actions={
        <Button loading={scan.isPending} onClick={() => scan.mutate()}>
          Check vaults for changes
        </Button>
      }
    >
      {scan.data ? <ReconcileSummary report={scan.data} /> : null}
      {scan.error ? <EmptyState tone="error" title="The check failed" hint={scan.error instanceof ApiError ? scan.error.message : "Could not reach the backend."} /> : null}
      {message ? (
        <p className="mb-4 rounded-control bg-ok-soft px-4 py-2.5 text-sm text-ok" role="status">
          {message}
        </p>
      ) : null}

      {domains.isLoading ? (
        <LoadingBlock label="Loading domains" />
      ) : domains.isError ? (
        <EmptyState tone="error" title="Could not load your domains" hint={domains.error.message} />
      ) : (domains.data ?? []).length === 0 ? (
        <EmptyState title="No domains yet" hint="Create a domain in Settings. Each domain has its own vault of notes." />
      ) : (
        <>
          <div className="mb-5 flex flex-wrap gap-3">
            <SelectInput aria-label="Domain" value={active} onChange={(e) => setSlug(e.target.value)} className="w-52">
              {domains.data!.map((d) => (
                <option key={d.slug} value={d.slug}>
                  {d.name}
                </option>
              ))}
            </SelectInput>
            <TextInput aria-label="Search notes" type="search" placeholder="Search by title or summary" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-sm" />
          </div>

          {notes.isLoading ? (
            <LoadingBlock label="Loading notes" />
          ) : notes.isError ? (
            <EmptyState tone="error" title="Could not load the notes" hint={notes.error.message} action={<Button onClick={() => notes.refetch()}>Try again</Button>} />
          ) : notes.data!.length === 0 ? (
            <EmptyState
              title={search ? "No notes match your search" : `No notes in ${names[active] ?? active} yet`}
              hint={search ? "Try fewer words." : "Notes appear here once a job's drafts are approved, or after you add files to the vault and check it for changes."}
            />
          ) : (
            <Card padded={false}>
              <ul className="divide-y divide-line">
                {notes.data!.map((n) => {
                  const options = deleteOptions(n);
                  return (
                    <li key={n.synapse_id} className="flex items-start justify-between gap-4 px-5 py-3.5">
                      <div className="min-w-0">
                        <p className="flex flex-wrap items-center gap-2 font-medium">
                          {n.title}
                          {n.user_modified ? <Chip tone="warn" title="Edited in Obsidian after Synapse wrote it">Edited by you</Chip> : null}
                          {n.twin_domains.map((t) => (
                            <Chip key={t}>Also in {names[t] ?? t}</Chip>
                          ))}
                        </p>
                        <p className="mt-0.5 font-mono text-xs text-muted">{n.path}</p>
                        {n.summary ? <p className="mt-1 line-clamp-2 max-w-prose text-sm text-muted">{n.summary}</p> : null}
                      </div>
                      <details className="relative shrink-0">
                        <summary className="flex h-7 cursor-pointer list-none items-center rounded-control border border-transparent px-2.5 text-[13px] font-medium text-muted hover:bg-sunken hover:text-fg [&::-webkit-details-marker]:hidden">
                          Delete
                        </summary>
                        <ul className="absolute right-0 z-10 mt-1 w-56 rounded-control border border-line bg-surface p-1 shadow-[var(--shadow-pop)]">
                          {options.map((o, i) => (
                            <li key={i}>
                              <button
                                type="button"
                                className="w-full rounded px-2.5 py-1.5 text-left text-sm hover:bg-sunken"
                                onClick={(e) => {
                                  (e.currentTarget.closest("details") as HTMLDetailsElement).open = false;
                                  setDialog(o);
                                }}
                              >
                                {o.label}
                              </button>
                            </li>
                          ))}
                        </ul>
                      </details>
                    </li>
                  );
                })}
              </ul>
            </Card>
          )}
        </>
      )}

      {dialog ? (
        <DeleteDialog
          request={dialog}
          onClose={() => setDialog(null)}
          onDeleted={(r: DeleteResult) => {
            setDialog(null);
            setMessage(`Deleted ${r.deleted} ${r.deleted === 1 ? "note" : "notes"}. Links removed in ${r.links_stripped_in} other ${r.links_stripped_in === 1 ? "note" : "notes"}, ${r.children_reattached} moved up.`);
          }}
        />
      ) : null}
    </PageFrame>
  );
}

function ReconcileSummary({ report }: { report: Record<string, ReconcileReport> }) {
  const rows = Object.entries(report);
  const total = rows.reduce((n, [, r]) => n + r.added + r.removed + r.modified + r.moved, 0);
  return (
    <div className="mb-5 rounded-control border border-line bg-sunken px-4 py-3 text-sm" role="status">
      <p className="font-medium">
        {total === 0 ? `Checked ${rows.length} vaults. Nothing changed.` : `Checked ${rows.length} vaults and found changes.`}
      </p>
      {total > 0 ? (
        <ul className="mt-1 text-muted">
          {rows.filter(([, r]) => r.added + r.removed + r.modified + r.moved > 0).map(([slug, r]) => (
            <li key={slug}>
              {slug}: {r.added} added, {r.removed} removed, {r.modified} edited by you, {r.moved} moved
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
