import type { ButtonHTMLAttributes, ReactNode } from "react";

import { Spinner } from "./Spinner";

type Variant = "primary" | "secondary" | "danger" | "ghost";

interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> {
  variant?: Variant;
  /** Shows a spinner and disables the button while an action is in flight. */
  loading?: boolean;
  size?: "md" | "sm";
  icon?: ReactNode;
  type?: "button" | "submit";
}

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-accent-fg border-transparent hover:bg-accent-hover",
  secondary: "bg-surface text-fg border-line-strong hover:bg-sunken",
  danger: "bg-danger text-surface border-transparent hover:opacity-90",
  ghost: "bg-transparent text-muted border-transparent hover:bg-sunken hover:text-fg",
};

const SIZES = { md: "h-9 px-3.5 text-sm", sm: "h-7 px-2.5 text-[13px]" };

export function Button({
  variant = "secondary",
  loading = false,
  size = "md",
  icon,
  type = "button",
  disabled,
  className = "",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`inline-flex shrink-0 items-center justify-center gap-2 rounded-control border font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${SIZES[size]} ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {loading ? <Spinner label="Working" /> : icon}
      {children}
    </button>
  );
}
