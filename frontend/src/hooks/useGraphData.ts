import { useQuery } from "@tanstack/react-query";

import { fetchGraph, type GraphEdge, type GraphNode } from "../api/graph";

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  isPending: boolean;
  isError: boolean;
}

/**
 * Single shared fetch of the graph, lifted out of GraphView so the top-bar
 * search and (later) the library dock can read the same data without
 * triggering duplicate requests.
 */
export function useGraphData(): GraphData {
  const query = useQuery({ queryKey: ["graph"], queryFn: fetchGraph });

  return {
    nodes: query.data?.nodes ?? [],
    edges: query.data?.edges ?? [],
    isPending: query.isPending,
    isError: query.isError,
  };
}
