import type { GraphEdge, GraphNode } from "../../api/graph";

export interface FilterOptions {
  /** Selected domains; empty means "no domain filter" (show all). */
  domains: string[];
  /** Selected statuses; empty means "no status filter" (show all). */
  statuses: string[];
}

export const NO_FILTER: FilterOptions = { domains: [], statuses: [] };

export function filterNodes(nodes: GraphNode[], options: FilterOptions): GraphNode[] {
  return nodes.filter((node) => {
    const domainOk = options.domains.length === 0 || node.domains.some((d) => options.domains.includes(d));
    const statusOk = options.statuses.length === 0 || options.statuses.includes(node.status);
    return domainOk && statusOk;
  });
}

/** Edges are only kept when both endpoints survived node filtering — a
 * view-level filter over the one graph, never a separate data source. */
export function filterEdges(edges: GraphEdge[], visibleNodeIds: ReadonlySet<string>): GraphEdge[] {
  return edges.filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target));
}

export function collectDomains(nodes: GraphNode[]): string[] {
  return [...new Set(nodes.flatMap((n) => n.domains))].sort();
}

export function collectStatuses(nodes: GraphNode[]): string[] {
  return [...new Set(nodes.map((n) => n.status))].sort();
}
