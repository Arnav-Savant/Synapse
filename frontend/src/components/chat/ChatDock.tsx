import { useState } from "react";

import { IconButton } from "../ui/IconButton";
import { ChatIcon, XIcon } from "../ui/icons";
import { ChatPanel } from "./ChatPanel";

interface ChatDockProps {
  /** Set via ConceptPanel's "ask about this concept" (App.tsx) — arriving
   * here non-null should both expand the dock and scope the chat session,
   * same as clearing it should leave the dock open but drop the scope. */
  contextSlug: string | null;
  onClearContext: () => void;
}

/**
 * Persistent chat affordance, collapsed to a small pill by default.
 *
 * Deliberately NOT a full-height right-edge dock like ConceptPanel: that
 * would either duplicate ConceptPanel's own slide-over space (right edge,
 * full height, up to 640px wide) or force both to negotiate width/z-index
 * every time either one opens. Instead this floats as a compact panel
 * anchored to the bottom-right corner of the viewport, well short of
 * ConceptPanel's height, with a higher z-index — when both happen to be
 * open at once, chat is a small overlay bubble sitting on top of the
 * bottom corner of ConceptPanel rather than two docks fighting for the
 * same full-height strip. See App.tsx for how the two are composed.
 */
export function ChatDock({ contextSlug, onClearContext }: ChatDockProps) {
  const [expanded, setExpanded] = useState(false);
  // Adjusting state in response to a prop change during render (rather than
  // in an Effect) per React's own guidance — this only needs to run once
  // per contextSlug change, not resync on every render.
  const [lastContextSlug, setLastContextSlug] = useState(contextSlug);
  if (contextSlug !== lastContextSlug) {
    setLastContextSlug(contextSlug);
    // "Ask about this concept" should surface the dock, not just set state
    // invisibly behind a collapsed pill.
    if (contextSlug) setExpanded(true);
  }

  if (!expanded) {
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        aria-label="Open chat"
        className="fixed bottom-5 right-5 z-30 flex items-center gap-2.5 rounded-sm border border-ink-line bg-ink-soft px-4 py-3 font-mono text-sm text-graphite shadow-[0_8px_24px_-8px_rgba(0,0,0,0.6)] transition-colors hover:border-spark-dim hover:text-paper"
      >
        <ChatIcon className="h-5 w-5" />
        chat
        {contextSlug && <span className="h-2 w-2 rounded-full bg-spark" />}
      </button>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-30 flex max-h-[80vh] w-[400px] max-w-[calc(100vw-2rem)] flex-col border border-ink-line bg-ink-soft shadow-[0_20px_60px_-20px_rgba(0,0,0,0.6)]">
      <div className="flex shrink-0 items-center justify-between border-b border-ink-line py-1.5 pl-3 pr-1.5">
        <span className="flex items-center gap-2 font-mono text-sm text-graphite">
          <ChatIcon className="h-4 w-4" />
          chat
        </span>
        <IconButton icon={<XIcon />} aria-label="Collapse chat" title="Collapse chat" onClick={() => setExpanded(false)} size="md" />
      </div>
      <div className="overflow-y-auto p-3">
        <ChatPanel contextSlug={contextSlug} onClearContext={onClearContext} />
      </div>
    </div>
  );
}
