import { useQuery } from "@tanstack/react-query";

import { fetchHealth } from "../api/health";

/** Small backend-connectivity indicator. */
export function HealthBadge() {
  const { data, isPending, isError } = useQuery({ queryKey: ["health"], queryFn: fetchHealth });

  const label = isPending ? "checking…" : isError ? "backend unreachable" : data.status;
  const color = isPending ? "bg-graphite" : isError ? "bg-rose-400" : "bg-emerald-400";

  return (
    <div className="flex items-center gap-2 font-mono text-xs text-graphite">
      <span className={`h-1.5 w-1.5 rounded-full ${color}`} />
      {label}
    </div>
  );
}
