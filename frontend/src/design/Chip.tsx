import type { ReactNode } from "react";

export type ChipTone = "neutral" | "info" | "warn" | "success" | "danger";

const TONES: Record<ChipTone, string> = {
  neutral: "bg-sunken text-muted",
  info: "bg-info-soft text-info",
  warn: "bg-warn-soft text-warn",
  success: "bg-ok-soft text-ok",
  danger: "bg-danger-soft text-danger",
};

interface ChipProps {
  tone?: ChipTone;
  /** A small filled dot before the label; pulses for work that is happening right now. */
  dot?: boolean | "live";
  children: ReactNode;
  title?: string;
}

export function Chip({ tone = "neutral", dot = false, children, title }: ChipProps) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${TONES[tone]}`}
    >
      {dot ? <span className={`h-1.5 w-1.5 rounded-full bg-current ${dot === "live" ? "trail-running" : ""}`} /> : null}
      {children}
    </span>
  );
}
