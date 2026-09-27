import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { deleteKnowledge, fetchKnowledgeDetail, updateKnowledge } from "../../api/knowledge";
import { ApiError } from "../../api/client";
import { ConceptMeta } from "./ConceptMeta";
import { EditForm } from "./EditForm";
import { MarkdownBody } from "./MarkdownBody";

interface KnowledgeViewerProps {
  slug: string;
  onNavigate: (slug: string) => void;
  onAskAboutConcept?: (slug: string) => void;
  /** Called after a successful delete — the caller owns clearing whatever
   * selection state made this concept visible in the first place. */
  onDeleted?: () => void;
}

export function KnowledgeViewer({ slug, onNavigate, onAskAboutConcept, onDeleted }: KnowledgeViewerProps) {
  const queryClient = useQueryClient();
  const detailQuery = useQuery({ queryKey: ["knowledge", slug], queryFn: () => fetchKnowledgeDetail(slug) });

  const [mode, setMode] = useState<"view" | "edit">("view");
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const saveMutation = useMutation({
    mutationFn: (body: string) => updateKnowledge(slug, body, detailQuery.data?.metadata ?? {}),
    onSuccess: () => {
      setMode("view");
      void queryClient.invalidateQueries({ queryKey: ["knowledge", slug] });
      void queryClient.invalidateQueries({ queryKey: ["graph"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteKnowledge(slug),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["graph"] });
      void queryClient.invalidateQueries({ queryKey: ["knowledge", slug] });
      onDeleted?.();
    },
  });

  if (detailQuery.isPending) {
    return <p className="font-mono text-xs text-graphite">loading…</p>;
  }

  if (detailQuery.isError) {
    const message = detailQuery.error instanceof ApiError ? detailQuery.error.message : "Failed to load concept.";
    return <p className="font-mono text-xs text-signal">{message}</p>;
  }

  const detail = detailQuery.data;

  return (
    <div className="max-w-[720px] space-y-5 border border-paper-line bg-paper p-8 shadow-[0_20px_60px_-20px_rgba(0,0,0,0.6)]">
      <ConceptMeta detail={detail} onNavigate={onNavigate} />

      {mode === "view" ? (
        <>
          <MarkdownBody body={detail.body} onNavigate={onNavigate} />
          <div className="flex flex-wrap gap-2 border-t border-paper-line pt-4 font-mono text-xs">
            <button
              onClick={() => setMode("edit")}
              className="rounded-sm border border-paper-line px-3 py-1.5 text-paper-ink/70 transition-colors hover:border-spark-dim hover:text-spark-dim"
            >
              edit
            </button>
            {onAskAboutConcept && (
              <button
                onClick={() => onAskAboutConcept(slug)}
                className="rounded-sm border border-paper-line px-3 py-1.5 text-paper-ink/70 transition-colors hover:border-spark-dim hover:text-spark-dim"
              >
                ask about this concept
              </button>
            )}
            <button
              onClick={() => setConfirmingDelete(true)}
              className="rounded-sm border border-paper-line px-3 py-1.5 text-signal-dim transition-colors hover:border-signal-dim hover:bg-signal-dim/10"
            >
              delete
            </button>
          </div>
          {confirmingDelete && (
            <div className="flex flex-wrap items-center gap-3 border-t border-paper-line pt-4 font-mono text-xs text-paper-ink/80">
              <span>delete this concept? this removes it and every relationship it has.</span>
              <button
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="bg-signal-dim px-3 py-1 text-paper disabled:opacity-50"
              >
                {deleteMutation.isPending ? "deleting…" : "confirm"}
              </button>
              <button
                onClick={() => setConfirmingDelete(false)}
                disabled={deleteMutation.isPending}
                className="text-paper-ink/60 hover:text-paper-ink"
              >
                cancel
              </button>
              {deleteMutation.isError && (
                <span className="text-signal-dim">{(deleteMutation.error as Error).message}</span>
              )}
            </div>
          )}
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
