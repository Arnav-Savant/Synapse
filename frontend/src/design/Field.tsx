import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { useId } from "react";

const CONTROL =
  "rounded-control border bg-surface px-3 text-sm text-fg placeholder:text-faint disabled:opacity-60";
const normal = "border-line-strong hover:border-faint";
const invalid = "border-danger";

interface FieldProps {
  label: string;
  hint?: string;
  error?: string | null;
  /** Receives the generated id and aria props so the label and message are wired up correctly. */
  children: (control: { id: string; "aria-describedby"?: string; "aria-invalid"?: true }) => ReactNode;
}

/** Label, control, hint and error as one unit. */
export function Field({ label, hint, error, children }: FieldProps) {
  const id = useId();
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-fg">
        {label}
      </label>
      {children({ id, "aria-describedby": describedBy, ...(error ? { "aria-invalid": true as const } : {}) })}
      {error ? (
        <p id={`${id}-error`} className="text-[13px] text-danger" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-[13px] text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function TextInput({ className = "", ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`${CONTROL} h-9 ${rest["aria-invalid"] ? invalid : normal} ${className}`}
      {...rest}
    />
  );
}

export function TextArea({ className = "", ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={`${CONTROL} min-h-24 resize-y py-2 leading-relaxed ${rest["aria-invalid"] ? invalid : normal} ${className}`}
      {...rest}
    />
  );
}

export function SelectInput({ className = "", children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={`${CONTROL} h-9 ${rest["aria-invalid"] ? invalid : normal} ${className}`} {...rest}>
      {children}
    </select>
  );
}
