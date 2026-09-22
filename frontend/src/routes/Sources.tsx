import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { type CreateSourceInput, createSource, fetchSources } from "../api/sources";
import { ProcessSourceButton } from "../components/jobs/ProcessSourceButton";

const inputClass =
  "w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none";

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
    <div className="space-y-8">
      <form onSubmit={handleSubmit} className="space-y-3 rounded-lg border border-slate-200 p-4">
        <h2 className="font-medium text-slate-800">Add source material</h2>
        <div className="flex gap-3">
          <input
            className={inputClass}
            placeholder="category (e.g. prompt-engineering)"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            required
          />
          <input
            className={inputClass}
            placeholder="filename (e.g. chat-001)"
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
            required
          />
        </div>
        <textarea
          className={inputClass}
          placeholder="Paste conversation / notes / article content here"
          rows={8}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          required
        />
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="rounded-md bg-slate-800 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {createMutation.isPending ? "Saving…" : "Save source"}
        </button>
        {createMutation.isError && (
          <p className="text-sm text-red-600">
            {createMutation.error instanceof Error ? createMutation.error.message : "Failed to save"}
          </p>
        )}
      </form>

      <div>
        <h2 className="mb-2 font-medium text-slate-800">Source files</h2>
        {sourcesQuery.isPending && <p className="text-sm text-slate-500">Loading…</p>}
        {sourcesQuery.isError && <p className="text-sm text-red-600">Failed to load sources.</p>}
        {sourcesQuery.data && sourcesQuery.data.length === 0 && (
          <p className="text-sm text-slate-500">No source files yet.</p>
        )}
        <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200">
          {sourcesQuery.data?.map((source) => (
            <li key={source.relative_path} className="flex items-center justify-between gap-4 px-4 py-2 text-sm">
              <span className="text-slate-700">{source.relative_path}</span>
              <div className="flex items-center gap-3">
                <span className="text-slate-400">{source.size_bytes} B</span>
                <ProcessSourceButton sourceRelativePath={source.relative_path} />
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
