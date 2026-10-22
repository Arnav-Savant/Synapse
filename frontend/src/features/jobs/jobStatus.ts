import type { ChipTone } from "../../design/Chip";
import type { Job } from "../../api/jobs";

/** The seven stages a job moves through, in order. Backend steps map onto these. */
export const STAGES = [
  { id: "classify", label: "Classify" },
  { id: "outline", label: "Outline" },
  { id: "research", label: "Research" },
  { id: "write", label: "Write" },
  { id: "check", label: "Check" },
  { id: "review", label: "Review" },
  { id: "save", label: "Save" },
] as const;

const STAGE_OF_STEP: Record<string, number> = {
  classify: 0,
  outline: 1,
  overlap: 1,
  outline_gate: 1,
  research: 2,
  write: 3,
  references: 3,
  related: 3,
  validate: 4,
  draft_gate: 5,
  commit: 6,
};

export type StageState = "done" | "current" | "needs-you" | "failed" | "upcoming" | "skipped";

/** Where each of the seven stages stands for this job. */
export function trailFor(job: Pick<Job, "status" | "current_step" | "input_kind" | "awaiting_owner">): StageState[] {
  const at = job.current_step ? (STAGE_OF_STEP[job.current_step] ?? 0) : 0;
  const states: StageState[] = STAGES.map((_, i) => {
    if (job.status === "completed") return "done";
    if (job.status === "queued" && !job.current_step) return "upcoming";
    if (i < at) return "done";
    if (i > at) return "upcoming";
    if (job.status === "failed") return "failed";
    if (job.status === "cancelled") return "failed";
    if (job.status === "awaiting_owner" || job.awaiting_owner) return "needs-you";
    return "current";
  });
  if (job.input_kind === "content") states[2] = "skipped"; // pasted material is the source, so nothing is researched
  return states;
}

const RUNNING_TEXT: Record<string, string> = {
  classify: "Working out which domain this belongs to",
  outline: "Drafting the outline",
  overlap: "Checking for notes that already cover this",
  research: "Researching each subtopic",
  write: "Writing the notes",
  references: "Finding references",
  related: "Linking related notes",
  validate: "Checking the drafts",
  commit: "Saving notes to your vault",
};

export function describeStep(step: string | null, status: string): string {
  if (status === "queued") return "Waiting for a free slot";
  if (status === "completed") return "Notes saved to your vault";
  if (status === "cancelled") return "Cancelled";
  if (status === "failed") return "Stopped with an error";
  if (status === "awaiting_owner") {
    return step === "draft_gate" ? "Drafts are ready for your review" : "Outline is ready for your approval";
  }
  return (step && RUNNING_TEXT[step]) || "Working";
}

export function statusChip(status: string): { tone: ChipTone; label: string; dot?: boolean | "live" } {
  switch (status) {
    case "queued":
      return { tone: "neutral", label: "Queued" };
    case "running":
      return { tone: "info", label: "Running", dot: "live" };
    case "awaiting_owner":
      return { tone: "warn", label: "Needs you", dot: true };
    case "completed":
      return { tone: "success", label: "Done" };
    case "failed":
      return { tone: "danger", label: "Failed" };
    default:
      return { tone: "neutral", label: "Cancelled" };
  }
}

/** Jobs grouped for the dashboard, in the order they should be read. */
export function groupJobs(jobs: Job[]) {
  return {
    needsYou: jobs.filter((j) => j.status === "awaiting_owner"),
    running: jobs.filter((j) => j.status === "running"),
    queued: jobs.filter((j) => j.status === "queued"),
    finished: jobs.filter((j) => ["completed", "failed", "cancelled"].includes(j.status)),
  };
}

export function timeAgo(iso: string): string {
  const seconds = Math.round((new Date(iso).getTime() - Date.now()) / 1000);
  const fmt = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [["day", 86400], ["hour", 3600], ["minute", 60]];
  for (const [unit, size] of steps) {
    if (Math.abs(seconds) >= size) return fmt.format(Math.round(seconds / size), unit);
  }
  return "just now";
}

export function formatCost(usd: number): string {
  return usd < 0.005 ? "$0.00" : `$${usd.toFixed(2)}`;
}
