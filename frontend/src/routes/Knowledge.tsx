import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchKnowledgeDetail, fetchKnowledgeSlugs } from "../api/knowledge";

/**
 * Phase 1: raw markdown only, no rendering/graph polish — see docs/PLAN.md
 * Phase 1 scope. Rendering + wikilink navigation land in Phase 5.
 */
export function Knowledge() {
  const [selected, setSelected] = useState<string | null>(null);

  const slugsQuery = useQuery({ queryKey: ["knowledge"], queryFn: fetchKnowledgeSlugs });
  const detailQuery = useQuery({
    queryKey: ["knowledge", selected],
    queryFn: () => fetchKnowledgeDetail(selected as string),
    enabled: selected !== null,
  });

  return (
    <div className="grid grid-cols-3 gap-6">
      <div>
        <h2 className="mb-2 font-medium text-slate-800">Concepts</h2>
        {slugsQuery.isPending && <p className="text-sm text-slate-500">Loading…</p>}
        {slugsQuery.isError && <p className="text-sm text-red-600">Failed to load knowledge list.</p>}
        <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200">
          {slugsQuery.data?.map((slug) => (
            <li key={slug}>
              <button
                onClick={() => setSelected(slug)}
                className={`w-full px-3 py-2 text-left text-sm hover:bg-slate-50 ${
                  selected === slug ? "bg-slate-100 font-medium" : ""
                }`}
              >
                {slug}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="col-span-2">
        <h2 className="mb-2 font-medium text-slate-800">Raw content</h2>
        {selected === null && <p className="text-sm text-slate-500">Select a concept to view it.</p>}
        {detailQuery.isPending && selected !== null && <p className="text-sm text-slate-500">Loading…</p>}
        {detailQuery.data && (
          <pre className="whitespace-pre-wrap rounded-lg border border-slate-200 p-4 text-sm text-slate-800">
            {detailQuery.data.content}
          </pre>
        )}
      </div>
    </div>
  );
}
