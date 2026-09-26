import type { GraphEdge, GraphNode } from "../../api/graph";

export interface TopicTreeNode {
  id: string;
  title: string;
  children: TopicTreeNode[];
}

/**
 * Builds a hierarchy from `subtopic-of` relationships — "prompt-engineering
 * has these topics under it" (the file-system-style browsing view). This
 * is deliberately *not* backed by physical folders under `knowledge/`: a
 * concept can have more than one `subtopic-of` parent (e.g. prompt
 * injection belongs under both prompt-engineering and ai-security), and a
 * real folder would force picking just one. A derived tree lets it appear
 * under every parent it actually has, same as the graph.
 *
 * Concepts with no `subtopic-of` parent become top-level entries.
 */
export function buildTopicTree(nodes: GraphNode[], edges: GraphEdge[]): TopicTreeNode[] {
  const childrenOf = new Map<string, string[]>();
  const hasParent = new Set<string>();

  for (const edge of edges) {
    if (edge.type !== "subtopic-of") continue;
    // edge.source_id is the more specific concept (the child); edge.target_id
    // is the broader one (the parent) — see docs/ARCHITECTURE.md §4.2.
    const siblings = childrenOf.get(edge.target_id) ?? [];
    siblings.push(edge.source_id);
    childrenOf.set(edge.target_id, siblings);
    hasParent.add(edge.source_id);
  }

  const nodeById = new Map(nodes.map((n) => [n.id, n]));

  function buildNode(id: string, ancestry: ReadonlySet<string>): TopicTreeNode | null {
    const node = nodeById.get(id);
    if (!node) return null;

    const children = (childrenOf.get(id) ?? [])
      .filter((childId) => !ancestry.has(childId)) // guard against a subtopic-of cycle
      .map((childId) => buildNode(childId, new Set(ancestry).add(childId)))
      .filter((child): child is TopicTreeNode => child !== null)
      .sort((a, b) => a.title.localeCompare(b.title));

    return { id: node.id, title: node.title, children };
  }

  return nodes
    .filter((n) => !hasParent.has(n.id))
    .map((n) => buildNode(n.id, new Set([n.id])))
    .filter((n): n is TopicTreeNode => n !== null)
    .sort((a, b) => a.title.localeCompare(b.title));
}
