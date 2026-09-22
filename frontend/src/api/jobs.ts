import { apiGet, apiPost } from "./client";

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface Job {
  id: string;
  source_relative_path: string;
  status: JobStatus;
  created_at: string;
  updated_at: string;
  result_summary: string | null;
  error: string | null;
  committed_files: string[];
  cost_usd: number | null;
}

export function processSource(sourceRelativePath: string): Promise<Job> {
  return apiPost<Job>("/jobs/process", { source_relative_path: sourceRelativePath });
}

export function fetchJob(jobId: string): Promise<Job> {
  return apiGet<Job>(`/jobs/${encodeURIComponent(jobId)}`);
}
