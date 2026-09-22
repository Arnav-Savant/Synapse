import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarkdownBody } from "./MarkdownBody";

describe("MarkdownBody", () => {
  it("renders plain markdown", () => {
    render(<MarkdownBody body="# Heading\n\nSome text." onNavigate={vi.fn()} />);

    expect(screen.getByText(/Some text\./)).toBeInTheDocument();
  });

  it("renders a [[wikilink]] as a clickable element, not a real link", () => {
    render(<MarkdownBody body="See [[prompt-engineering]] for more." onNavigate={vi.fn()} />);

    const link = screen.getByRole("button", { name: "prompt-engineering" });
    expect(link).toBeInTheDocument();
  });

  it("calls onNavigate with the target slug when a wikilink is clicked", () => {
    const onNavigate = vi.fn();
    render(<MarkdownBody body="See [[prompt-engineering]] for more." onNavigate={onNavigate} />);

    fireEvent.click(screen.getByRole("button", { name: "prompt-engineering" }));

    expect(onNavigate).toHaveBeenCalledWith("prompt-engineering");
  });

  it("renders [[slug|label]] with the display label but navigates to the slug", () => {
    const onNavigate = vi.fn();
    render(<MarkdownBody body="See [[prompt-engineering|the topic]]." onNavigate={onNavigate} />);

    const link = screen.getByRole("button", { name: "the topic" });
    fireEvent.click(link);

    expect(onNavigate).toHaveBeenCalledWith("prompt-engineering");
  });

  it("renders a normal markdown link as a real external anchor", () => {
    render(<MarkdownBody body="[external](https://example.com)" onNavigate={vi.fn()} />);

    const link = screen.getByRole("link", { name: "external" });
    expect(link).toHaveAttribute("href", "https://example.com");
    expect(link).toHaveAttribute("target", "_blank");
  });
});
