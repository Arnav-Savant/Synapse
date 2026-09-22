import { useState } from "react";

import { Graph } from "./routes/Graph";
import { HealthBadge } from "./routes/HealthBadge";
import { Knowledge } from "./routes/Knowledge";
import { Sources } from "./routes/Sources";

type Tab = "graph" | "sources" | "knowledge";

const TABS: { id: Tab; label: string }[] = [
  { id: "graph", label: "Graph" },
  { id: "sources", label: "Sources" },
  { id: "knowledge", label: "Knowledge" },
];

export function App() {
  const [tab, setTab] = useState<Tab>("graph");

  return (
    <main className="mx-auto max-w-6xl p-8">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">Synapse</h1>
          <p className="text-sm text-slate-500">Phase 4 — graph visualization and navigation</p>
        </div>
        <HealthBadge />
      </header>

      <nav className="mb-6 flex gap-1 border-b border-slate-200">
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`px-3 py-2 text-sm font-medium ${
              tab === id
                ? "border-b-2 border-slate-800 text-slate-800"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      {tab === "graph" && <Graph />}
      {tab === "sources" && <Sources />}
      {tab === "knowledge" && <Knowledge />}
    </main>
  );
}
