import { apiGet, apiPut } from "./client";

interface KnowledgeListResponse {
  slugs: string[];
}

export interface Relationship {
  type: string;
  target: string;
  note: string | null;
}

export interface KnowledgeDetail {
  slug: string;
  title: string;
  aliases: string[];
  domains: string[];
  status: string;
  created: string | null;
  updated: string | null;
  sources: string[];
  relationships: Relationship[];
  body: string;
  raw_content: string;
}

export async function fetchKnowledgeSlugs(): Promise<string[]> {
  return (await apiGet<KnowledgeListResponse>("/knowledge")).slugs;
}

export function fetchKnowledgeDetail(slug: string): Promise<KnowledgeDetail> {
  return apiGet<KnowledgeDetail>(`/knowledge/${encodeURIComponent(slug)}`);
}

export function updateKnowledge(slug: string, content: string): Promise<KnowledgeDetail> {
  return apiPut<KnowledgeDetail>(`/knowledge/${encodeURIComponent(slug)}`, { content });
}
