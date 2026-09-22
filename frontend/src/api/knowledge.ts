import { apiGet } from "./client";

interface KnowledgeListResponse {
  slugs: string[];
}

export interface KnowledgeDetail {
  slug: string;
  content: string;
}

export async function fetchKnowledgeSlugs(): Promise<string[]> {
  return (await apiGet<KnowledgeListResponse>("/knowledge")).slugs;
}

export function fetchKnowledgeDetail(slug: string): Promise<KnowledgeDetail> {
  return apiGet<KnowledgeDetail>(`/knowledge/${encodeURIComponent(slug)}`);
}
