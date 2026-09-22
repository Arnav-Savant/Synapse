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
    <div className="space-y-3">
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={20}
        className="w-full border border-paper-line bg-paper-soft p-3 font-mono text-xs text-paper-ink focus:border-spark-dim focus:outline-none"
      />
      <div className="flex items-center gap-4 font-mono text-xs">
        <button
          onClick={() => onSave(content)}
          disabled={isSaving}
          className="bg-paper-ink px-4 py-1.5 text-paper disabled:opacity-50"
        >
          {isSaving ? "saving…" : "save"}
        </button>
        <button onClick={onCancel} disabled={isSaving} className="text-paper-ink/60 hover:text-paper-ink">
          cancel
        </button>
        {error && <span className="text-rose-700">{error}</span>}
      </div>
    </div>
  );
}
