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
        placeholder="Search concepts…"
        className="w-64 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
      />
      {query.trim() && (
        <ul className="absolute z-10 mt-1 max-h-64 w-64 overflow-auto rounded-md border border-slate-200 bg-white shadow-lg">
          {results.length === 0 && <li className="px-3 py-2 text-sm text-slate-400">No matches</li>}
          {results.map((node) => (
            <li key={node.id}>
              <button
                onClick={() => onSelect(node.id)}
                className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
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
