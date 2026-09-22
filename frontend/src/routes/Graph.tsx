import { GraphView } from "../components/graph/GraphView";

/**
 * Phase 4: the graph as navigation surface. Node selection is observable
 * (`onSelectNode`) but doesn't open anything yet — that's Phase 5.
 */
export function Graph() {
  return <GraphView onSelectNode={(nodeId) => console.info("selected node:", nodeId)} />;
}
