import { useState } from "react";

import { ChatDock } from "./components/chat/ChatDock";
import { GraphView } from "./components/graph/GraphView";
import { SearchBox } from "./components/graph/SearchBox";
import { ConceptPanel } from "./components/knowledge/ConceptPanel";
import { LibraryDock } from "./components/knowledge/LibraryDock";
import { SettingsModal } from "./components/settings/SettingsModal";
import { QuickAddOverlay } from "./components/sources/QuickAddOverlay";
import { useGraphData } from "./hooks/useGraphData";
import { HealthBadge } from "./routes/HealthBadge";

export function App() {
  // Shared across the graph canvas and the knowledge/paper panel: selecting
  // a node here opens it there; navigating a [[wikilink]] there updates
  // what's selected back here (docs/PLAN.md Phase 5).
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  // "Ask about this concept" (Phase 6) scopes the chat dock to a concept
  // until cleared, independent of the graph/knowledge selection above.
  const [chatContextSlug, setChatContextSlug] = useState<string | null>(null);
  // Quick-add compose overlay (replaces the old full-page Sources tab) —
  // not kept mounted while closed, so each open starts from a blank form.
  const [composeOpen, setComposeOpen] = useState(false);
  // Settings overlay (agent configuration) — a separate transient modal
  // from the compose overlay above, opened only from the header's gear icon.
  const [settingsOpen, setSettingsOpen] = useState(false);

  const graph = useGraphData();
  const [searchQuery, setSearchQuery] = useState("");

  function selectNode(nodeId: string) {
    setSearchQuery("");
    setSelectedSlug(nodeId);
  }

  return (
    <div className="flex h-screen flex-col bg-ink">
      <header className="flex items-center justify-between gap-6 border-b border-ink-line px-6 py-3">
        <div className="flex items-center gap-2.5">
          <span className="h-2 w-2 rounded-full bg-spark shadow-[0_0_8px_2px_rgba(217,164,65,0.5)]" />
          <h1 className="font-mono text-sm tracking-wide text-paper">synapse</h1>
        </div>

        <div className="flex flex-1 justify-center">
          <SearchBox nodes={graph.nodes} query={searchQuery} onQueryChange={setSearchQuery} onSelect={selectNode} />
        </div>

        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => setComposeOpen(true)}
            aria-label="add source"
            className="font-mono text-sm text-graphite hover:text-paper"
          >
            +
          </button>
          <HealthBadge />
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            aria-label="settings"
            className="font-mono text-sm text-graphite hover:text-paper"
          >
            ⚙
          </button>
        </div>
      </header>

      <main className="flex flex-1 overflow-hidden">
        <LibraryDock
          nodes={graph.nodes}
          edges={graph.edges}
          isPending={graph.isPending}
          isError={graph.isError}
          selectedSlug={selectedSlug}
          onSelect={selectNode}
        />

        {/* Own positioning context for GraphView's floating filter/breadcrumb
            cluster and ConceptPanel's slide-over, kept separate from
            LibraryDock (a real flex sibling, not an overlay) so neither one
            has to know about the other's width/state to avoid colliding. */}
        <div className="relative flex-1 overflow-hidden">
          <GraphView
            nodes={graph.nodes}
            edges={graph.edges}
            isPending={graph.isPending}
            isError={graph.isError}
            selectedNodeId={selectedSlug}
            onSelectNode={selectNode}
          />
          <ConceptPanel
            slug={selectedSlug}
            onClose={() => setSelectedSlug(null)}
            onNavigate={setSelectedSlug}
            onAskAboutConcept={setChatContextSlug}
          />
        </div>
      </main>

      <ChatDock contextSlug={chatContextSlug} onClearContext={() => setChatContextSlug(null)} />

      {composeOpen && <QuickAddOverlay onClose={() => setComposeOpen(false)} />}
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}
