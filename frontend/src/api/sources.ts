import { apiGet, apiPost } from "./client";

export interface SourceFile {
  category: string;
  filename: string;
  relative_path: string;
  size_bytes: number;
}

interface SourceFileListResponse {
  sources: SourceFile[];
}

export async function fetchSources(): Promise<SourceFile[]> {
  return (await apiGet<SourceFileListResponse>("/sources")).sources;
}

export interface CreateSourceInput {
  content: string;
  /** All optional — leave category/filename unset to have Claude Code
   * decide them from the content (and topicHint, if given). */
  category?: string;
  filename?: string;
  topicHint?: string;
}

export interface CreateSourceResult {
  source: SourceFile;
  jobId: string;
}

export async function createSource(input: CreateSourceInput): Promise<CreateSourceResult> {
  const response = await apiPost<{ source: SourceFile; job_id: string }>("/sources", {
    content: input.content,
    category: input.category ?? null,
    filename: input.filename ?? null,
    topic_hint: input.topicHint ?? null,
  });
  return { source: response.source, jobId: response.job_id };
}

interface SourceContentResponse {
  relative_path: string;
  content: string;
}

export async function fetchSourceContent(relativePath: string): Promise<string> {
  const encodedPath = relativePath.split("/").map(encodeURIComponent).join("/");
  return (await apiGet<SourceContentResponse>(`/sources/${encodedPath}`)).content;
}
