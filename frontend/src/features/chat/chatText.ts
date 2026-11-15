import type { Citation } from "../../api/chats";

/**
 * Replaces each `[E#]` in an answer with a markdown link `[n](#cite-E#)`, numbering 1, 2, ... in order of
 * first use. A reference that is not among the citations is left as written.
 */
export function linkCitations(text: string, citations: Citation[]): string {
  const known = new Set(citations.map((c) => c.ref));
  const numbers = new Map<number, number>();
  return text.replace(/\[E(\d+)\]/g, (match, digits: string) => {
    const ref = Number(digits);
    if (!known.has(ref)) return match;
    if (!numbers.has(ref)) numbers.set(ref, numbers.size + 1);
    return `[${numbers.get(ref)}](#cite-E${ref})`;
  });
}

/** The citations in the order the answer first uses them, which is the order of the numbers `linkCitations` gives. */
export function citedInOrder(text: string, citations: Citation[]): Citation[] {
  const byRef = new Map(citations.map((c) => [c.ref, c]));
  const seen = new Set<number>();
  const ordered: Citation[] = [];
  for (const match of text.matchAll(/\[E(\d+)\]/g)) {
    const ref = Number(match[1]);
    const citation = byRef.get(ref);
    if (citation && !seen.has(ref)) {
      seen.add(ref);
      ordered.push(citation);
    }
  }
  return ordered;
}
