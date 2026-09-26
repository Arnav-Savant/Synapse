import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useMemo, useRef, useState } from "react";
import CytoscapeComponent from "react-cytoscapejs";

import type { GraphEdge, GraphNode } from "../../api/graph";
import { Breadcrumb } from "./Breadcrumb";
import { GRAPH_STYLESHEET } from "./cytoscapeStyle";
import { colorForCategory } from "./domainColors";
import { FilterControls } from "./FilterControls";
import { collectCategories, filterEdges, filterNodes, NO_FILTER, type FilterOptions } from "./filters";
import { computeNeighborhood } from "./neighborhood";
import { estimateNodeSize } from "./nodeSize";

cytoscape.use(fcose);

const FOCUS_DEPTH = 2;
const FCOSE_LAYOUT = {
  name: "fcose",
  animate: false,
  fit: true,
  padding: 48,
  // Node width/height come from data(width)/data(height) (nodeSize.ts),
  // computed upfront in JS — not cytoscape's own "width: label" auto-
  // sizing, which fcose can't see correctly at layout time (confirmed:
  // without this, every node collapses onto the same spot because fcose
  // spaces them as if they were near-zero size).
  nodeDimensionsIncludeLabels: true,
} as unknown as cytoscape.LayoutOptions;

interface GraphViewProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  isPending: boolean;
  isError: boolean;
  /** Controlled selection, shared with the knowledge viewer (Phase 5) so
   * graph clicks and wikilink navigation stay in sync regardless of which
   * one triggered the change. */
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
}

export function GraphView({ nodes: allNodes, edges: allEdges, isPending, isError, selectedNodeId, onSelectNode }: GraphViewProps) {
  const cyRef = useRef<cytoscape.Core | null>(null);

  const [filters, setFilters] = useState<FilterOptions>(NO_FILTER);
  const [focusMode, setFocusMode] = useState(false);

  const categoryOptions = useMemo(() => collectCategories(allNodes), [allNodes]);

  const { visibleNodes, visibleEdges } = useMemo(() => {
    let nodes = filterNodes(allNodes, filters);

    if (focusMode && selectedNodeId) {
      const neighborhood = computeNeighborhood(selectedNodeId, allEdges, FOCUS_DEPTH);
      nodes = nodes.filter((n) => neighborhood.has(n.id));
    }

    const visibleIds = new Set(nodes.map((n) => n.id));
    return { visibleNodes: nodes, visibleEdges: filterEdges(allEdges, visibleIds) };
  }, [allNodes, allEdges, filters, focusMode, selectedNodeId]);

  const elements = useMemo(
    () =>
      CytoscapeComponent.normalizeElements([
        ...visibleNodes.map((n) => ({
          data: { id: n.id, label: n.title, color: colorForCategory(n.category), ...estimateNodeSize(n.title) },
        })),
        ...visibleEdges.map((e) => ({
          data: {
            id: `${e.source_id}->${e.target_id}->${e.type}`,
            source: e.source_id,
            target: e.target_id,
            type: e.type,
          },
        })),
      ]),
    [visibleNodes, visibleEdges],
  );

  // Forces a fresh cytoscape mount (and layout re-run) whenever the
  // *visible set* changes — react-cytoscapejs doesn't re-run layout on its
  // own when `elements` changes, only on initial mount.
  const cytoscapeKey = `${filters.categories.join(",")}|${focusMode ? `focus:${selectedNodeId}` : "global"}`;

  // Re-applies selection highlight/centering whenever the selected node
  // changes OR the cytoscape instance is freshly remounted (a new instance
  // starts with nothing selected) — covers both a graph click and an
  // external change (e.g. a wikilink navigated to this node elsewhere).
  // Relationship-type labels only appear on the selected node's own edges
  // (the `.highlighted` class in cytoscapeStyle.ts) — revealed by the
  // action of selecting, not shown cluttering the whole graph by default.
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.edges().removeClass("highlighted");
    if (!selectedNodeId) return;
    const target = cy.getElementById(selectedNodeId);
    if (target.nonempty()) {
      cy.elements().unselect();
      target.select();
      target.connectedEdges().addClass("highlighted");
      cy.animate({ center: { eles: target }, zoom: Math.max(cy.zoom(), 1.2) }, { duration: 300 });
    }
  }, [selectedNodeId, cytoscapeKey]);

  return (
    <div className="relative h-full w-full bg-ink">
      <div className="absolute left-4 top-4 z-10 max-w-md space-y-2 rounded-sm border border-ink-line bg-ink-soft/90 p-3 font-mono text-xs shadow-lg shadow-black/40 backdrop-blur-sm">
        <FilterControls categoryOptions={categoryOptions} filters={filters} onChange={setFilters} />
        <Breadcrumb
          selectedNodeId={selectedNodeId}
          focusMode={focusMode}
          focusDepth={FOCUS_DEPTH}
          onToggleFocus={setFocusMode}
        />
      </div>

      {isPending && <p className="p-4 font-mono text-xs text-graphite">loading graph…</p>}
      {isError && <p className="p-4 font-mono text-xs text-signal">failed to load graph.</p>}
      {!isPending && !isError && visibleNodes.length === 0 && (
        <p className="p-4 font-mono text-xs text-graphite">no concepts match the current filters.</p>
      )}
      {!isPending && !isError && visibleNodes.length > 0 && (
        <CytoscapeComponent
          key={cytoscapeKey}
          elements={elements}
          style={{ width: "100%", height: "100%" }}
          // cytoscape-fcose has no official types, so its layout options
          // (e.g. "fcose" as a `name`) aren't part of @types/cytoscape's
          // built-in LayoutOptions union — cast through unknown rather
          // than fight that gap.
          layout={FCOSE_LAYOUT}
          stylesheet={GRAPH_STYLESHEET}
          cy={(cy) => {
            cyRef.current = cy;
            cy.off("tap", "node");
            cy.on("tap", "node", (evt) => onSelectNode(evt.target.id()));
          }}
        />
      )}
    </div>
  );
}
