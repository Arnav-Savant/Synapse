interface BreadcrumbProps {
  selectedNodeId: string | null;
  focusMode: boolean;
  focusDepth: number;
  onToggleFocus: (focus: boolean) => void;
}

export function Breadcrumb({ selectedNodeId, focusMode, focusDepth, onToggleFocus }: BreadcrumbProps) {
  if (!selectedNodeId) return null;

  return (
    <div className="flex items-center gap-3 font-mono text-xs text-graphite">
      <span className="flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full bg-spark" />
        {selectedNodeId}
      </span>
      <label className="flex items-center gap-1.5">
        <input type="checkbox" checked={focusMode} onChange={(e) => onToggleFocus(e.target.checked)} />
        focus view ({focusDepth}-hop)
      </label>
      {focusMode && (
        <button onClick={() => onToggleFocus(false)} className="text-spark hover:text-paper">
          ← back to global view
        </button>
      )}
    </div>
  );
}
