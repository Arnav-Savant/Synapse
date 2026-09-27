import type { ButtonHTMLAttributes, ReactNode } from "react";

interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  icon?: ReactNode;
  /** primary: the one filled, high-contrast action on a given screen (e.g.
   * "add source") — spark is otherwise reserved for selection/active state,
   * so spending it on a real button gives that one action actual weight.
   * ghost (default): everything else. Quiet until touched, so it doesn't
   * compete with the primary action — same reveal-on-hover chrome as
   * IconButton, so the two read as one system rather than two button
   * languages. */
  variant?: "primary" | "ghost";
}

const VARIANT_CLASSES: Record<"primary" | "ghost", string> = {
  primary:
    "border-transparent bg-spark font-medium text-ink hover:brightness-95 active:brightness-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-spark",
  ghost:
    "border-transparent text-graphite hover:border-ink-line hover:bg-ink-soft hover:text-paper focus-visible:border-spark",
};

export function Button({ icon, variant = "ghost", className = "", children, ...buttonProps }: ButtonProps) {
  return (
    <button
      type="button"
      className={`flex h-10 items-center gap-2 rounded-sm border px-3.5 font-mono text-sm transition-colors focus-visible:outline-none ${VARIANT_CLASSES[variant]} ${className}`}
      {...buttonProps}
    >
      {icon}
      <span>{children}</span>
    </button>
  );
}
