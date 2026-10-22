import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../api/client";
import { cancelJob, getJob, type Job } from "../../api/jobs";
import { Button } from "../../design/Button";
import { Card } from "../../design/Card";
import { Chip } from "../../design/Chip";
import { EmptyState } from "../../design/EmptyState";
import { LoadingBlock } from "../../design/Spinner";
import { PageFrame } from "../../shell/PageFrame";
import { PipelineTrail } from "./PipelineTrail";
import { JOBS_QUERY_KEY } from "./useJobs";
import { describeStep, formatCost, statusChip, timeAgo, trailFor } from "./jobStatus";

interface Props {
  job: Job;
  onBack: () => void;
}

const ACTIVE = ["queued", "running", "awaiting_owner"];

/** Read-only view of a job: where it is, what each step did and cost, and why it stopped if it did. */
export function JobDetailView({ job, onBack }: Props) {
  const queryClient = useQueryClient();
  const detail = useQuery({ queryKey: ["job", job.id], queryFn: () => getJob(job.id), refetchInterval: 3000 });
  const cancel = useMutation({
    mutationFn: () => cancelJob(job.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: JOBS_QUERY_KEY }),
  });
  const chip = statusChip(job.status);

  return (
    <PageFrame
      title={job.title}
      description={describeStep(job.current_step, job.status)}
      actions={
        <>
          <Button onClick={onBack}>Back to jobs</Button>
          {ACTIVE.includes(job.status) ? (
            <Button variant="danger" loading={cancel.isPending} onClick={() => cancel.mutate()}>
              Cancel job
            </Button>
          ) : null}
        </>
      }
    >
      <div className="flex flex-col gap-6">
        {cancel.error ? (
          <EmptyState tone="error" title="Could not cancel the job" hint={cancel.error instanceof ApiError ? cancel.error.message : String(cancel.error)} />
        ) : null}
        {job.error ? <EmptyState tone="error" title="This job stopped" hint={job.error} /> : null}

        <Card>
          <div className="mb-4 flex items-center justify-between gap-3">
            <Chip tone={chip.tone} dot={chip.dot}>
              {chip.label}
            </Chip>
            <span className="text-sm text-muted">
              Started {timeAgo(job.created_at)}, {formatCost(job.total_cost_usd)} so far
            </span>
          </div>
          <PipelineTrail states={trailFor(job)} />
        </Card>

        <section aria-labelledby="steps-heading">
          <h2 id="steps-heading" className="mb-2 text-sm font-semibold text-muted">
            What has run
          </h2>
          {detail.isLoading ? (
            <LoadingBlock label="Loading steps" />
          ) : detail.isError ? (
            <EmptyState tone="error" title="Could not load the steps" hint={detail.error.message} />
          ) : detail.data!.steps.length === 0 ? (
            <EmptyState title="Nothing has run yet" hint="Steps appear here as the job moves along." />
          ) : (
            <Card padded={false}>
              <ul className="divide-y divide-line">
                {detail.data!.steps.map((s, i) => (
                  <li key={i} className="flex items-center gap-4 px-5 py-3 text-sm">
                    <span className="w-24 font-medium capitalize">{s.step}</span>
                    <span className="w-32 text-muted">{s.agent_role ?? "automatic"}</span>
                    <span className={s.status === "failed" ? "text-danger" : "text-muted"}>
                      {s.status === "failed" ? "Failed" : "Done"}
                      {s.attempt > 1 ? `, attempt ${s.attempt}` : ""}
                    </span>
                    {s.error ? <span className="min-w-0 flex-1 truncate text-danger">{s.error}</span> : <span className="flex-1" />}
                    <span className="tabular-nums text-muted">{formatCost(s.cost_usd)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </section>
      </div>
    </PageFrame>
  );
}
