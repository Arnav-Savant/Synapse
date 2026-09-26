import type cytoscape from "cytoscape";

// Nodes are compact pills sized to their own label ("width"/"height":
// "label") — the label IS the node, not a separate floating text element
// beneath a small dot. Edge relationship-type labels stay hidden by
// default (cluttered and, with many edges, unreadable) and only appear on
// the edges touching the current selection, via the `.highlighted` class
// toggled in GraphView's selection effect — a person's action reveals more
// detail, rather than everything being labeled all the time.
export const GRAPH_STYLESHEET: cytoscape.StylesheetJsonBlock[] = [
  {
    selector: "node",
    style: {
      shape: "round-rectangle",
      "background-color": "data(color)",
      "background-opacity": 0.16,
      "border-width": 1.25,
      "border-color": "data(color)",
      label: "data(label)",
      "font-family": "JetBrains Mono, ui-monospace, monospace",
      "font-size": 10,
      color: "#D8DCE6",
      "text-valign": "center",
      "text-halign": "center",
      "text-wrap": "wrap",
      "text-max-width": "128px",
      width: "data(width)",
      height: "data(height)",
    },
  },
  {
    selector: "node:selected",
    style: {
      "background-color": "#D9A441",
      "background-opacity": 0.3,
      "border-color": "#D9A441",
      "border-width": 1.5,
      color: "#FBEBCB",
    },
  },
  {
    selector: "edge",
    style: {
      width: 1,
      "line-color": "#262B38",
      "target-arrow-color": "#262B38",
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.6,
      "curve-style": "bezier",
      "line-opacity": 0.9,
    },
  },
  {
    selector: "edge.highlighted",
    style: {
      "line-color": "#D9A441",
      "target-arrow-color": "#D9A441",
      width: 1.25,
      label: "data(type)",
      "font-family": "JetBrains Mono, ui-monospace, monospace",
      "font-size": 9,
      color: "#D9A441",
      "text-rotation": "autorotate",
      "text-background-color": "#14161C",
      "text-background-opacity": 1,
      "text-background-padding": "2px",
    },
  },
];
