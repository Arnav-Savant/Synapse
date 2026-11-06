import type { Ancestor, ParentInfo, NoteBrief } from "../../api/jobs";
import { Button } from "../../design/Button";
import { Card } from "../../design/Card";
import { Chip } from "../../design/Chip";
import { SelectInput, TextInput } from "../../design/Field";

const MAX_LEVELS = 2;
const NEW_PARENT = "__new__";

interface PlacementEditorProps {
  domainName: string;
  topicTitle: string;
  ancestors: Ancestor[];
  attached: string[];
  parents: ParentInfo[];
  notes: NoteBrief[];
  onAncestors: (ancestors: Ancestor[]) => void;
  onToggleNote: (noteId: string) => void;
}

const newParent = (): Ancestor => ({ title: "", summary: "", existing_note_id: null });

/** The parent notes that may sit at `level`: an existing parent inside an existing parent must really sit under it. */
function parentsForLevel(level: number, ancestors: Ancestor[], parents: ParentInfo[]): ParentInfo[] {
  if (level === 0) return parents;
  const outer = ancestors[level - 1];
  if (!outer.existing_note_id) return [];
  return parents.filter((p) => p.parent_title?.toLowerCase() === outer.title.toLowerCase());
}

/** Where the topic sits above its top note: up to two parent levels, and existing notes that join it there. */
export function PlacementEditor(props: PlacementEditorProps) {
  const { domainName, topicTitle, ancestors, attached, parents, notes, onAncestors, onToggleNote } = props;
  const attachable = notes.filter((n) => !ancestors.some((a) => a.existing_note_id === n.id));
  const replace = (i: number, value: Ancestor) => onAncestors(ancestors.map((a, j) => (j === i ? value : a)));
  const innermost = ancestors[ancestors.length - 1];

  return (
    <Card>
      <h2 className="font-semibold">Where this topic sits in {domainName}</h2>
      <p className="mt-0.5 max-w-prose text-sm text-muted">
        A parent note is a short overview that groups related topics. Up to two levels can sit above the topic, or none.
      </p>

      <div className="mt-4 flex flex-col gap-3">
        {ancestors.map((a, i) => {
          const allowed = parentsForLevel(i, ancestors, parents);
          const current = parents.find((p) => p.id === a.existing_note_id);
          // Keep the chosen parent visible even when it cannot sit here, and say why.
          const misplaced = current !== undefined && !allowed.some((p) => p.id === current.id);
          const options = misplaced ? [current, ...allowed] : allowed;
          const isNew = !a.existing_note_id;
          return (
            <div key={i} className="flex flex-wrap items-start gap-3" style={{ marginLeft: i * 20 }}>
              <div className="flex min-w-0 flex-1 flex-col gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <SelectInput
                    aria-label={`Parent level ${i + 1}`}
                    value={a.existing_note_id ?? NEW_PARENT}
                    className="max-w-72"
                    onChange={(e) => {
                      const parent = parents.find((p) => p.id === e.target.value);
                      replace(i, parent ? { title: parent.title, summary: parent.summary, existing_note_id: parent.id } : newParent());
                    }}
                  >
                    {options.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.title}
                      </option>
                    ))}
                    <option value={NEW_PARENT}>New parent…</option>
                  </SelectInput>
                  <Chip tone={isNew ? "warn" : "neutral"}>{isNew ? "New parent" : "Existing parent"}</Chip>
                  <Button size="sm" variant="ghost" onClick={() => onAncestors(ancestors.filter((_, j) => j !== i))}>
                    Remove
                  </Button>
                </div>
                {misplaced ? (
                  <p className="text-[13px] text-danger" role="alert">
                    {ancestors[i - 1]?.existing_note_id
                      ? `${a.title} does not sit under ${ancestors[i - 1].title}.`
                      : `${a.title} already exists, so it cannot sit under a new parent.`}{" "}
                    Remove this level or change the parent above it.
                  </p>
                ) : null}
                {isNew ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    <TextInput aria-label={`Title of parent level ${i + 1}`} placeholder="Parent title" value={a.title} onChange={(e) => replace(i, { ...a, title: e.target.value })} />
                    <TextInput aria-label={`Summary of parent level ${i + 1}`} placeholder="One line on what it covers" value={a.summary} onChange={(e) => replace(i, { ...a, summary: e.target.value })} />
                  </div>
                ) : a.summary ? (
                  <p className="text-sm text-muted">{a.summary}</p>
                ) : null}
              </div>
            </div>
          );
        })}
        <div className="flex items-center gap-2 text-sm" style={{ marginLeft: ancestors.length * 20 }}>
          <span className="h-px w-4 bg-line-strong" aria-hidden="true" />
          <span className="font-medium">{topicTitle}</span>
          <span className="text-muted">(this topic)</span>
        </div>
      </div>

      {ancestors.length < MAX_LEVELS ? (
        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" onClick={() => onAncestors([newParent(), ...ancestors])}>
            {ancestors.length === 0 ? "Add a parent" : "Add a parent above"}
          </Button>
          {ancestors.length > 0 ? (
            <Button size="sm" onClick={() => onAncestors([...ancestors, newParent()])}>
              Add a parent below
            </Button>
          ) : null}
        </div>
      ) : null}
      {ancestors.length === 0 ? <p className="mt-3 text-sm text-muted">No parent: this topic stands at the top level.</p> : null}

      {innermost && attachable.length > 0 ? (
        <fieldset className="mt-5 border-t border-line pt-4">
          <legend className="text-sm font-medium">Attach existing notes under “{innermost.title || "the new parent"}”</legend>
          <p className="mb-2 text-[13px] text-muted">Only their parent link changes; their text is not touched.</p>
          <ul className="flex flex-col gap-1.5">
            {attachable.map((n) => (
              <li key={n.id}>
                <label className="flex items-start gap-2.5 text-sm">
                  <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[var(--accent)]" checked={attached.includes(n.id)} onChange={() => onToggleNote(n.id)} />
                  <span>
                    <span className="font-medium">{n.title}</span>
                    {n.summary ? <span className="block text-muted">{n.summary}</span> : null}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
      ) : null}
    </Card>
  );
}
