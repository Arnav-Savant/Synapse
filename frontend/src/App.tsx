import { useState } from "react";

import { Chat } from "./routes/Chat";
import { Graph } from "./routes/Graph";
import { HealthBadge } from "./routes/HealthBadge";
import { Knowledge } from "./routes/Knowledge";
import { Sources } from "./routes/Sources";

type Tab = "graph" | "sources" | "knowledge" | "chat";

const TABS: { id: Tab; label: string }[] = [
  { id: "graph", label: "Graph" },
  { id: "sources", label: "Sources" },
  { id: "knowledge", label: "Knowledge" },
  { id: "chat", label: "Chat" },
];

export function App() {
  const [tab, setTab] = useState<Tab>("graph");
  // Shared across Graph and Knowledge tabs: selecting a node in the graph
  // opens it here; navigating a [[wikilink]] here updates what's selected
  // back in the graph (docs/PLAN.md Phase 5).
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  // "Ask about this concept" (Phase 6) scopes the chat tab to a concept
  // until cleared, independent of the graph/knowledge selection above.
  const [chatContextSlug, setChatContextSlug] = useState<string | null>(null);

  function openConcept(slug: string) {
    setSelectedSlug(slug);
    setTab("knowledge");
  }

  function askAboutConcept(slug: string) {
    setChatContextSlug(slug);
    setTab("chat");
  }

  return (
    <main className="mx-auto max-w-6xl p-8">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-800">Synapse</h1>
          <p className="text-sm text-slate-500">Phase 6 — chat interface</p>
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

      {tab === "graph" && <Graph selectedSlug={selectedSlug} onSelectSlug={openConcept} />}
      {tab === "sources" && <Sources />}
      {tab === "knowledge" && (
        <Knowledge selectedSlug={selectedSlug} onSelectSlug={setSelectedSlug} onAskAboutConcept={askAboutConcept} />
      )}
      {tab === "chat" && (
        <Chat contextSlug={chatContextSlug} onClearContext={() => setChatContextSlug(null)} />
      )}
    </main>
  );
}
