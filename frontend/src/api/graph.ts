import { apiGet } from "./client";

export interface GraphNode {
  id: string;
  title: string;
  aliases: string[];
  domains: string[];
  status: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  inverse_type: string;
  note: string | null;
  implicit: boolean;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  warnings: string[];
}

export function fetchGraph(): Promise<GraphResponse> {
  return apiGet<GraphResponse>("/graph");
}
