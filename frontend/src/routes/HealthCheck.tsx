import { useQuery } from "@tanstack/react-query";

import { fetchHealth } from "../api/health";

/**
 * Phase 0 placeholder route: proves the frontend can reach the backend.
 * Replaced by the real graph route in Phase 4.
 */
export function HealthCheck() {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  if (isPending) {
    return <p className="text-slate-500">Checking backend…</p>;
  }

  if (isError) {
    return (
      <p className="text-red-600">
        Backend unreachable: {error instanceof Error ? error.message : "unknown error"}
      </p>
    );
  }

  return (
    <dl className="space-y-2 text-sm">
      <div className="flex gap-2">
        <dt className="font-medium text-slate-600">status</dt>
        <dd className="text-emerald-600">{data.status}</dd>
      </div>
      <div className="flex gap-2">
        <dt className="font-medium text-slate-600">knowledge_repo_path</dt>
        <dd>{data.knowledge_repo_path}</dd>
      </div>
      <div className="flex gap-2">
        <dt className="font-medium text-slate-600">knowledge_repo_exists</dt>
        <dd>{String(data.knowledge_repo_exists)}</dd>
      </div>
    </dl>
  );
}
