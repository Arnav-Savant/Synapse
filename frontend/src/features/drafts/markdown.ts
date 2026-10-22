/** Preview helpers: show the note body the way Obsidian would, without its frontmatter. */

export function stripFrontmatter(md: string): string {
  const match = /^---\r?\n[\s\S]*?\r?\n---\r?\n?/.exec(md);
  return match ? md.slice(match[0].length) : md;
}

/** `[[Note]]` and `[[Note|alias]]` become links with a marker href, rendered as note links. */
export function wikilinksToMarkdown(md: string): string {
  return md.replace(/\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]/g, (_m, target: string, alias?: string) => {
    return `[${(alias ?? target).trim()}](#note:${encodeURIComponent(target.trim())})`;
  });
}

/** The `##` headings of a note body, for the "which section" choice. */
export function sectionHeadings(md: string): string[] {
  const body = stripFrontmatter(md);
  const out: string[] = [];
  let inFence = false;
  for (const line of body.split("\n")) {
    if (/^\s*(```|~~~)/.test(line)) inFence = !inFence;
    const m = !inFence && /^## (.+?)\s*$/.exec(line);
    if (m && !["Subtopics", "Related", "References"].includes(m[1])) out.push(m[1]);
  }
  return out;
}
