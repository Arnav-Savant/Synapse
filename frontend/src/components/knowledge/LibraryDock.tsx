import { useMemo, useState } from "react";

import type { GraphEdge, GraphNode } from "../../api/graph";
import { collectCategories, filterNodes } from "../graph/filters";
import { searchNodes } from "../graph/search";
import { buildTopicTree } from "./topicTree";
import { TopicTree } from "./TopicTree";

interface LibraryDockProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  isPending: boolean;
  isError: boolean;
  /** Shared with the canvas and ConceptPanel — see App.tsx. */
  selectedSlug: string | null;
  onSelect: (slug: string) => void;
}

/**
 * Collapsible left-edge dock: the concept library. Replaces the old
 * Knowledge tab's standalone tree route — same lifted graph data
 * (App.tsx's useGraphData()), same selectedSlug/onSelect wiring as the
 * canvas and the right-edge ConceptPanel, so there's one selection and one
 * detail surface, not a second one here.
 *
 * Deletion isn't duplicated as a second confirm-UI: the per-row "×" opens
 * the concept in ConceptPanel (same as clicking the row), where the
 * existing gated delete flow (KnowledgeViewer) already lives.
 */
export function LibraryDock({ nodes, edges, isPending, isError, selectedSlug, onSelect }: LibraryDockProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [query, setQuery] = useState("");
  const [categories, setCategories] = useState<string[]>([]);

  const categoryOptions = useMemo(() => collectCategories(nodes), [nodes]);
  const isFiltering = query.trim() !== "" || categories.length > 0;

  // A search/category filter flattens the view into a plain result list —
  // matches can be scattered anywhere in the hierarchy, and re-deriving a
  // pruned tree per keystroke isn't worth the complexity here. With no
  // filter active, the full hierarchy (below) is what's shown instead.
  const filteredList = useMemo(() => {
    if (!isFiltering) return [];
    const byCategory = filterNodes(nodes, { categories });
    if (!query.trim()) return [...byCategory].sort((a, b) => a.title.localeCompare(b.title));
    return searchNodes(byCategory, query);
  }, [nodes, query, categories, isFiltering]);

  const tree = useMemo(() => buildTopicTree(nodes, edges), [nodes, edges]);

  function toggleCategory(category: string) {
    setCategories((current) => (current.includes(category) ? current.filter((c) => c !== category) : [...current, category]));
  }

  return (
    <div
      className={`relative flex h-full shrink-0 flex-col border-r border-ink-line bg-ink-soft shadow-[0_20px_60px_-20px_rgba(0,0,0,0.6)] transition-[width] duration-300 ease-out ${
        collapsed ? "w-11" : "w-72"
      }`}
    >
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        aria-label={collapsed ? "expand library" : "collapse library"}
        className="flex h-9 w-full shrink-0 items-center justify-center border-b border-ink-line font-mono text-xs text-graphite hover:text-paper"
      >
        {collapsed ? "»" : "«"}
      </button>

      {!collapsed && (
        <div className="flex flex-1 flex-col gap-3 overflow-hidden p-3 font-mono text-xs">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="filter library…"
            className="shrink-0 border-b border-ink-line bg-transparent py-1.5 text-graphite placeholder-graphite/60 focus:border-spark focus:text-paper focus:outline-none"
          />

          {categoryOptions.length > 0 && (
            <div className="flex shrink-0 flex-wrap gap-1.5">
              {categoryOptions.map((category) => (
                <button
                  key={category}
                  onClick={() => toggleCategory(category)}
                  className={`rounded-sm border px-2 py-0.5 ${
                    categories.includes(category)
                      ? "border-spark text-spark"
                      : "border-ink-line text-graphite hover:border-graphite hover:text-paper"
                  }`}
                >
                  {category}
                </button>
              ))}
            </div>
          )}

          <div className="flex-1 overflow-y-auto">
            {isPending && <p className="text-graphite">loading…</p>}
            {isError && <p className="text-signal">failed to load concepts.</p>}

            {!isPending && !isError && isFiltering && filteredList.length === 0 && (
              <p className="text-graphite/60">no matches.</p>
            )}

            {!isPending && !isError && isFiltering && filteredList.length > 0 && (
              <ul className="space-y-0.5">
                {filteredList.map((node) => (
                  <li key={node.id} className="group flex items-center gap-1">
                    <button
                      onClick={() => onSelect(node.id)}
                      className={`flex-1 truncate py-1 text-left ${
                        selectedSlug === node.id ? "text-spark" : "text-graphite hover:text-paper"
                      }`}
                    >
                      {node.title}
                    </button>
                    <button
                      onClick={() => onSelect(node.id)}
                      aria-label={`delete ${node.title}`}
                      title="open concept to delete"
                      className="shrink-0 px-1 text-graphite/0 hover:text-signal group-hover:text-graphite/60"
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            )}

            {!isPending && !isError && !isFiltering && (
              <TopicTree nodes={tree} selectedSlug={selectedSlug} onSelect={onSelect} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
