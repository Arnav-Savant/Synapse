import { useQuery } from "@tanstack/react-query";

import { fetchHealth } from "../api/health";

/** Small backend-connectivity indicator. */
export function HealthBadge() {
  const { data, isPending, isError } = useQuery({ queryKey: ["health"], queryFn: fetchHealth });

  // "backend" as its own leading label — the status word alone ("ok",
  // "unreachable") reads as unexplained AI-ops jargon without it.
  const statusText = isPending ? "checking…" : isError ? "unreachable" : data.status;
  const color = isPending ? "bg-graphite" : isError ? "bg-signal" : "bg-signal-ok";

  return (
    <div className="flex items-center gap-2 font-mono text-sm text-graphite" title="Backend connection status">
      <span className={`h-2 w-2 shrink-0 rounded-full ${color}`} />
      <span>backend</span>
      <span className={isError ? "text-signal" : "text-paper"}>{statusText}</span>
    </div>
  );
}
