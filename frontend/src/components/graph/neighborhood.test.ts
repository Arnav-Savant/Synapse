import { describe, expect, it } from "vitest";

import type { GraphEdge } from "../../api/graph";
import { computeNeighborhood } from "./neighborhood";

function edge(source_id: string, target_id: string): GraphEdge {
  return {
    source_id,
    target_id,
    type: "related-to",
    note: "",
    justification: "",
    confidence: null,
    status: "committed",
    job_id: null,
  };
}

// a - b - c - d   (chain), plus an isolated node "z"
const edges: GraphEdge[] = [edge("a", "b"), edge("b", "c"), edge("c", "d")];

describe("computeNeighborhood", () => {
  it("depth 0 returns only the node itself", () => {
    expect(computeNeighborhood("b", edges, 0)).toEqual(new Set(["b"]));
  });

  it("depth 1 returns direct neighbors, undirected", () => {
    expect(computeNeighborhood("b", edges, 1)).toEqual(new Set(["a", "b", "c"]));
  });

  it("depth 2 expands two hops", () => {
    expect(computeNeighborhood("b", edges, 2)).toEqual(new Set(["a", "b", "c", "d"]));
  });

  it("an isolated node's neighborhood is just itself", () => {
    expect(computeNeighborhood("z", edges, 2)).toEqual(new Set(["z"]));
  });

  it("does not revisit nodes (no infinite loop on cycles)", () => {
    const cyclic = [edge("a", "b"), edge("b", "a")];
    expect(computeNeighborhood("a", cyclic, 3)).toEqual(new Set(["a", "b"]));
  });
});
