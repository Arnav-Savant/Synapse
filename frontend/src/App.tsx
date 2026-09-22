import { useState } from "react";

import { Knowledge } from "./routes/Knowledge";
import { HealthBadge } from "./routes/HealthBadge";
import { Sources } from "./routes/Sources";

type Tab = "sources" | "knowledge";

const TABS: { id: Tab; label: string }[] = [
  { id: "sources", label: "Sources" },
  { id: "knowledge", label: "Knowledge" },
];

export function App() {
  const [tab, setTab] = useState<Tab>("sources");

  return (
    <main className="mx-auto max-w-4xl p-8">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">Synapse</h1>
          <p className="text-sm text-slate-500">Phase 2 — Claude Code knowledge processing</p>
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

      {tab === "sources" ? <Sources /> : <Knowledge />}
    </main>
  );
}
