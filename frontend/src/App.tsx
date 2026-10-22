import { useState } from "react";

import { IngestPage } from "./features/ingest/IngestPage";
import { JobsPage } from "./features/jobs/JobsPage";
import { NotesPage } from "./features/notes/NotesPage";
import { SettingsPage } from "./features/settings/SettingsPage";
import { useJobs } from "./features/jobs/useJobs";
import { Sidebar, type View } from "./shell/Sidebar";

export function App() {
  // No router: four top-level screens, and the two gate screens open from inside Jobs.
  const [view, setView] = useState<View>("ingest");
  const jobs = useJobs();
  const needsYou = (jobs.data ?? []).filter((j) => j.awaiting_owner && j.status === "awaiting_owner").length;

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <Sidebar view={view} onChange={setView} needsYouCount={needsYou} />
      {view === "ingest" ? (
        <IngestPage onSubmitted={() => setView("jobs")} />
      ) : view === "jobs" ? (
        <JobsPage onGoToIngest={() => setView("ingest")} />
      ) : view === "notes" ? (
        <NotesPage />
      ) : (
        <SettingsPage />
      )}
    </div>
  );
}
