import type { GraphNode } from "../../api/graph";
import { searchNodes } from "./search";

interface SearchBoxProps {
  nodes: GraphNode[];
  query: string;
  onQueryChange: (query: string) => void;
  onSelect: (nodeId: string) => void;
}

export function SearchBox({ nodes, query, onQueryChange, onSelect }: SearchBoxProps) {
  const results = query.trim() ? searchNodes(nodes, query).slice(0, 10) : [];

  return (
    <div className="relative">
      <input
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        placeholder="search concepts…"
        className="w-64 border-b border-ink-line bg-transparent py-1.5 text-graphite placeholder-graphite/60 focus:border-spark focus:text-paper focus:outline-none"
      />
      {query.trim() && (
        <ul className="absolute z-10 mt-1 max-h-64 w-64 overflow-auto border border-ink-line bg-ink-soft shadow-lg shadow-black/40">
          {results.length === 0 && <li className="px-3 py-2 text-graphite/60">no matches</li>}
          {results.map((node) => (
            <li key={node.id}>
              <button
                onClick={() => onSelect(node.id)}
                className="block w-full px-3 py-2 text-left text-paper hover:bg-ink hover:text-spark"
              >
                {node.title}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
