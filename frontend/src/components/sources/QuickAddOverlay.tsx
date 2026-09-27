import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { type CreateSourceResult, createSource, fetchSources } from "../../api/sources";
import { JobStatusIndicator } from "../jobs/JobStatusIndicator";
import { ProcessSourceButton } from "../jobs/ProcessSourceButton";
import { IconButton } from "../ui/IconButton";
import { XIcon } from "../ui/icons";

const inputClass =
  "w-full border-b border-ink-line bg-transparent px-1 py-2 text-paper placeholder-graphite/60 focus:border-spark focus:outline-none";

interface QuickAddOverlayProps {
  onClose: () => void;
}

/**
 * Centered compose overlay for quickly filing a new source, opened from the
 * header's "+" trigger (App.tsx). Reuses the same form/list logic that used
 * to live on the full-page Sources route, since removed as part of the
 * graph-canvas shell redesign.
 *
 * On a successful save this shows a brief confirmation (saved-as category +
 * JobStatusIndicator) instead of closing immediately: JobStatusIndicator
 * polls for a real `claude -p` run, which can take a couple of minutes, and
 * closing the instant the job is dispatched would unmount that indicator —
 * stranding the one piece of feedback that tells the user whether filing
 * actually worked. The user can still dismiss at any time (×, backdrop
 * click, or Escape); reopening the trigger always starts from a blank form
 * since this component isn't kept mounted while closed.
 */
export function QuickAddOverlay({ onClose }: QuickAddOverlayProps) {
  const queryClient = useQueryClient();
  const sourcesQuery = useQuery({ queryKey: ["sources"], queryFn: fetchSources });

  const [topicHint, setTopicHint] = useState("");
  const [content, setContent] = useState("");
  const [lastSaved, setLastSaved] = useState<CreateSourceResult | null>(null);

  const createMutation = useMutation({
    mutationFn: () => createSource({ content, topicHint: topicHint.trim() || undefined }),
    onSuccess: (result) => {
      setLastSaved(result);
      setTopicHint("");
      setContent("");
      void queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    createMutation.mutate();
  }

  return (
    <div
      className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-ink/80 p-6 pt-20"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg space-y-6 border border-ink-line bg-ink-soft p-5 font-mono text-xs shadow-[0_20px_60px_-20px_rgba(0,0,0,0.6)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm text-graphite">add source</h2>
          <IconButton icon={<XIcon />} aria-label="Close" title="Close" onClick={onClose} size="md" />
        </div>

        {lastSaved ? (
          <div className="space-y-3">
            <p className="text-graphite">
              saved as <span className="text-paper">{lastSaved.source.category}</span>
            </p>
            <p className="text-graphite">
              processing: <JobStatusIndicator jobId={lastSaved.jobId} />
            </p>
            <button
              type="button"
              onClick={onClose}
              className="border border-ink-line px-3 py-1.5 text-graphite hover:border-spark hover:text-spark"
            >
              close
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <textarea
              className={`${inputClass} border`}
              placeholder="paste conversation / notes / article content here — raw is fine"
              rows={8}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              required
            />
            <input
              className={inputClass}
              placeholder="topic (optional) — leave blank and Claude will figure out where this belongs"
              value={topicHint}
              onChange={(e) => setTopicHint(e.target.value)}
            />
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="bg-spark px-4 py-1.5 text-ink disabled:opacity-50"
            >
              {createMutation.isPending ? "filing this…" : "save source"}
            </button>
            {createMutation.isError && (
              <p className="text-signal">
                {createMutation.error instanceof Error ? createMutation.error.message : "failed to save"}
              </p>
            )}
          </form>
        )}

        <div>
          <h2 className="mb-2 text-graphite">recent sources</h2>
          {sourcesQuery.isPending && <p className="text-graphite">loading…</p>}
          {sourcesQuery.isError && <p className="text-signal">failed to load sources.</p>}
          {sourcesQuery.data && sourcesQuery.data.length === 0 && <p className="text-graphite">no sources yet.</p>}
          {sourcesQuery.data && sourcesQuery.data.length > 0 && (
            <ul className="max-h-56 divide-y divide-ink-line overflow-y-auto border-y border-ink-line">
              {sourcesQuery.data.map((source) => (
                <li key={source.id} className="flex items-center justify-between gap-3 py-2">
                  <div className="flex min-w-0 flex-col">
                    <span className="truncate text-paper">{source.category}</span>
                    {source.topic_hint && (
                      <span className="truncate text-graphite/70">{source.topic_hint}</span>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <span className="text-graphite">{source.content.length} chars</span>
                    <ProcessSourceButton sourceId={source.id} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
