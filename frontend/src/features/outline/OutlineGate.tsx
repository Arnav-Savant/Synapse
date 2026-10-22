import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import { listDomains } from "../../api/domains";
import { getOutline, postOutlineDecision, type Outline, type OverlapKind } from "../../api/jobs";
import { listNotes } from "../../api/notes";
import { Button } from "../../design/Button";
import { Card } from "../../design/Card";
import { EmptyState } from "../../design/EmptyState";
import { Field, TextArea } from "../../design/Field";
import { LoadingBlock } from "../../design/Spinner";
import { ActionBar, PageFrame } from "../../shell/PageFrame";
import { JOBS_QUERY_KEY } from "../jobs/useJobs";
import { OutlineTree } from "./OutlineTree";
import { addChild, applyExclusions, setVerdict, toggleDomain } from "./outlineTree";

export function OutlineGate({ jobId, onBack }: { jobId: string; onBack: () => void }) {
  const queryClient = useQueryClient();
  const view = useQuery({ queryKey: ["outline", jobId], queryFn: () => getOutline(jobId) });
  const domains = useQuery({ queryKey: ["domains"], queryFn: listDomains });

  const resolved = view.data?.resolved_domains ?? [];
  const noteQueries = useQueries({
    queries: resolved.map((slug) => ({ queryKey: ["notes", slug, ""], queryFn: () => listNotes(slug) })),
  });
  const noteTitles = useMemo(() => {
    const map = new Map<string, string>();
    for (const q of noteQueries) for (const n of q.data ?? []) map.set(n.synapse_id, n.title);
    return map;
  }, [noteQueries]);
  const domainNames = useMemo(() => Object.fromEntries((domains.data ?? []).map((d) => [d.slug, d.name])), [domains.data]);

  // The owner's working copy. It resets only when a fresh outline arrives (after a re-plan).
  const [tree, setTree] = useState<Outline | null>(null);
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [feedback, setFeedback] = useState("");
  const [loadedFrom, setLoadedFrom] = useState<typeof view.data>(undefined);
  if (view.data && view.data !== loadedFrom) {
    setLoadedFrom(view.data);
    setTree(view.data.outline);
    setExcluded(new Set());
    setFeedback("");
  }

  const decide = useMutation({
    mutationFn: (kind: "approve" | "replan") =>
      postOutlineDecision(jobId, {
        kind,
        tree: applyExclusions(tree!, excluded),
        feedback: feedback.trim() || null,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: JOBS_QUERY_KEY });
      queryClient.removeQueries({ queryKey: ["outline", jobId] });
      onBack();
    },
  });

  const kept = useMemo(() => (tree ? applyExclusions(tree, excluded) : null), [tree, excluded]);
  const noteCount = kept ? kept.nodes.reduce((sum, n) => sum + n.domains.length, 0) : 0;
  const vaultCount = kept ? new Set(kept.nodes.flatMap((n) => n.domains)).size : 0;
  const leftOut = tree && kept ? tree.nodes.length - kept.nodes.length : 0;

  const edit = (change: (t: Outline) => Outline) => setTree((t) => (t ? change(t) : t));
  const toggleExcluded = (key: string) =>
    setExcluded((prev) => {
      const next = new Set(prev);
      if (!next.delete(key)) next.add(key);
      return next;
    });

  return (
    <PageFrame
      wide
      title={tree?.topic_title ?? "Outline"}
      description="Choose what gets written. Untick a note to leave it out with everything under it, add subtopics, or ask for a different plan."
      actions={<Button onClick={onBack}>Back to jobs</Button>}
    >
      {view.isLoading || !tree ? (
        view.isError ? (
          <EmptyState
            tone="error"
            title="Could not load the outline"
            hint={`${view.error.message} It may already have been decided; check the job list.`}
            action={<Button onClick={onBack}>Back to jobs</Button>}
          />
        ) : (
          <LoadingBlock label="Loading the outline" />
        )
      ) : (
        <div className="flex max-w-4xl flex-col gap-6">
          {view.data!.error ? <EmptyState tone="error" title="Your last change was not accepted" hint={view.data!.error} /> : null}

          <Card tone="sunken" className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
            <span>
              Writing into{" "}
              <strong className="font-semibold">{resolved.map((s) => domainNames[s] ?? s).join(" and ") || "…"}</strong>
            </span>
            {view.data!.classifier_confidence !== null ? (
              <span className={view.data!.low_confidence ? "font-medium text-warn" : "text-muted"}>
                Detected with {Math.round(view.data!.classifier_confidence * 100)}% confidence
              </span>
            ) : null}
          </Card>
          {view.data!.low_confidence ? (
            <EmptyState
              title="Check the domain before you approve"
              hint="The domain was a close call. If it is wrong, cancel this job and submit it again with the right domain selected."
              tone="neutral"
            />
          ) : null}

          <Card padded={false} className="px-5 py-2">
            <OutlineTree
              tree={tree}
              excluded={excluded}
              domainNames={domainNames}
              jobDomains={resolved}
              noteTitles={noteTitles}
              onToggleExcluded={toggleExcluded}
              onAdd={(parent, title) => edit((t) => addChild(t, parent, title))}
              onToggleDomain={(key, slug) => edit((t) => toggleDomain(t, key, slug))}
              onVerdict={(key, slug, kind: OverlapKind) => edit((t) => setVerdict(t, key, slug, kind))}
            />
          </Card>

          <Field label="Feedback for a new plan" hint="Say what to change, for example “fewer notes, and skip implementation details”. Required to re-plan.">
            {(c) => <TextArea {...c} value={feedback} rows={3} onChange={(e) => setFeedback(e.target.value)} />}
          </Field>
        </div>
      )}

      {tree ? (
        <ActionBar>
          <div className="min-w-0 text-sm">
            {decide.error ? (
              <span className="text-danger" role="alert">
                {decide.error instanceof ApiError ? decide.error.message : "Could not reach the backend."}
              </span>
            ) : (
              <span className="text-muted">
                {noteCount} {noteCount === 1 ? "note" : "notes"} will be written in {vaultCount} {vaultCount === 1 ? "vault" : "vaults"}
                {leftOut > 0 ? `, ${leftOut} left out` : ""}
              </span>
            )}
          </div>
          <div className="flex gap-2">
            <Button disabled={!feedback.trim() || decide.isPending} loading={decide.isPending && decide.variables === "replan"} onClick={() => decide.mutate("replan")}>
              Re-plan with feedback
            </Button>
            <Button variant="primary" disabled={decide.isPending} loading={decide.isPending && decide.variables === "approve"} onClick={() => decide.mutate("approve")}>
              Approve &amp; write notes
            </Button>
          </div>
        </ActionBar>
      ) : null}
    </PageFrame>
  );
}
