import { useQuery } from "@tanstack/react-query";

import { fetchHealth } from "../api/health";

/** Small backend-connectivity indicator, replaces the Phase 0 full-page health view. */
export function HealthBadge() {
  const { data, isPending, isError } = useQuery({ queryKey: ["health"], queryFn: fetchHealth });

  const label = isPending ? "checking…" : isError ? "backend unreachable" : data.status;
  const color = isPending ? "bg-slate-300" : isError ? "bg-red-500" : "bg-emerald-500";

  return (
    <div className="flex items-center gap-2 text-xs text-slate-500">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {label}
    </div>
  );
}
