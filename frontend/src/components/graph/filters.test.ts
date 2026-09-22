import { describe, expect, it } from "vitest";

import type { GraphEdge, GraphNode } from "../../api/graph";
import { collectDomains, collectStatuses, filterEdges, filterNodes } from "./filters";

const nodes: GraphNode[] = [
  { id: "a", title: "A", aliases: [], domains: ["prompt-engineering"], status: "stub" },
  { id: "b", title: "B", aliases: [], domains: ["ai-security"], status: "developing" },
  { id: "c", title: "C", aliases: [], domains: ["prompt-engineering", "ai-security"], status: "stable" },
];

const edges: GraphEdge[] = [
  { source: "a", target: "b", type: "related-to", inverse_type: "related-to", note: null, implicit: false },
  { source: "b", target: "c", type: "related-to", inverse_type: "related-to", note: null, implicit: false },
];

describe("filterNodes", () => {
  it("returns all nodes when no filter is set", () => {
    expect(filterNodes(nodes, { domains: [], statuses: [] })).toEqual(nodes);
  });

  it("filters by domain", () => {
    const result = filterNodes(nodes, { domains: ["ai-security"], statuses: [] });
    expect(result.map((n) => n.id)).toEqual(["b", "c"]);
  });

  it("filters by status", () => {
    const result = filterNodes(nodes, { domains: [], statuses: ["stub"] });
    expect(result.map((n) => n.id)).toEqual(["a"]);
  });

  it("combines domain and status filters with AND", () => {
    const result = filterNodes(nodes, { domains: ["prompt-engineering"], statuses: ["stable"] });
    expect(result.map((n) => n.id)).toEqual(["c"]);
  });
});

describe("filterEdges", () => {
  it("keeps only edges whose endpoints are both visible", () => {
    const visible = new Set(["a", "b"]);
    const result = filterEdges(edges, visible);
    expect(result).toEqual([edges[0]]);
  });
});

describe("collectDomains / collectStatuses", () => {
  it("collects unique sorted domains across nodes", () => {
    expect(collectDomains(nodes)).toEqual(["ai-security", "prompt-engineering"]);
  });

  it("collects unique sorted statuses across nodes", () => {
    expect(collectStatuses(nodes)).toEqual(["developing", "stable", "stub"]);
  });
});
