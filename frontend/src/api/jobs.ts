import { apiGet, apiPost } from "./client";

export type JobStatus = "running" | "succeeded" | "failed" | "needs_review";

export interface Job {
  id: string;
  source_id: string;
  status: JobStatus;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export function processSource(sourceId: string): Promise<Job> {
  return apiPost<Job>("/jobs/process", { source_id: sourceId });
}

export function fetchJob(jobId: string): Promise<Job> {
  return apiGet<Job>(`/jobs/${encodeURIComponent(jobId)}`);
}
