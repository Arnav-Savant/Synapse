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
    return <p className="text-sm text-slate-500">Loading…</p>;
  }

  if (detailQuery.isError) {
    const message = detailQuery.error instanceof ApiError ? detailQuery.error.message : "Failed to load concept.";
    return <p className="text-sm text-red-600">{message}</p>;
  }

  const detail = detailQuery.data;

  return (
    <div className="space-y-4">
      <ConceptMeta detail={detail} onNavigate={onNavigate} />

      {mode === "view" ? (
        <>
          <MarkdownBody body={detail.body} onNavigate={onNavigate} />
          <div className="flex gap-2">
            <button
              onClick={() => setMode("edit")}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
            >
              Edit
            </button>
            {onAskAboutConcept && (
              <button
                onClick={() => onAskAboutConcept(slug)}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
              >
                Ask about this concept
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
        <div className="space-y-2 border-t border-slate-200 pt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Sources</p>
          <div className="flex flex-wrap gap-2">
            {detail.sources.map((source) => (
              <button
                key={source}
                onClick={() => setOpenSource(openSource === source ? null : source)}
                className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
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
