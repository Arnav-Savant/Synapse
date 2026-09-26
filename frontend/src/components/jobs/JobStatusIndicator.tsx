import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { type JobStatus, fetchJob } from "../../api/jobs";

const TERMINAL_STATUSES = new Set<JobStatus>(["succeeded", "failed", "needs_review"]);
const POLL_INTERVAL_MS = 1000;

/** Polls and displays a processing job's status, given its id. Used both
 * for a manually-triggered "process" click and for the job auto-enqueued
 * right after a source is saved (docs/PLAN.md's ingestion flow — saving
 * and processing are meant to be one action). */
export function JobStatusIndicator({ jobId }: { jobId: string }) {
  const queryClient = useQueryClient();

  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => fetchJob(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && TERMINAL_STATUSES.has(status) ? false : POLL_INTERVAL_MS;
    },
    // Processing runs can take well over a minute (real Claude Code
    // invocations, not instant) — without this, TanStack Query pauses
    // polling as soon as the tab loses focus/visibility, and the status
    // sticks on "running…" until the user manually returns to this tab.
    refetchIntervalInBackground: true,
  });

  const status = jobQuery.data?.status;

  useEffect(() => {
    if (status === "succeeded") {
      void queryClient.invalidateQueries({ queryKey: ["knowledge"] });
      void queryClient.invalidateQueries({ queryKey: ["graph"] });
    }
  }, [status, queryClient]);

  if (status === "succeeded") {
    return <span className="text-emerald-400">done</span>;
  }

  if (status === "failed") {
    return (
      <span className="text-rose-400" title={jobQuery.data?.error ?? undefined}>
        failed — {jobQuery.data?.error}
      </span>
    );
  }

  if (status === "needs_review") {
    return (
      <span className="text-spark" title={jobQuery.data?.error ?? undefined}>
        needs review
      </span>
    );
  }

  return <span className="text-spark">{status ?? "queued"}…</span>;
}
