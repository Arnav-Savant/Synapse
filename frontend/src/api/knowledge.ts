import { apiGet, apiPut } from "./client";

export interface Relationship {
  source_id: string;
  target_id: string;
  type: string;
  note: string | null;
}

export interface KnowledgeDetail {
  id: string;
  title: string;
  category: string;
  metadata: Record<string, unknown>;
  body: string;
  relationships: Relationship[];
}

export function fetchKnowledgeDetail(conceptId: string): Promise<KnowledgeDetail> {
  return apiGet<KnowledgeDetail>(`/knowledge/${encodeURIComponent(conceptId)}`);
}

export function updateKnowledge(
  conceptId: string,
  body: string,
  metadata: Record<string, unknown>,
): Promise<KnowledgeDetail> {
  return apiPut<KnowledgeDetail>(`/knowledge/${encodeURIComponent(conceptId)}`, { body, metadata });
}
