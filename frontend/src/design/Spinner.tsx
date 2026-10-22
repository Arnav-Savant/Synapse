interface SpinnerProps {
  label?: string;
  className?: string;
}

export function Spinner({ label = "Loading", className = "" }: SpinnerProps) {
  return (
    <svg
      role="img"
      aria-label={label}
      viewBox="0 0 24 24"
      className={`h-4 w-4 animate-spin text-current ${className}`}
      fill="none"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

/** A centred loading line for a whole screen or panel. */
export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2.5 py-10 text-sm text-muted" role="status">
      <Spinner label={label} />
      <span>{label}</span>
    </div>
  );
}
