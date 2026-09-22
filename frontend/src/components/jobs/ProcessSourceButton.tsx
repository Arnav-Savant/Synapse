import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { processSource } from "../../api/jobs";
import { JobStatusIndicator } from "./JobStatusIndicator";

export function ProcessSourceButton({ sourceRelativePath }: { sourceRelativePath: string }) {
  const [jobId, setJobId] = useState<string | null>(null);

  const triggerMutation = useMutation({
    mutationFn: () => processSource(sourceRelativePath),
    onSuccess: (job) => setJobId(job.id),
  });

  if (jobId === null) {
    return (
      <button
        onClick={() => triggerMutation.mutate()}
        disabled={triggerMutation.isPending}
        className="border border-ink-line px-2 py-1 text-graphite hover:border-spark hover:text-spark disabled:opacity-50"
      >
        {triggerMutation.isPending ? "starting…" : "process"}
      </button>
    );
  }

  return <JobStatusIndicator jobId={jobId} />;
}
