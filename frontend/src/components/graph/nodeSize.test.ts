import { describe, expect, it } from "vitest";

import { estimateNodeSize } from "./nodeSize";

describe("estimateNodeSize", () => {
  it("gives short labels a single-line box with a sensible minimum width", () => {
    const size = estimateNodeSize("RAG");
    expect(size.width).toBeGreaterThanOrEqual(56);
    expect(size.height).toBeGreaterThan(0);
  });

  it("grows width with label length up to the wrap threshold", () => {
    const short = estimateNodeSize("Agents");
    const longer = estimateNodeSize("Prompt Engineering");
    expect(longer.width).toBeGreaterThan(short.width);
  });

  it("wraps very long labels onto multiple lines instead of growing width indefinitely", () => {
    const size = estimateNodeSize("Retrieval-Augmented Generation for Long-Context Agents");
    expect(size.width).toBeLessThanOrEqual(150);
    expect(size.height).toBeGreaterThan(estimateNodeSize("Agents").height);
  });
});
