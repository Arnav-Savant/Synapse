import { apiGet } from "./client";

export interface GraphNode {
  id: string;
  title: string;
  category: string;
}

export interface GraphEdge {
  source_id: string;
  target_id: string;
  type: string;
  note: string;
  justification: string;
  confidence: number | null;
  status: string;
  job_id: string | null;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export function fetchGraph(): Promise<GraphResponse> {
  return apiGet<GraphResponse>("/graph");
}
