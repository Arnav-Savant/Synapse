import type { HTMLAttributes } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** `sunken` for a recessed region inside a surface (a code block, a diff). */
  tone?: "surface" | "sunken";
  padded?: boolean;
}

export function Card({ tone = "surface", padded = true, className = "", children, ...rest }: CardProps) {
  const base = tone === "surface" ? "bg-surface border-line" : "bg-sunken border-transparent";
  return (
    <div className={`rounded-panel border ${base} ${padded ? "p-5" : ""} ${className}`} {...rest}>
      {children}
    </div>
  );
}
