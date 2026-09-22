import { describe, expect, it } from "vitest";

import { preprocessWikilinks, wikilinkTarget } from "./wikilinkPreprocess";

describe("preprocessWikilinks", () => {
  it("converts a plain wikilink into a markdown link with the wikilink scheme", () => {
    expect(preprocessWikilinks("See [[prompt-engineering]].")).toBe(
      "See [prompt-engineering](wikilink:prompt-engineering).",
    );
  });

  it("uses the display label for [[slug|label]] but encodes the slug", () => {
    expect(preprocessWikilinks("[[few-shot-prompting|the technique]]")).toBe(
      "[the technique](wikilink:few-shot-prompting)",
    );
  });

  it("leaves normal markdown links untouched", () => {
    const body = "[external](https://example.com)";
    expect(preprocessWikilinks(body)).toBe(body);
  });
});

describe("wikilinkTarget", () => {
  it("extracts the decoded slug from a wikilink href", () => {
    expect(wikilinkTarget("wikilink:prompt-engineering")).toBe("prompt-engineering");
  });

  it("returns null for a non-wikilink href", () => {
    expect(wikilinkTarget("https://example.com")).toBeNull();
  });

  it("returns null for undefined", () => {
    expect(wikilinkTarget(undefined)).toBeNull();
  });
});
