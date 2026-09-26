import { describe, expect, it } from "vitest";

import type { GraphEdge, GraphNode } from "../../api/graph";
import { buildTopicTree } from "./topicTree";

function node(id: string, title?: string): GraphNode {
  return { id, title: title ?? id, category: "stub" };
}

function subtopicOf(child: string, parent: string): GraphEdge {
  return {
    source_id: child,
    target_id: parent,
    type: "subtopic-of",
    note: "",
    justification: "",
    confidence: null,
    status: "committed",
    job_id: null,
  };
}

function relatedTo(a: string, b: string): GraphEdge {
  return {
    source_id: a,
    target_id: b,
    type: "related-to",
    note: "",
    justification: "",
    confidence: null,
    status: "committed",
    job_id: null,
  };
}

describe("buildTopicTree", () => {
  it("nests a subtopic under its parent", () => {
    const nodes = [node("prompt-engineering", "Prompt Engineering"), node("few-shot-prompting", "Few-Shot Prompting")];
    const edges = [subtopicOf("few-shot-prompting", "prompt-engineering")];

    const tree = buildTopicTree(nodes, edges);

    expect(tree).toHaveLength(1);
    expect(tree[0].id).toBe("prompt-engineering");
    expect(tree[0].children.map((c) => c.id)).toEqual(["few-shot-prompting"]);
  });

  it("puts concepts with no subtopic-of parent at the top level", () => {
    const nodes = [node("agents"), node("rag")];
    const edges: GraphEdge[] = [];

    const tree = buildTopicTree(nodes, edges);

    expect(tree.map((n) => n.id).sort()).toEqual(["agents", "rag"]);
  });

  it("ignores non-subtopic-of edges when building the hierarchy", () => {
    const nodes = [node("agents"), node("rag")];
    const edges = [relatedTo("agents", "rag")];

    const tree = buildTopicTree(nodes, edges);

    expect(tree).toHaveLength(2);
  });

  it("shows a concept under every subtopic-of parent it has", () => {
    const nodes = [node("prompt-engineering"), node("ai-security"), node("prompt-injection")];
    const edges = [subtopicOf("prompt-injection", "prompt-engineering"), subtopicOf("prompt-injection", "ai-security")];

    const tree = buildTopicTree(nodes, edges);

    const promptEngNode = tree.find((n) => n.id === "prompt-engineering");
    const aiSecNode = tree.find((n) => n.id === "ai-security");
    expect(promptEngNode?.children.map((c) => c.id)).toEqual(["prompt-injection"]);
    expect(aiSecNode?.children.map((c) => c.id)).toEqual(["prompt-injection"]);
  });

  it("nests multiple levels deep", () => {
    const nodes = [node("ai"), node("llms"), node("prompt-engineering")];
    const edges = [subtopicOf("llms", "ai"), subtopicOf("prompt-engineering", "llms")];

    const tree = buildTopicTree(nodes, edges);

    expect(tree).toHaveLength(1);
    expect(tree[0].id).toBe("ai");
    expect(tree[0].children[0].id).toBe("llms");
    expect(tree[0].children[0].children[0].id).toBe("prompt-engineering");
  });

  it("does not infinite-loop on a subtopic-of cycle", () => {
    const nodes = [node("a"), node("b")];
    const edges = [subtopicOf("a", "b"), subtopicOf("b", "a")];

    // Both have a parent, so neither is a root — the tree is empty, not a
    // crash. The important thing is this call returns at all.
    const tree = buildTopicTree(nodes, edges);

    expect(tree).toEqual([]);
  });

  it("sorts siblings alphabetically by title", () => {
    const nodes = [node("root"), node("z", "Zebra"), node("a", "Alpha")];
    const edges = [subtopicOf("z", "root"), subtopicOf("a", "root")];

    const tree = buildTopicTree(nodes, edges);

    expect(tree[0].children.map((c) => c.title)).toEqual(["Alpha", "Zebra"]);
  });
});
