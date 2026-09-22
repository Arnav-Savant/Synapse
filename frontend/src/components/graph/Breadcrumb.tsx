interface BreadcrumbProps {
  selectedNodeId: string | null;
  focusMode: boolean;
  focusDepth: number;
  onToggleFocus: (focus: boolean) => void;
}

export function Breadcrumb({ selectedNodeId, focusMode, focusDepth, onToggleFocus }: BreadcrumbProps) {
  if (!selectedNodeId) return null;

  return (
    <div className="flex items-center gap-3 text-sm text-slate-600">
      <span>
        Selected: <span className="font-medium text-slate-800">{selectedNodeId}</span>
      </span>
      <label className="flex items-center gap-1.5">
        <input type="checkbox" checked={focusMode} onChange={(e) => onToggleFocus(e.target.checked)} />
        Focus view ({focusDepth}-hop neighborhood)
      </label>
      {focusMode && (
        <button
          onClick={() => onToggleFocus(false)}
          className="rounded border border-slate-300 px-2 py-0.5 text-xs hover:bg-slate-50"
        >
          ← back to global view
        </button>
      )}
    </div>
  );
}
