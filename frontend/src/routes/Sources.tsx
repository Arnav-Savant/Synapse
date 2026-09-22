import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { type CreateSourceInput, createSource, fetchSources } from "../api/sources";
import { ProcessSourceButton } from "../components/jobs/ProcessSourceButton";

const inputClass =
  "w-full border-b border-ink-line bg-transparent px-1 py-2 text-paper placeholder-graphite/60 focus:border-spark focus:outline-none";

export function Sources() {
  const queryClient = useQueryClient();
  const sourcesQuery = useQuery({ queryKey: ["sources"], queryFn: fetchSources });

  const [category, setCategory] = useState("");
  const [filename, setFilename] = useState("");
  const [content, setContent] = useState("");

  const createMutation = useMutation({
    mutationFn: (input: CreateSourceInput) => createSource(input),
    onSuccess: () => {
      setFilename("");
      setContent("");
      void queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    createMutation.mutate({ category, filename, content });
  }

  return (
    <div className="max-w-2xl space-y-10 font-mono text-xs">
      <form onSubmit={handleSubmit} className="space-y-4">
        <h2 className="text-graphite">add source material</h2>
        <div className="flex gap-6">
          <input
            className={inputClass}
            placeholder="category — e.g. prompt-engineering"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            required
          />
          <input
            className={inputClass}
            placeholder="filename — e.g. chat-001"
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
            required
          />
        </div>
        <textarea
          className={`${inputClass} border`}
          placeholder="paste conversation / notes / article content here"
          rows={8}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          required
        />
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="bg-spark px-4 py-1.5 text-ink disabled:opacity-50"
        >
          {createMutation.isPending ? "saving…" : "save source"}
        </button>
        {createMutation.isError && (
          <p className="text-rose-400">
            {createMutation.error instanceof Error ? createMutation.error.message : "failed to save"}
          </p>
        )}
      </form>

      <div>
        <h2 className="mb-3 text-graphite">source files</h2>
        {sourcesQuery.isPending && <p className="text-graphite">loading…</p>}
        {sourcesQuery.isError && <p className="text-rose-400">failed to load sources.</p>}
        {sourcesQuery.data && sourcesQuery.data.length === 0 && (
          <p className="text-graphite">no source files yet.</p>
        )}
        <ul className="divide-y divide-ink-line border-y border-ink-line">
          {sourcesQuery.data?.map((source) => (
            <li key={source.relative_path} className="flex items-center justify-between gap-4 py-2.5">
              <span className="text-paper">{source.relative_path}</span>
              <div className="flex items-center gap-4">
                <span className="text-graphite">{source.size_bytes}b</span>
                <ProcessSourceButton sourceRelativePath={source.relative_path} />
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
