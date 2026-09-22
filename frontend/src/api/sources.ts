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
  category: string;
  filename: string;
  content: string;
}

export function createSource(input: CreateSourceInput): Promise<SourceFile> {
  return apiPost<SourceFile>("/sources", input);
}
