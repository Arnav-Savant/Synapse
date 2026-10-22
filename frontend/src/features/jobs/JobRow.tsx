import type { Job } from "../../api/jobs";
import { Chip } from "../../design/Chip";
import { PipelineTrail } from "./PipelineTrail";
import { describeStep, formatCost, statusChip, timeAgo, trailFor } from "./jobStatus";

interface JobRowProps {
  job: Job;
  onOpen: (job: Job) => void;
}

export function JobRow({ job, onOpen }: JobRowProps) {
  const chip = statusChip(job.status);
  const domains = job.resolved_domains.length ? job.resolved_domains : job.domain_choice === "auto" ? [] : [job.domain_choice];
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(job)}
        className="flex w-full flex-col gap-3 px-5 py-4 text-left transition-colors hover:bg-sunken"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="truncate font-medium">{job.title}</p>
            <p className="mt-0.5 truncate text-sm text-muted">
              {job.status === "failed" && job.error ? job.error : describeStep(job.current_step, job.status)}
            </p>
          </div>
          <Chip tone={chip.tone} dot={chip.dot}>
            {chip.label}
          </Chip>
        </div>
        <PipelineTrail states={trailFor(job)} />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
          <span>{job.input_kind === "topic" ? "Topic only" : "Pasted content"}</span>
          {domains.map((d) => (
            <span key={d} className="rounded bg-sunken px-1.5 py-0.5 font-medium text-fg">
              {d}
            </span>
          ))}
          <span>{timeAgo(job.created_at)}</span>
          <span className="ml-auto tabular-nums">{formatCost(job.total_cost_usd)}</span>
        </div>
      </button>
    </li>
  );
}
