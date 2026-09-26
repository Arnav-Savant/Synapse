import { apiGet, apiPost } from "./client";

export interface Source {
  id: string;
  content: string;
  category: string;
  topic_hint: string | null;
  uploaded_at: string;
}

interface SourceListResponse {
  sources: Source[];
}

export async function fetchSources(): Promise<Source[]> {
  return (await apiGet<SourceListResponse>("/sources")).sources;
}

export interface CreateSourceInput {
  content: string;
  /** Optional — leave category unset to have Claude Code decide it from
   * the content (and topicHint, if given). */
  category?: string;
  topicHint?: string;
}

export interface CreateSourceResult {
  source: Source;
  jobId: string;
}

export async function createSource(input: CreateSourceInput): Promise<CreateSourceResult> {
  const response = await apiPost<{ source: Source; job_id: string }>("/sources", {
    content: input.content,
    category: input.category ?? null,
    topic_hint: input.topicHint ?? null,
  });
  return { source: response.source, jobId: response.job_id };
}
