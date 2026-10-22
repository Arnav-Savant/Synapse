import type { ReactNode } from "react";

interface PageFrameProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  /** Gate screens use the full width; everything else keeps a readable column. */
  wide?: boolean;
  children: ReactNode;
}

export function PageFrame({ title, description, actions, wide = false, children }: PageFrameProps) {
  return (
    <main className="min-w-0 flex-1">
      <div className={`px-5 py-7 md:px-10 md:py-9 ${wide ? "" : "max-w-[64rem]"}`}>
        <header className="mb-7 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
            {description ? <p className="mt-1 max-w-prose text-muted">{description}</p> : null}
          </div>
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </header>
        {children}
      </div>
    </main>
  );
}

/** Pinned to the bottom of the window so the main action is never scrolled out of reach. */
export function ActionBar({ children }: { children: ReactNode }) {
  return (
    <div className="sticky bottom-0 z-10 -mx-5 mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-line bg-surface px-5 py-3 md:-mx-10 md:px-10">
      {children}
    </div>
  );
}
