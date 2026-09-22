import { useQuery } from "@tanstack/react-query";
import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { useMemo, useRef, useState } from "react";
import CytoscapeComponent from "react-cytoscapejs";

import { fetchGraph } from "../../api/graph";
import { Breadcrumb } from "./Breadcrumb";
import { GRAPH_STYLESHEET } from "./cytoscapeStyle";
import { FilterControls } from "./FilterControls";
import { collectDomains, collectStatuses, filterEdges, filterNodes, NO_FILTER, type FilterOptions } from "./filters";
import { computeNeighborhood } from "./neighborhood";
import { SearchBox } from "./SearchBox";

cytoscape.use(fcose);

const FOCUS_DEPTH = 2;
const FCOSE_LAYOUT = { name: "fcose", animate: false } as unknown as cytoscape.LayoutOptions;

interface GraphViewProps {
  onSelectNode?: (nodeId: string) => void;
}

export function GraphView({ onSelectNode }: GraphViewProps) {
  const graphQuery = useQuery({ queryKey: ["graph"], queryFn: fetchGraph });
  const cyRef = useRef<cytoscape.Core | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [filters, setFilters] = useState<FilterOptions>(NO_FILTER);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [focusMode, setFocusMode] = useState(false);

  const allNodes = useMemo(() => graphQuery.data?.nodes ?? [], [graphQuery.data]);
  const allEdges = useMemo(() => graphQuery.data?.edges ?? [], [graphQuery.data]);

  const domainOptions = useMemo(() => collectDomains(allNodes), [allNodes]);
  const statusOptions = useMemo(() => collectStatuses(allNodes), [allNodes]);

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
        ...visibleNodes.map((n) => ({ data: { id: n.id, label: n.title } })),
        ...visibleEdges.map((e) => ({
          data: {
            id: `${e.source}->${e.target}->${e.type}`,
            source: e.source,
            target: e.target,
            type: e.type,
            implicit: e.implicit,
          },
        })),
      ]),
    [visibleNodes, visibleEdges],
  );

  // Forces a fresh cytoscape mount (and layout re-run) whenever the
  // *visible set* changes — react-cytoscapejs doesn't re-run layout on its
  // own when `elements` changes, only on initial mount.
  const cytoscapeKey = `${filters.domains.join(",")}|${filters.statuses.join(",")}|${
    focusMode ? `focus:${selectedNodeId}` : "global"
  }`;

  function selectNode(nodeId: string) {
    setSelectedNodeId(nodeId);
    setSearchQuery("");
    onSelectNode?.(nodeId);

    const cy = cyRef.current;
    const target = cy?.getElementById(nodeId);
    if (cy && target && target.nonempty()) {
      cy.elements().unselect();
      target.select();
      cy.animate({ center: { eles: target }, zoom: Math.max(cy.zoom(), 1.2) }, { duration: 300 });
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-4">
        <SearchBox nodes={allNodes} query={searchQuery} onQueryChange={setSearchQuery} onSelect={selectNode} />
        <FilterControls
          domainOptions={domainOptions}
          statusOptions={statusOptions}
          filters={filters}
          onChange={setFilters}
        />
      </div>

      <Breadcrumb
        selectedNodeId={selectedNodeId}
        focusMode={focusMode}
        focusDepth={FOCUS_DEPTH}
        onToggleFocus={setFocusMode}
      />

      <div className="overflow-hidden rounded-lg border border-slate-200" style={{ height: 600 }}>
        {graphQuery.isPending && <p className="p-4 text-sm text-slate-500">Loading graph…</p>}
        {graphQuery.isError && <p className="p-4 text-sm text-red-600">Failed to load graph.</p>}
        {graphQuery.data && visibleNodes.length === 0 && (
          <p className="p-4 text-sm text-slate-500">No concepts match the current filters.</p>
        )}
        {graphQuery.data && visibleNodes.length > 0 && (
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
              cy.on("tap", "node", (evt) => selectNode(evt.target.id()));
            }}
          />
        )}
      </div>

      {graphQuery.data && graphQuery.data.warnings.length > 0 && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-800">
          <p className="font-medium">Warnings</p>
          <ul className="list-disc pl-4">
            {graphQuery.data.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
