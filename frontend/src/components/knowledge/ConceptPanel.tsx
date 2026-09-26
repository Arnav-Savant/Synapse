import { KnowledgeViewer } from "./KnowledgeViewer";

interface ConceptPanelProps {
  /** null hides the panel entirely — there is no "keep it in the graph but
   * hide the panel" state; closing and clearing the selection are the same
   * action (see the parent's onClose). */
  slug: string | null;
  onClose: () => void;
  onNavigate: (slug: string) => void;
  onAskAboutConcept: (slug: string) => void;
}

/** Right-edge slide-over that hosts KnowledgeViewer over the graph canvas.
 * Stays mounted (rather than unmounting on close) purely so the
 * slide-out transition has something to animate — content only renders
 * once a slug is selected. */
export function ConceptPanel({ slug, onClose, onNavigate, onAskAboutConcept }: ConceptPanelProps) {
  return (
    <div
      className={`absolute right-0 top-0 z-20 h-full w-full max-w-[640px] overflow-y-auto border-l border-ink-line bg-paper shadow-[0_20px_60px_-20px_rgba(0,0,0,0.6)] transition-transform duration-300 ease-out ${
        slug ? "translate-x-0" : "translate-x-full"
      }`}
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="close"
        className="absolute right-4 top-4 z-10 font-mono text-lg text-paper-ink/50 hover:text-paper-ink"
      >
        ×
      </button>

      {slug && (
        <div className="p-6 pt-14">
          <KnowledgeViewer slug={slug} onNavigate={onNavigate} onAskAboutConcept={onAskAboutConcept} onDeleted={onClose} />
        </div>
      )}
    </div>
  );
}
