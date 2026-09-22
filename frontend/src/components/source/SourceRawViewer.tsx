import { useQuery } from "@tanstack/react-query";

import { fetchSourceContent } from "../../api/sources";

interface SourceRawViewerProps {
  relativePath: string;
  onClose: () => void;
}

/** Read-only raw source material. Deliberately breaks out of the paper
 * reading surface into the dark/mono "unprocessed" voice used everywhere
 * else for raw or structural material — unmistakable that this hasn't been
 * through synthesis (FR4.1: never confuse raw source with generated
 * knowledge). */
export function SourceRawViewer({ relativePath, onClose }: SourceRawViewerProps) {
  const query = useQuery({
    queryKey: ["source-content", relativePath],
    queryFn: () => fetchSourceContent(relativePath),
  });

  return (
    <div className="border border-ink-line bg-ink p-3 font-mono text-xs">
      <div className="mb-2 flex items-center justify-between text-graphite">
        <p>
          raw source — <span className="text-paper">{relativePath}</span>
        </p>
        <button onClick={onClose} className="hover:text-spark">
          close
        </button>
      </div>
      {query.isPending && <p className="text-graphite">loading…</p>}
      {query.isError && <p className="text-rose-400">failed to load source.</p>}
      {query.data && (
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap text-graphite">{query.data}</pre>
      )}
    </div>
  );
}
