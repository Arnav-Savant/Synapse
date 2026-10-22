import { STAGES, type StageState } from "./jobStatus";

const BAR: Record<StageState, string> = {
  done: "bg-accent",
  current: "bg-info trail-running",
  "needs-you": "bg-warn-bar",
  failed: "bg-danger",
  upcoming: "bg-line-strong/60",
  skipped: "border-t border-dashed border-line-strong bg-transparent",
};

const LABEL: Record<StageState, string> = {
  done: "text-muted",
  current: "text-info font-medium",
  "needs-you": "text-warn font-medium",
  failed: "text-danger font-medium",
  upcoming: "text-faint",
  skipped: "text-faint line-through decoration-faint/60",
};

const SPOKEN: Record<StageState, string> = {
  done: "done",
  current: "in progress",
  "needs-you": "waiting for you",
  failed: "stopped",
  upcoming: "not started",
  skipped: "skipped",
};

/** A job's progress as seven segments: finished stages filled, the current one marked, the rest quiet. */
export function PipelineTrail({ states }: { states: StageState[] }) {
  return (
    <ol
      className="grid grid-cols-7 gap-1.5"
      aria-label={`Progress: ${STAGES.map((s, i) => `${s.label} ${SPOKEN[states[i]]}`).join(", ")}`}
    >
      {STAGES.map((stage, i) => (
        <li key={stage.id} className="flex min-w-0 flex-col gap-1">
          <span className={`block h-1 rounded-full ${BAR[states[i]]}`} />
          <span className={`hidden truncate text-[11px] leading-none sm:block ${LABEL[states[i]]}`}>{stage.label}</span>
        </li>
      ))}
    </ol>
  );
}
