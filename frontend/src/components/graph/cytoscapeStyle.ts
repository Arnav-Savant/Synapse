import type * as cytoscape from "cytoscape";

export const GRAPH_STYLESHEET: cytoscape.StylesheetJsonBlock[] = [
  {
    selector: "node",
    style: {
      "background-color": "#64748b",
      label: "data(label)",
      "font-size": 10,
      color: "#334155",
      "text-valign": "bottom",
      "text-margin-y": 4,
      width: 22,
      height: 22,
    },
  },
  {
    selector: "node:selected",
    style: {
      "background-color": "#0f172a",
      "border-width": 3,
      "border-color": "#38bdf8",
    },
  },
  {
    selector: "edge",
    style: {
      width: 1.5,
      "line-color": "#cbd5e1",
      "target-arrow-color": "#cbd5e1",
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.8,
      "curve-style": "bezier",
      label: "data(type)",
      "font-size": 8,
      color: "#94a3b8",
      "text-rotation": "autorotate",
    },
  },
  {
    selector: "edge[?implicit]",
    style: {
      "line-style": "dashed",
    },
  },
];
