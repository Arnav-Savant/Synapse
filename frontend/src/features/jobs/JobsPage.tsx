import { useState } from "react";

import type { Job } from "../../api/jobs";
import { Button } from "../../design/Button";
import { Card } from "../../design/Card";
import { EmptyState } from "../../design/EmptyState";
import { LoadingBlock } from "../../design/Spinner";
import { PageFrame } from "../../shell/PageFrame";
import { DraftReview } from "../drafts/DraftReview";
import { OutlineGate } from "../outline/OutlineGate";
import { JobDetailView } from "./JobDetailView";
import { JobRow } from "./JobRow";
import { groupJobs } from "./jobStatus";
import { useJobs } from "./useJobs";

export function JobsPage({ onGoToIngest }: { onGoToIngest: () => void }) {
  const jobs = useJobs();
  const [openId, setOpenId] = useState<string | null>(null);

  const open = openId ? jobs.data?.find((j) => j.id === openId) : undefined;
  if (open) {
    const back = () => setOpenId(null);
    if (open.status === "awaiting_owner" && open.current_step === "outline_gate") return <OutlineGate jobId={open.id} onBack={back} />;
    if (open.status === "awaiting_owner" && open.current_step === "draft_gate") return <DraftReview jobId={open.id} onBack={back} />;
    return <JobDetailView job={open} onBack={back} />;
  }

  return (
    <PageFrame title="Jobs" description="Everything you have submitted, and what each job is doing right now.">
      {jobs.isLoading ? (
        <LoadingBlock label="Loading jobs" />
      ) : jobs.isError ? (
        <EmptyState
          tone="error"
          title="Could not load jobs"
          hint={`${jobs.error.message} Check that the backend is running, then try again.`}
          action={<Button onClick={() => jobs.refetch()}>Try again</Button>}
        />
      ) : jobs.data!.length === 0 ? (
        <EmptyState
          title="No jobs yet"
          hint="Submit a topic or paste some notes and the job shows up here with its progress."
          action={<Button variant="primary" onClick={onGoToIngest}>Go to Ingest</Button>}
        />
      ) : (
        <Groups jobs={jobs.data!} onOpen={(j) => setOpenId(j.id)} />
      )}
    </PageFrame>
  );
}

function Groups({ jobs, onOpen }: { jobs: Job[]; onOpen: (job: Job) => void }) {
  const g = groupJobs(jobs);
  const sections: [string, Job[]][] = [
    ["Needs you", g.needsYou],
    ["Running", g.running],
    ["Queued", g.queued],
    ["Finished", g.finished],
  ];
  return (
    <div className="flex flex-col gap-8">
      {sections
        .filter(([, list]) => list.length > 0)
        .map(([title, list]) => (
          <section key={title} aria-labelledby={`jobs-${title}`}>
            <h2 id={`jobs-${title}`} className="mb-2 flex items-baseline gap-2 text-sm font-semibold text-muted">
              {title}
              <span className="font-normal text-faint">{list.length}</span>
            </h2>
            <Card padded={false} className={title === "Needs you" ? "border-warn-bar/60" : ""}>
              <ul className="divide-y divide-line">
                {list.map((job) => (
                  <JobRow key={job.id} job={job} onOpen={onOpen} />
                ))}
              </ul>
            </Card>
          </section>
        ))}
    </div>
  );
}
