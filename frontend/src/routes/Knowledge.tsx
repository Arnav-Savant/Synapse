import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { fetchGraph } from "../api/graph";
import { KnowledgeViewer } from "../components/knowledge/KnowledgeViewer";
import { TopicTree } from "../components/knowledge/TopicTree";
import { buildTopicTree } from "../components/knowledge/topicTree";

interface KnowledgeProps {
  selectedSlug: string | null;
  onSelectSlug: (slug: string) => void;
  onAskAboutConcept: (slug: string) => void;
}

export function Knowledge({ selectedSlug, onSelectSlug, onAskAboutConcept }: KnowledgeProps) {
  // Reuses the same ["graph"] query the Graph tab uses — the hierarchy
  // here is derived from the same subtopic-of relationships, so there's
  // no separate fetch or separate source of truth for it.
  const graphQuery = useQuery({ queryKey: ["graph"], queryFn: fetchGraph });
  const tree = useMemo(
    () => (graphQuery.data ? buildTopicTree(graphQuery.data.nodes, graphQuery.data.edges) : []),
    [graphQuery.data],
  );

  return (
    <div className="grid grid-cols-4 gap-8">
      <div className="font-mono text-xs">
        <h2 className="mb-3 text-graphite">concepts</h2>
        {graphQuery.isPending && <p className="text-graphite">loading…</p>}
        {graphQuery.isError && <p className="text-rose-400">failed to load knowledge list.</p>}
        {graphQuery.data && tree.length === 0 && <p className="text-graphite">no concepts yet.</p>}
        <TopicTree nodes={tree} selectedSlug={selectedSlug} onSelect={onSelectSlug} />
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
