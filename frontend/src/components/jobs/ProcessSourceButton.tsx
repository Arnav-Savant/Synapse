import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { type JobStatus, fetchJob, processSource } from "../../api/jobs";

const TERMINAL_STATUSES = new Set<JobStatus>(["succeeded", "failed"]);
const POLL_INTERVAL_MS = 1000;

export function ProcessSourceButton({ sourceRelativePath }: { sourceRelativePath: string }) {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);

  const triggerMutation = useMutation({
    mutationFn: () => processSource(sourceRelativePath),
    onSuccess: (job) => setJobId(job.id),
  });

  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => fetchJob(jobId as string),
    enabled: jobId !== null,
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
    }
  }, [status, queryClient]);

  if (jobId === null) {
    return (
      <button
        onClick={() => triggerMutation.mutate()}
        disabled={triggerMutation.isPending}
        className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
      >
        {triggerMutation.isPending ? "Starting…" : "Process"}
      </button>
    );
  }

  if (status === "succeeded") {
    return (
      <span className="text-xs text-emerald-600">
        done — {jobQuery.data?.committed_files.length ?? 0} file(s) updated
      </span>
    );
  }

  if (status === "failed") {
    return (
      <span className="text-xs text-red-600" title={jobQuery.data?.error ?? undefined}>
        failed — {jobQuery.data?.error}
      </span>
    );
  }

  return <span className="text-xs text-slate-500">{status ?? "queued"}…</span>;
}
