export const WIKILINK_SCHEME = "wikilink:";
const WIKILINK_PATTERN = /\[\[([^\]]+)\]\]/g;

/**
 * Rewrites `[[slug]]` / `[[slug|label]]` into a normal Markdown link with a
 * custom `wikilink:` scheme, so react-markdown renders it as a real link
 * node that a custom `a` component can intercept — standard Markdown has
 * no wikilink syntax of its own.
 */
export function preprocessWikilinks(body: string): string {
  return body.replace(WIKILINK_PATTERN, (_match, inner: string) => {
    const [target, label] = inner.split("|");
    const display = (label ?? target).trim();
    return `[${display}](${WIKILINK_SCHEME}${encodeURIComponent(target.trim())})`;
  });
}

export function wikilinkTarget(href: string | undefined): string | null {
  if (!href || !href.startsWith(WIKILINK_SCHEME)) return null;
  return decodeURIComponent(href.slice(WIKILINK_SCHEME.length));
}
