import { useQuery } from "@tanstack/react-query";

import { fetchSourceContent } from "../../api/sources";

interface SourceRawViewerProps {
  relativePath: string;
  onClose: () => void;
}

/** Read-only raw source material — deliberately unstyled/plain compared to
 * generated knowledge, so it's unmistakable which one you're looking at
 * (FR4.1: preserve the distinction between raw source and synthesized
 * knowledge). */
export function SourceRawViewer({ relativePath, onClose }: SourceRawViewerProps) {
  const query = useQuery({
    queryKey: ["source-content", relativePath],
    queryFn: () => fetchSourceContent(relativePath),
  });

  return (
    <div className="rounded-md border border-amber-300 bg-amber-50 p-3">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-amber-700">
          Raw source material — {relativePath}
        </p>
        <button onClick={onClose} className="text-xs text-amber-700 underline hover:text-amber-900">
          close
        </button>
      </div>
      {query.isPending && <p className="text-sm text-amber-700">Loading…</p>}
      {query.isError && <p className="text-sm text-red-600">Failed to load source.</p>}
      {query.data && (
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap font-mono text-xs text-amber-900">
          {query.data}
        </pre>
      )}
    </div>
  );
}
