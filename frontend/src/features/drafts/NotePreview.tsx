import type { ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { stripFrontmatter, wikilinksToMarkdown } from "./markdown";

function NoteLink({ href, children, ...rest }: ComponentProps<"a">) {
  if (href?.startsWith("#note:")) {
    return <span className="rounded bg-accent-soft px-1 text-accent">{children}</span>;
  }
  return (
    <a href={href} target="_blank" rel="noreferrer" {...rest}>
      {children}
    </a>
  );
}

/** A note as it will read in Obsidian: the body only, with [[links]] shown as note links. */
export function NotePreview({ markdown }: { markdown: string }) {
  return (
    <article className="prose prose-note">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: NoteLink }} urlTransform={(url) => url}>
        {wikilinksToMarkdown(stripFrontmatter(markdown))}
      </ReactMarkdown>
    </article>
  );
}
