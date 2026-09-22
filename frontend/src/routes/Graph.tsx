import { GraphView } from "../components/graph/GraphView";

interface GraphProps {
  selectedSlug: string | null;
  onSelectSlug: (slug: string) => void;
}

export function Graph({ selectedSlug, onSelectSlug }: GraphProps) {
  return <GraphView selectedNodeId={selectedSlug} onSelectNode={onSelectSlug} />;
}
