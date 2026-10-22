import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  hint?: string;
  action?: ReactNode;
  /** `error` is for a request that failed: say what went wrong and how to fix it. */
  tone?: "neutral" | "error";
}

export function EmptyState({ title, hint, action, tone = "neutral" }: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-start gap-1 rounded-panel border border-dashed px-6 py-8 ${
        tone === "error" ? "border-danger/50 bg-danger-soft" : "border-line-strong"
      }`}
      role={tone === "error" ? "alert" : undefined}
    >
      <p className={`font-medium ${tone === "error" ? "text-danger" : "text-fg"}`}>{title}</p>
      {hint ? <p className="max-w-prose text-sm text-muted">{hint}</p> : null}
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}
