import type { Ancestor, HubInfo, NoteBrief } from "../../api/jobs";
import { Button } from "../../design/Button";
import { Card } from "../../design/Card";
import { Chip } from "../../design/Chip";
import { SelectInput, TextInput } from "../../design/Field";

const MAX_LEVELS = 2;
const NEW_HUB = "__new__";

interface PlacementEditorProps {
  domainName: string;
  topicTitle: string;
  ancestors: Ancestor[];
  attached: string[];
  hubs: HubInfo[];
  notes: NoteBrief[];
  onAncestors: (ancestors: Ancestor[]) => void;
  onToggleNote: (noteId: string) => void;
}

const newHub = (): Ancestor => ({ title: "", summary: "", existing_note_id: null });

/** The hubs that may sit at `level`: an existing hub inside an existing hub must really sit under it. */
function hubsForLevel(level: number, ancestors: Ancestor[], hubs: HubInfo[]): HubInfo[] {
  if (level === 0) return hubs;
  const outer = ancestors[level - 1];
  if (!outer.existing_note_id) return [];
  return hubs.filter((h) => h.parent_title?.toLowerCase() === outer.title.toLowerCase());
}

/** Where the topic sits above its top note: up to two hub levels, and existing notes that join it there. */
export function PlacementEditor(props: PlacementEditorProps) {
  const { domainName, topicTitle, ancestors, attached, hubs, notes, onAncestors, onToggleNote } = props;
  const replace = (i: number, value: Ancestor) => onAncestors(ancestors.map((a, j) => (j === i ? value : a)));
  const innermost = ancestors[ancestors.length - 1];

  return (
    <Card>
      <h2 className="font-semibold">Where this topic sits in {domainName}</h2>
      <p className="mt-0.5 max-w-prose text-sm text-muted">
        A hub is a short overview note that groups related topics. Up to two levels can sit above the topic, or none.
      </p>

      <div className="mt-4 flex flex-col gap-3">
        {ancestors.map((a, i) => {
          const allowed = hubsForLevel(i, ancestors, hubs);
          const current = hubs.find((h) => h.id === a.existing_note_id);
          // Keep the chosen hub visible even when it cannot sit here, and say why.
          const misplaced = current !== undefined && !allowed.some((h) => h.id === current.id);
          const options = misplaced ? [current, ...allowed] : allowed;
          const isNew = !a.existing_note_id;
          return (
            <div key={i} className="flex flex-wrap items-start gap-3" style={{ marginLeft: i * 20 }}>
              <div className="flex min-w-0 flex-1 flex-col gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <SelectInput
                    aria-label={`Hub level ${i + 1}`}
                    value={a.existing_note_id ?? NEW_HUB}
                    className="max-w-72"
                    onChange={(e) => {
                      const hub = hubs.find((h) => h.id === e.target.value);
                      replace(i, hub ? { title: hub.title, summary: hub.summary, existing_note_id: hub.id } : newHub());
                    }}
                  >
                    {options.map((h) => (
                      <option key={h.id} value={h.id}>
                        {h.title}
                      </option>
                    ))}
                    <option value={NEW_HUB}>New hub…</option>
                  </SelectInput>
                  <Chip tone={isNew ? "warn" : "neutral"}>{isNew ? "New hub" : "Existing hub"}</Chip>
                  <Button size="sm" variant="ghost" onClick={() => onAncestors(ancestors.filter((_, j) => j !== i))}>
                    Remove
                  </Button>
                </div>
                {misplaced ? (
                  <p className="text-[13px] text-danger" role="alert">
                    {ancestors[i - 1]?.existing_note_id
                      ? `${a.title} does not sit under ${ancestors[i - 1].title}.`
                      : `${a.title} already exists, so it cannot sit under a new hub.`}{" "}
                    Remove this level or change the hub above it.
                  </p>
                ) : null}
                {isNew ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    <TextInput aria-label={`Title of hub level ${i + 1}`} placeholder="Hub title" value={a.title} onChange={(e) => replace(i, { ...a, title: e.target.value })} />
                    <TextInput aria-label={`Summary of hub level ${i + 1}`} placeholder="One line on what it covers" value={a.summary} onChange={(e) => replace(i, { ...a, summary: e.target.value })} />
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
          <Button size="sm" onClick={() => onAncestors([newHub(), ...ancestors])}>
            {ancestors.length === 0 ? "Add a hub" : "Add a hub above"}
          </Button>
          {ancestors.length > 0 ? (
            <Button size="sm" onClick={() => onAncestors([...ancestors, newHub()])}>
              Add a hub below
            </Button>
          ) : null}
        </div>
      ) : null}
      {ancestors.length === 0 ? <p className="mt-3 text-sm text-muted">No hub: this topic stands at the top level.</p> : null}

      {innermost && notes.length > 0 ? (
        <fieldset className="mt-5 border-t border-line pt-4">
          <legend className="text-sm font-medium">Attach existing notes under “{innermost.title || "the new hub"}”</legend>
          <p className="mb-2 text-[13px] text-muted">Only their parent link changes; their text is not touched.</p>
          <ul className="flex flex-col gap-1.5">
            {notes.map((n) => (
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
