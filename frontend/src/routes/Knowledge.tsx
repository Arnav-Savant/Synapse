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
    <div className="grid grid-cols-4 gap-8">
      <div className="font-mono text-xs">
        <h2 className="mb-3 text-graphite">concepts</h2>
        {slugsQuery.isPending && <p className="text-graphite">loading…</p>}
        {slugsQuery.isError && <p className="text-rose-400">failed to load knowledge list.</p>}
        <ul className="space-y-0.5">
          {slugsQuery.data?.map((slug) => (
            <li key={slug}>
              <button
                onClick={() => onSelectSlug(slug)}
                className={`block w-full truncate px-2 py-1.5 text-left ${
                  selectedSlug === slug ? "bg-ink-soft text-spark" : "text-graphite hover:text-paper"
                }`}
              >
                {slug}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="col-span-3">
        {selectedSlug === null ? (
          <p className="font-mono text-xs text-graphite">select a concept to view it.</p>
        ) : (
          <KnowledgeViewer slug={selectedSlug} onNavigate={onSelectSlug} onAskAboutConcept={onAskAboutConcept} />
        )}
      </div>
    </div>
  );
}
