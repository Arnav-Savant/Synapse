import type { GraphEdge } from "../../api/graph";

/**
 * Node ids within `depth` hops of `nodeId` (inclusive of `nodeId` itself),
 * via undirected BFS over the edge list — the focus/ego view for dense
 * regions (docs/ARCHITECTURE.md §8).
 */
export function computeNeighborhood(nodeId: string, edges: GraphEdge[], depth: number): Set<string> {
  const adjacency = buildAdjacency(edges);
  const visited = new Set<string>([nodeId]);
  let frontier = [nodeId];

  for (let hop = 0; hop < depth; hop++) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const neighbor of adjacency.get(id) ?? []) {
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          next.push(neighbor);
        }
      }
    }
    frontier = next;
  }

  return visited;
}

function buildAdjacency(edges: GraphEdge[]): Map<string, string[]> {
  const adjacency = new Map<string, string[]>();
  for (const edge of edges) {
    add(adjacency, edge.source_id, edge.target_id);
    add(adjacency, edge.target_id, edge.source_id);
  }
  return adjacency;
}

function add(adjacency: Map<string, string[]>, from: string, to: string): void {
  const existing = adjacency.get(from);
  if (existing) {
    existing.push(to);
  } else {
    adjacency.set(from, [to]);
  }
}
