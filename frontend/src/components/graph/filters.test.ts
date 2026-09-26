import { describe, expect, it } from "vitest";

import type { GraphEdge, GraphNode } from "../../api/graph";
import { collectCategories, filterEdges, filterNodes } from "./filters";

const nodes: GraphNode[] = [
  { id: "a", title: "A", category: "prompt-engineering" },
  { id: "b", title: "B", category: "ai-security" },
  { id: "c", title: "C", category: "prompt-engineering" },
];

const edges: GraphEdge[] = [
  {
    source_id: "a",
    target_id: "b",
    type: "related-to",
    note: "",
    justification: "",
    confidence: null,
    status: "committed",
    job_id: null,
  },
  {
    source_id: "b",
    target_id: "c",
    type: "related-to",
    note: "",
    justification: "",
    confidence: null,
    status: "committed",
    job_id: null,
  },
];

describe("filterNodes", () => {
  it("returns all nodes when no filter is set", () => {
    expect(filterNodes(nodes, { categories: [] })).toEqual(nodes);
  });

  it("filters by category", () => {
    const result = filterNodes(nodes, { categories: ["ai-security"] });
    expect(result.map((n) => n.id)).toEqual(["b"]);
  });

  it("matches any selected category", () => {
    const result = filterNodes(nodes, { categories: ["ai-security", "prompt-engineering"] });
    expect(result.map((n) => n.id)).toEqual(["a", "b", "c"]);
  });
});

describe("filterEdges", () => {
  it("keeps only edges whose endpoints are both visible", () => {
    const visible = new Set(["a", "b"]);
    const result = filterEdges(edges, visible);
    expect(result).toEqual([edges[0]]);
  });
});

describe("collectCategories", () => {
  it("collects unique sorted categories across nodes", () => {
    expect(collectCategories(nodes)).toEqual(["ai-security", "prompt-engineering"]);
  });
});
