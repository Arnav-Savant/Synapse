import type { GraphEdge, GraphNode } from "../../api/graph";

export interface FilterOptions {
  /** Selected categories; empty means "no category filter" (show all). */
  categories: string[];
}

export const NO_FILTER: FilterOptions = { categories: [] };

export function filterNodes(nodes: GraphNode[], options: FilterOptions): GraphNode[] {
  return nodes.filter((node) => options.categories.length === 0 || options.categories.includes(node.category));
}

/** Edges are only kept when both endpoints survived node filtering — a
 * view-level filter over the one graph, never a separate data source. */
export function filterEdges(edges: GraphEdge[], visibleNodeIds: ReadonlySet<string>): GraphEdge[] {
  return edges.filter((edge) => visibleNodeIds.has(edge.source_id) && visibleNodeIds.has(edge.target_id));
}

export function collectCategories(nodes: GraphNode[]): string[] {
  return [...new Set(nodes.map((n) => n.category))].sort();
}
