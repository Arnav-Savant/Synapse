import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { fetchKnowledgeDetail, updateKnowledge } from "../../api/knowledge";
import { ApiError } from "../../api/client";
import { SourceRawViewer } from "../source/SourceRawViewer";
import { ConceptMeta } from "./ConceptMeta";
import { EditForm } from "./EditForm";
import { MarkdownBody } from "./MarkdownBody";

interface KnowledgeViewerProps {
  slug: string;
  onNavigate: (slug: string) => void;
  onAskAboutConcept?: (slug: string) => void;
}

export function KnowledgeViewer({ slug, onNavigate, onAskAboutConcept }: KnowledgeViewerProps) {
  const queryClient = useQueryClient();
  const detailQuery = useQuery({ queryKey: ["knowledge", slug], queryFn: () => fetchKnowledgeDetail(slug) });

  const [mode, setMode] = useState<"view" | "edit">("view");
  const [openSource, setOpenSource] = useState<string | null>(null);

  const saveMutation = useMutation({
    mutationFn: (content: string) => updateKnowledge(slug, content),
    onSuccess: () => {
      setMode("view");
      void queryClient.invalidateQueries({ queryKey: ["knowledge", slug] });
      void queryClient.invalidateQueries({ queryKey: ["graph"] });
    },
  });

  if (detailQuery.isPending) {
    return <p className="font-mono text-xs text-graphite">loading…</p>;
  }

  if (detailQuery.isError) {
    const message = detailQuery.error instanceof ApiError ? detailQuery.error.message : "Failed to load concept.";
    return <p className="font-mono text-xs text-rose-400">{message}</p>;
  }

  const detail = detailQuery.data;

  return (
    <div className="max-w-[720px] space-y-5 border border-paper-line bg-paper p-8 shadow-[0_20px_60px_-20px_rgba(0,0,0,0.6)]">
      <ConceptMeta detail={detail} onNavigate={onNavigate} />

      {mode === "view" ? (
        <>
          <MarkdownBody body={detail.body} onNavigate={onNavigate} />
          <div className="flex gap-3 border-t border-paper-line pt-4 font-mono text-xs">
            <button onClick={() => setMode("edit")} className="text-paper-ink/60 hover:text-spark-dim">
              edit
            </button>
            {onAskAboutConcept && (
              <button onClick={() => onAskAboutConcept(slug)} className="text-paper-ink/60 hover:text-spark-dim">
                ask about this concept
              </button>
            )}
          </div>
        </>
      ) : (
        <EditForm
          initialContent={detail.raw_content}
          onSave={(content) => saveMutation.mutate(content)}
          onCancel={() => setMode("view")}
          isSaving={saveMutation.isPending}
          error={saveMutation.isError ? (saveMutation.error as Error).message : null}
        />
      )}

      {detail.sources.length > 0 && (
        <div className="space-y-2 border-t border-paper-line pt-4">
          <p className="font-mono text-[11px] text-paper-ink/50">sources</p>
          <div className="flex flex-wrap gap-2">
            {detail.sources.map((source) => (
              <button
                key={source}
                onClick={() => setOpenSource(openSource === source ? null : source)}
                className="border border-paper-line px-2 py-1 font-mono text-[11px] text-paper-ink/70 hover:border-spark-dim hover:text-spark-dim"
              >
                {source}
              </button>
            ))}
          </div>
          {openSource && <SourceRawViewer relativePath={openSource} onClose={() => setOpenSource(null)} />}
        </div>
      )}
    </div>
  );
}
