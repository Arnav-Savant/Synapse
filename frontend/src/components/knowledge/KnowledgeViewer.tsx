import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { fetchKnowledgeDetail, updateKnowledge } from "../../api/knowledge";
import { ApiError } from "../../api/client";
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

  const saveMutation = useMutation({
    mutationFn: (body: string) => updateKnowledge(slug, body, detailQuery.data?.metadata ?? {}),
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
          initialContent={detail.body}
          onSave={(content) => saveMutation.mutate(content)}
          onCancel={() => setMode("view")}
          isSaving={saveMutation.isPending}
          error={saveMutation.isError ? (saveMutation.error as Error).message : null}
        />
      )}
    </div>
  );
}
