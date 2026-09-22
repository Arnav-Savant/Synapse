import { useState } from "react";

import { Chat } from "./routes/Chat";
import { Graph } from "./routes/Graph";
import { HealthBadge } from "./routes/HealthBadge";
import { Knowledge } from "./routes/Knowledge";
import { Sources } from "./routes/Sources";

type Tab = "graph" | "sources" | "knowledge" | "chat";

const TABS: { id: Tab; label: string }[] = [
  { id: "graph", label: "graph" },
  { id: "sources", label: "sources" },
  { id: "knowledge", label: "knowledge" },
  { id: "chat", label: "chat" },
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
    <div className="min-h-screen bg-ink">
      <main className="mx-auto max-w-6xl p-8">
        <header className="mb-8 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="h-2 w-2 rounded-full bg-spark shadow-[0_0_8px_2px_rgba(217,164,65,0.5)]" />
            <h1 className="font-mono text-sm tracking-wide text-paper">synapse</h1>
          </div>
          <HealthBadge />
        </header>

        <nav className="mb-8 flex gap-6 border-b border-ink-line font-mono text-xs">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`-mb-px border-b pb-2 ${
                tab === id ? "border-spark text-spark" : "border-transparent text-graphite hover:text-paper"
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
        {tab === "chat" && <Chat contextSlug={chatContextSlug} onClearContext={() => setChatContextSlug(null)} />}
      </main>
    </div>
  );
}
