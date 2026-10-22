import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { fetchHealth } from "../api/health";
import { IngestIcon, JobsIcon, NotesIcon, SettingsIcon } from "../design/icons";

export type View = "ingest" | "jobs" | "notes" | "settings";

const ITEMS: { view: View; label: string; icon: ReactNode }[] = [
  { view: "ingest", label: "Ingest", icon: <IngestIcon /> },
  { view: "jobs", label: "Jobs", icon: <JobsIcon /> },
  { view: "notes", label: "Notes", icon: <NotesIcon /> },
  { view: "settings", label: "Settings", icon: <SettingsIcon /> },
];

interface SidebarProps {
  view: View;
  onChange: (view: View) => void;
  /** Jobs waiting on a decision from the owner. */
  needsYouCount: number;
}

function Mark() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
      <path d="M6 17 12 6l6 11" stroke="var(--accent)" strokeWidth="1.6" strokeLinejoin="round" />
      <circle cx="12" cy="6" r="2.3" fill="var(--accent)" />
      <circle cx="6" cy="17" r="2.3" fill="var(--surface)" stroke="var(--accent)" strokeWidth="1.6" />
      <circle cx="18" cy="17" r="2.3" fill="var(--surface)" stroke="var(--accent)" strokeWidth="1.6" />
    </svg>
  );
}

function BackendStatus() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, refetchInterval: 15000, retry: false });
  const up = health.data?.status === "ok";
  const down = health.isError;
  return (
    <p className="flex items-center gap-2 px-3 text-xs text-muted" role="status">
      <span className={`h-2 w-2 rounded-full ${up ? "bg-ok" : down ? "bg-danger" : "bg-faint"}`} />
      {up ? "Backend running" : down ? "Backend not reachable" : "Checking backend"}
    </p>
  );
}

export function Sidebar({ view, onChange, needsYouCount }: SidebarProps) {
  return (
    <aside className="flex shrink-0 flex-col gap-2 border-b border-line bg-surface px-3 py-3 md:sticky md:top-0 md:h-screen md:w-56 md:border-b-0 md:border-r md:py-5">
      <div className="flex items-center gap-2.5 px-3 pb-1 md:pb-4">
        <Mark />
        <span className="text-[17px] font-semibold tracking-tight">Synapse</span>
      </div>
      <nav
        aria-label="Main"
        className="flex gap-0.5 overflow-x-auto [scrollbar-width:none] md:flex-col md:gap-1 md:overflow-visible [&::-webkit-scrollbar]:hidden"
      >
        {ITEMS.map((item) => {
          const active = item.view === view;
          return (
            <button
              key={item.view}
              type="button"
              aria-current={active ? "page" : undefined}
              onClick={() => onChange(item.view)}
              className={`flex h-9 shrink-0 items-center gap-2 rounded-control px-2.5 text-sm md:gap-2.5 md:px-3 font-medium transition-colors ${
                active ? "bg-accent-soft text-accent" : "text-muted hover:bg-sunken hover:text-fg"
              }`}
            >
              {item.icon}
              <span>{item.label}</span>
              {item.view === "jobs" && needsYouCount > 0 ? (
                <span
                  className="ml-auto rounded-full bg-warn-soft px-1.5 text-xs font-semibold text-warn"
                  aria-label={`${needsYouCount} waiting for you`}
                >
                  {needsYouCount}
                </span>
              ) : null}
            </button>
          );
        })}
      </nav>
      <div className="hidden md:mt-auto md:block">
        <BackendStatus />
      </div>
    </aside>
  );
}
