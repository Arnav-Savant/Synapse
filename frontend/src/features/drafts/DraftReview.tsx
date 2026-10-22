import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import { listDomains } from "../../api/domains";
import { cancelJob, getDrafts, postDraftDecision, type Draft } from "../../api/jobs";
import { Button } from "../../design/Button";
import { Card } from "../../design/Card";
import { Chip } from "../../design/Chip";
import { EmptyState } from "../../design/EmptyState";
import { LoadingBlock } from "../../design/Spinner";
import { ActionBar, PageFrame } from "../../shell/PageFrame";
import { JOBS_QUERY_KEY } from "../jobs/useJobs";
import { DraftDiff } from "./DraftDiff";
import { DraftList } from "./DraftList";
import { buildDraftDecision, draftKey, feedbackProblem, flagLabel, type FeedbackForm } from "./draftDecision";
import { FeedbackPanel } from "./FeedbackPanel";
import { sectionHeadings } from "./markdown";
import { NotePreview } from "./NotePreview";

type Tab = "preview" | "changes" | "markdown";
const EMPTY_FORM: FeedbackForm = { scope: "note", section: "", text: "", reResearch: false };

export function DraftReview({ jobId, onBack }: { jobId: string; onBack: () => void }) {
  const queryClient = useQueryClient();
  const drafts = useQuery({ queryKey: ["drafts", jobId], queryFn: () => getDrafts(jobId) });
  const domains = useQuery({ queryKey: ["domains"], queryFn: listDomains });
  const domainNames = useMemo(() => Object.fromEntries((domains.data ?? []).map((d) => [d.slug, d.name])), [domains.data]);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab | null>(null);
  const [form, setForm] = useState<FeedbackForm>(EMPTY_FORM);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [loadedFrom, setLoadedFrom] = useState<typeof drafts.data>(undefined);

  // Start with every draft that can be saved ticked; reset when a fresh set arrives after feedback.
  if (drafts.data && drafts.data !== loadedFrom) {
    setLoadedFrom(drafts.data);
    setSelected(new Set(drafts.data.drafts.filter((d) => d.stage !== "stale" && !d.validator_flags.some((f) => f.code === "commit_failed")).map(draftKey)));
    setActiveKey((k) => (k && drafts.data!.drafts.some((d) => draftKey(d) === k) ? k : drafts.data!.drafts[0] ? draftKey(drafts.data!.drafts[0]) : null));
    setForm(EMPTY_FORM);
  }

  const list = drafts.data?.drafts ?? [];
  const active: Draft | undefined = list.find((d) => draftKey(d) === activeKey);
  const tabNow: Tab = tab ?? (active?.kind === "merge" ? "changes" : "preview");

  const finish = async () => {
    await queryClient.invalidateQueries({ queryKey: JOBS_QUERY_KEY });
    queryClient.removeQueries({ queryKey: ["drafts", jobId] });
    onBack();
  };
  const decide = useMutation({
    mutationFn: (kind: "approve" | "feedback") =>
      postDraftDecision(jobId, buildDraftDecision({ kind, drafts: list, selected, active: active ?? null, feedback: form })),
    onSuccess: finish,
  });
  const cancel = useMutation({ mutationFn: () => cancelJob(jobId), onSuccess: finish });

  const toggle = (key: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (!next.delete(key)) next.add(key);
      return next;
    });
  const problem = feedbackProblem(form);
  const error = decide.error ?? cancel.error;
  const errorText = error ? (error instanceof ApiError ? error.message : error instanceof Error ? error.message : "Could not reach the backend.") : null;
  const additions = (drafts.data?.link_additions ?? []).filter((a) => !active || a.entry_title === active.title);

  return (
    <PageFrame
      wide
      title="Review the drafts"
      description="Nothing is written to your vault until you approve. Open a note to read it, ask for changes, or untick it to discard it."
      actions={<Button onClick={onBack}>Back to jobs</Button>}
    >
      {drafts.isLoading ? (
        <LoadingBlock label="Loading the drafts" />
      ) : drafts.isError ? (
        <EmptyState tone="error" title="Could not load the drafts" hint={`${drafts.error.message} They may already have been decided; check the job list.`} action={<Button onClick={onBack}>Back to jobs</Button>} />
      ) : list.length === 0 ? (
        <EmptyState title="No drafts to review" hint="This job has no drafts waiting. Check its status in the job list." action={<Button onClick={onBack}>Back to jobs</Button>} />
      ) : (
        <div className="grid items-start gap-8 lg:grid-cols-[21rem_minmax(0,1fr)]">
          <div className="flex flex-col gap-6 lg:sticky lg:top-6">
            <DraftList drafts={list} domainNames={domainNames} selected={selected} activeKey={activeKey} onToggle={toggle} onOpen={(k) => { setActiveKey(k); setTab(null); }} />
            {(drafts.data!.link_additions.length > 0 || drafts.data!.attachments.length > 0) ? (
              <section aria-labelledby="existing-heading">
                <h3 id="existing-heading" className="mb-1 text-sm font-semibold text-muted">Also changes existing notes</h3>
                <ul className="flex flex-col gap-1 text-sm">
                  {drafts.data!.attachments.map((a, i) => (
                    <li key={`attach-${i}`} className="text-muted">
                      Attaches <span className="font-medium text-fg">[[{a.note_title}]]</span> under <span className="font-medium text-fg">[[{a.hub_title}]]</span>
                    </li>
                  ))}
                  {drafts.data!.link_additions.map((a, i) => (
                    <li key={i} className="text-muted">
                      Adds a link to <span className="font-medium text-fg">[[{a.entry_title}]]</span> in <span className="font-medium text-fg">[[{a.note_title}]]</span>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </div>

          {active ? (
            <div className="flex min-w-0 flex-col gap-6">
              <div>
                <h2 className="text-xl font-semibold tracking-tight">{active.title}</h2>
                <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
                  <span className="font-mono text-xs">{active.path}</span>
                  {active.kind === "merge" ? <Chip tone="info">Merges into an existing note</Chip> : <Chip>New note</Chip>}
                  {active.stage === "stale" ? <Chip tone="info" dot="live">Being rebuilt from the current file</Chip> : null}
                </p>
              </div>

              {active.validator_flags.length > 0 ? (
                <Card className="border-warn-bar/60 bg-warn-soft" role="note" aria-label="Things to check">
                  <p className="mb-2 text-sm font-semibold text-warn">To check before approving</p>
                  <ul className="flex flex-col gap-1.5 text-sm">
                    {active.validator_flags.map((f, i) => (
                      <li key={i}>
                        <span className="font-medium">{flagLabel(f.code)}.</span> <span className="text-muted">{f.message}</span>
                      </li>
                    ))}
                  </ul>
                </Card>
              ) : null}

              {additions.length > 0 ? (
                <p className="text-sm text-muted">
                  Approving also adds a link in {additions.map((a) => `[[${a.note_title}]]`).join(", ")}.
                </p>
              ) : null}

              <div>
                <div className="mb-3 inline-flex rounded-control border border-line-strong p-0.5" role="tablist" aria-label="View">
                  {([["preview", "Preview"], ...(active.kind === "merge" ? [["changes", "Changes"]] : []), ["markdown", "Markdown"]] as [Tab, string][]).map(([id, label]) => (
                    <button
                      key={id}
                      role="tab"
                      type="button"
                      aria-selected={tabNow === id}
                      onClick={() => setTab(id)}
                      className={`rounded-[4px] px-3 py-1 text-sm font-medium transition-colors ${tabNow === id ? "bg-sunken text-fg" : "text-muted hover:text-fg"}`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                {tabNow === "preview" ? (
                  <NotePreview markdown={active.body_md} />
                ) : tabNow === "changes" && active.diff !== null ? (
                  <DraftDiff diff={active.diff} />
                ) : (
                  <pre className="overflow-x-auto whitespace-pre-wrap rounded-control border border-line bg-sunken p-4 font-mono text-[12.5px] leading-relaxed">{active.body_md}</pre>
                )}
              </div>

              <FeedbackPanel form={form} onChange={setForm} sections={sectionHeadings(active.body_md)} noteTitle={active.title} />
            </div>
          ) : null}
        </div>
      )}

      {list.length > 0 ? (
        <ActionBar>
          <div className="min-w-0 text-sm">
            {errorText ? (
              <span className="text-danger" role="alert">{errorText}</span>
            ) : (
              <span className="text-muted">
                {selected.size} of {list.length} selected. Notes you leave unticked are discarded when you approve.
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {confirmCancel ? (
              <>
                <Button variant="danger" loading={cancel.isPending} onClick={() => cancel.mutate()}>Yes, discard everything</Button>
                <Button variant="ghost" onClick={() => setConfirmCancel(false)}>Keep reviewing</Button>
              </>
            ) : (
              <Button variant="ghost" onClick={() => setConfirmCancel(true)}>Cancel job</Button>
            )}
            <Button title={problem ?? undefined} disabled={Boolean(problem) || decide.isPending} loading={decide.isPending && decide.variables === "feedback"} onClick={() => decide.mutate("feedback")}>
              Send feedback
            </Button>
            <Button variant="primary" disabled={selected.size === 0 || decide.isPending} loading={decide.isPending && decide.variables === "approve"} onClick={() => decide.mutate("approve")}>
              Approve selected
            </Button>
          </div>
        </ActionBar>
      ) : null}
    </PageFrame>
  );
}
