import type { ButtonHTMLAttributes, ReactNode } from "react";

interface IconButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  icon: ReactNode;
  "aria-label": string;
  /** lg (40px) for standalone header/panel controls, md (36px) inside a
   * tighter compound control like the chat dock's own header row. */
  size?: "md" | "lg";
  /** ink: for controls on the dark canvas (header, chat dock, modals).
   * paper: for controls on the paper reading surface (ConceptPanel). */
  surface?: "ink" | "paper";
}

const SIZE_CLASSES: Record<"md" | "lg", string> = {
  md: "h-9 w-9",
  lg: "h-10 w-10",
};

const SURFACE_CLASSES: Record<"ink" | "paper", string> = {
  ink: "text-graphite hover:border-ink-line hover:bg-ink-soft hover:text-paper focus-visible:border-spark",
  paper: "text-paper-ink/50 hover:border-paper-line hover:bg-paper-soft hover:text-paper-ink focus-visible:border-spark-dim",
};

/** Shared icon-only control: a real, consistently-sized hit box with visible
 * hover/focus affordance, instead of a bare unicode glyph floating with no
 * button chrome (why "+", "⚙", "×" all read as too small regardless of
 * browser zoom — there was no box to make bigger). */
export function IconButton({ icon, size = "lg", surface = "ink", className = "", ...buttonProps }: IconButtonProps) {
  return (
    <button
      type="button"
      className={`flex shrink-0 items-center justify-center rounded-sm border border-transparent transition-colors focus-visible:outline-none ${SIZE_CLASSES[size]} ${SURFACE_CLASSES[surface]} ${className}`}
      {...buttonProps}
    >
      {icon}
    </button>
  );
}
