import { useState } from "react";

interface EditFormProps {
  initialContent: string;
  onSave: (content: string) => void;
  onCancel: () => void;
  isSaving: boolean;
  error: string | null;
}

/** Edits the whole raw file (frontmatter + body) as one text blob — no
 * structured frontmatter editor yet (not required by Phase 5's scope; see
 * docs/ARCHITECTURE.md §4.1). The backend refreshes `updated` and
 * validates the frontmatter regardless of what's typed here. */
export function EditForm({ initialContent, onSave, onCancel, isSaving, error }: EditFormProps) {
  const [content, setContent] = useState(initialContent);

  return (
    <div className="space-y-2">
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={20}
        className="w-full rounded-md border border-slate-300 p-3 font-mono text-xs focus:border-slate-500 focus:outline-none"
      />
      <div className="flex items-center gap-2">
        <button
          onClick={() => onSave(content)}
          disabled={isSaving}
          className="rounded-md bg-slate-800 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {isSaving ? "Saving…" : "Save"}
        </button>
        <button
          onClick={onCancel}
          disabled={isSaving}
          className="rounded-md border border-slate-300 px-4 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
        >
          Cancel
        </button>
        {error && <span className="text-sm text-red-600">{error}</span>}
      </div>
    </div>
  );
}
