/**
 * A small, quiet categorical palette for graph nodes, keyed by domain.
 * Deliberately muted and similar in lightness/saturation so no single
 * domain visually dominates — the amber "spark" accent (cytoscapeStyle.ts)
 * is reserved exclusively for selection/interaction state, never used here.
 *
 * Kept entirely to cool/neutral hues (violet/teal/mauve/moss/blue/plum) —
 * none of them warm — so a category color is never confusable with the
 * warm spark accent or the clay-red/sage-green status colors (index.css).
 * Tuned brighter than a strict desaturated-gray reading: at the low fill
 * opacity cytoscapeStyle.ts renders these at, a too-muted color blends
 * into the near-black canvas as a muddy brown rather than reading as its
 * own hue.
 */
const DOMAIN_PALETTE = [
  "#9C8CD9", // violet
  "#57B0A6", // teal
  "#C97FA0", // mauve
  "#93A857", // moss
  "#6E93C9", // steel blue
  "#9B87A8", // plum
];

const DORMANT_NODE_COLOR = "#4B5568";

export function colorForCategory(category: string): string {
  if (!category) return DORMANT_NODE_COLOR;
  return DOMAIN_PALETTE[hash(category) % DOMAIN_PALETTE.length];
}

function hash(value: string): number {
  let h = 0;
  for (let i = 0; i < value.length; i++) {
    h = (h * 31 + value.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}
