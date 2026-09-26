import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { type CreateSourceResult, createSource, fetchSources } from "../api/sources";
import { JobStatusIndicator } from "../components/jobs/JobStatusIndicator";
import { ProcessSourceButton } from "../components/jobs/ProcessSourceButton";

const inputClass =
  "w-full border-b border-ink-line bg-transparent px-1 py-2 text-paper placeholder-graphite/60 focus:border-spark focus:outline-none";

export function Sources() {
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

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    createMutation.mutate();
  }

  return (
    <div className="max-w-2xl space-y-10 font-mono text-xs">
      <form onSubmit={handleSubmit} className="space-y-4">
        <h2 className="text-graphite">add source material</h2>
        <textarea
          className={`${inputClass} border`}
          placeholder="paste conversation / notes / article content here — raw is fine"
          rows={10}
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
          <p className="text-rose-400">
            {createMutation.error instanceof Error ? createMutation.error.message : "failed to save"}
          </p>
        )}
        {lastSaved && (
          <p className="text-graphite">
            saved as <span className="text-paper">{lastSaved.source.category}</span> — processing:{" "}
            <JobStatusIndicator jobId={lastSaved.jobId} />
          </p>
        )}
      </form>

      <div>
        <h2 className="mb-3 text-graphite">sources</h2>
        {sourcesQuery.isPending && <p className="text-graphite">loading…</p>}
        {sourcesQuery.isError && <p className="text-rose-400">failed to load sources.</p>}
        {sourcesQuery.data && sourcesQuery.data.length === 0 && <p className="text-graphite">no sources yet.</p>}
        <ul className="divide-y divide-ink-line border-y border-ink-line">
          {sourcesQuery.data?.map((source) => (
            <li key={source.id} className="flex items-center justify-between gap-4 py-2.5">
              <span className="text-paper">
                {source.category}
                {source.topic_hint && <span className="text-graphite"> · {source.topic_hint}</span>}
              </span>
              <div className="flex items-center gap-4">
                <span className="text-graphite">{source.content.length} chars</span>
                <ProcessSourceButton sourceId={source.id} />
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
