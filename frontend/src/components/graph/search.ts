import type { GraphNode } from "../../api/graph";

/**
 * Fuzzy-ish search over node title/aliases/id. No external library —
 * exact/prefix/substring/subsequence scoring is enough for "hundreds of
 * nodes" and keeps this a pure, trivially testable function.
 */
export function searchNodes(nodes: GraphNode[], query: string): GraphNode[] {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) return [];

  return nodes
    .map((node) => ({ node, score: bestMatchScore(node, trimmed) }))
    .filter((scored) => scored.score > 0)
    .sort((a, b) => b.score - a.score)
    .map((scored) => scored.node);
}

function bestMatchScore(node: GraphNode, query: string): number {
  const candidates = [node.title, ...node.aliases, node.id];
  return Math.max(...candidates.map((candidate) => matchScore(candidate.toLowerCase(), query)));
}

function matchScore(text: string, query: string): number {
  if (text === query) return 100;
  if (text.startsWith(query)) return 80;
  if (text.includes(query)) return 60;
  if (isSubsequence(query, text)) return 30;
  return 0;
}

function isSubsequence(query: string, text: string): boolean {
  if (query.length === 0) return true;
  let i = 0;
  for (const char of text) {
    if (char === query[i]) i++;
    if (i === query.length) return true;
  }
  return false;
}
