import { describe, expect, it } from "vitest";

import type { GraphNode } from "../../api/graph";
import { searchNodes } from "./search";

const nodes: GraphNode[] = [
  { id: "prompt-engineering", title: "Prompt Engineering", category: "prompting" },
  { id: "few-shot-prompting", title: "Few-Shot Prompting", category: "prompting" },
  { id: "prompt-injection", title: "Prompt Injection", category: "security" },
];

describe("searchNodes", () => {
  it("returns nothing for an empty query", () => {
    expect(searchNodes(nodes, "")).toEqual([]);
    expect(searchNodes(nodes, "   ")).toEqual([]);
  });

  it("matches by exact title, case-insensitively", () => {
    const results = searchNodes(nodes, "prompt injection");
    expect(results[0].id).toBe("prompt-injection");
  });

  it("matches by substring across multiple nodes and ranks prefix above substring", () => {
    const results = searchNodes(nodes, "prompt");
    const ids = results.map((n) => n.id);
    expect(ids).toContain("prompt-engineering");
    expect(ids).toContain("prompt-injection");
    expect(ids).toContain("few-shot-prompting");
    // "prompt-engineering"/"prompt-injection" start with "prompt" (prefix,
    // higher score) — "few-shot-prompting" only contains it (substring).
    expect(ids.indexOf("prompt-engineering")).toBeLessThan(ids.indexOf("few-shot-prompting"));
  });

  it("subsequence-matches a loosely typed query", () => {
    const results = searchNodes(nodes, "fsp");
    expect(results.map((n) => n.id)).toContain("few-shot-prompting");
  });

  it("excludes nodes that match nothing", () => {
    const results = searchNodes(nodes, "zzzzz");
    expect(results).toEqual([]);
  });
});
