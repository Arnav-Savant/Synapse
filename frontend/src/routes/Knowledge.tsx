import { useQuery } from "@tanstack/react-query";

import { fetchKnowledgeSlugs } from "../api/knowledge";
import { KnowledgeViewer } from "../components/knowledge/KnowledgeViewer";

interface KnowledgeProps {
  selectedSlug: string | null;
  onSelectSlug: (slug: string) => void;
  onAskAboutConcept: (slug: string) => void;
}

export function Knowledge({ selectedSlug, onSelectSlug, onAskAboutConcept }: KnowledgeProps) {
  const slugsQuery = useQuery({ queryKey: ["knowledge"], queryFn: fetchKnowledgeSlugs });

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
                onClick={() => onSelectSlug(slug)}
                className={`w-full px-3 py-2 text-left text-sm hover:bg-slate-50 ${
                  selectedSlug === slug ? "bg-slate-100 font-medium" : ""
                }`}
              >
                {slug}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="col-span-2">
        {selectedSlug === null ? (
          <p className="text-sm text-slate-500">Select a concept to view it.</p>
        ) : (
          <KnowledgeViewer slug={selectedSlug} onNavigate={onSelectSlug} onAskAboutConcept={onAskAboutConcept} />
        )}
      </div>
    </div>
  );
}
