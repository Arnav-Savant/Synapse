/**
 * A small, quiet categorical palette for graph nodes, keyed by domain.
 * Deliberately muted and similar in lightness/saturation so no single
 * domain visually dominates — the amber "spark" accent (cytoscapeStyle.ts)
 * is reserved exclusively for selection/interaction state, never used here.
 */
const DOMAIN_PALETTE = [
  "#8B7FB8", // muted violet
  "#6FA8A0", // muted teal
  "#B87F7F", // muted rose
  "#8FA05E", // muted olive
  "#6E8CB8", // muted blue
  "#B89A5E", // muted ochre
];

const DORMANT_NODE_COLOR = "#4B5568";

export function colorForDomains(domains: string[]): string {
  if (domains.length === 0) return DORMANT_NODE_COLOR;
  return DOMAIN_PALETTE[hash(domains[0]) % DOMAIN_PALETTE.length];
}

function hash(value: string): number {
  let h = 0;
  for (let i = 0; i < value.length; i++) {
    h = (h * 31 + value.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}
