/**
 * Pre-computes each node's pill size from its label, as plain numeric
 * data rather than relying on cytoscape's own "width: label" auto-sizing.
 *
 * That auto-sizing has a real timing problem with force-directed layouts:
 * fcose reads node dimensions when it lays the graph out, but a
 * label-sized node's true width/height isn't settled until cytoscape has
 * actually rendered it — so fcose spaces nodes as if they were near-zero
 * size and they end up stacked on top of each other. Computing the size
 * upfront in JS and passing it as `data(width)`/`data(height)` gives fcose
 * a real number from the start.
 */

const CHAR_WIDTH_PX = 6.4; // approx. JetBrains Mono at 10px
const PADDING_X = 22;
const MAX_WIDTH = 150;
const LINE_HEIGHT = 15;
const PADDING_Y = 13;

export interface NodeSize {
  width: number;
  height: number;
}

export function estimateNodeSize(label: string): NodeSize {
  const singleLineWidth = label.length * CHAR_WIDTH_PX + PADDING_X;
  if (singleLineWidth <= MAX_WIDTH) {
    return { width: Math.max(56, Math.round(singleLineWidth)), height: LINE_HEIGHT + PADDING_Y };
  }

  const charsPerLine = (MAX_WIDTH - PADDING_X) / CHAR_WIDTH_PX;
  const lines = Math.ceil(label.length / charsPerLine);
  return { width: MAX_WIDTH, height: lines * LINE_HEIGHT + PADDING_Y };
}
