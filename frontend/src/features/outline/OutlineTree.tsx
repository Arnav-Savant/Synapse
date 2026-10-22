import { useState } from "react";

import type { OutlineNode, OverlapKind, Outline } from "../../api/jobs";
import { Button } from "../../design/Button";
import { TextInput } from "../../design/Field";
import { childrenByParent, subtreeKeys } from "./outlineTree";

interface OutlineTreeProps {
  tree: Outline;
  excluded: ReadonlySet<string>;
  /** Domain slug -> display name. */
  domainNames: Record<string, string>;
  /** Every domain this job can write to. Per-node domain toggles only show when there is more than one. */
  jobDomains: string[];
  /** Existing note id -> title, for the overlap badges. */
  noteTitles: ReadonlyMap<string, string>;
  onToggleExcluded: (key: string) => void;
  onAdd: (parentKey: string, title: string) => void;
  onToggleDomain: (key: string, slug: string) => void;
  onVerdict: (key: string, slug: string, kind: OverlapKind) => void;
}

const KIND_STYLE: Record<OverlapKind, string> = {
  same: "border-info/40 bg-info-soft text-info",
  partial: "border-line-strong bg-sunken text-fg",
  distinct: "border-transparent bg-sunken text-muted",
};

export function OutlineTree(props: OutlineTreeProps) {
  const children = childrenByParent(props.tree);
  const roots = children.get(null) ?? [];
  return (
    <ul role="tree" aria-label="Proposed notes" className="flex flex-col">
      {roots.map((n) => (
        <NodeRow key={n.key} node={n} depth={0} childMap={children} {...props} />
      ))}
    </ul>
  );
}

interface NodeRowProps extends OutlineTreeProps {
  node: OutlineNode;
  depth: number;
  childMap: Map<string | null, OutlineNode[]>;
}

function NodeRow(props: NodeRowProps) {
  const { node, depth, tree, excluded, domainNames, jobDomains } = props;
  const kids = props.childMap.get(node.key) ?? [];
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState("");
  const isRoot = node.parent_keys.length === 0;
  const dimmed = [...excluded].some((k) => subtreeKeys(tree, k).has(node.key));
  const own = excluded.has(node.key);

  function commit() {
    if (draft.trim()) props.onAdd(node.key, draft);
    setDraft("");
    setAdding(false);
  }

  return (
    <li role="treeitem" aria-expanded={kids.length ? true : undefined} aria-selected={false}>
      <div className={`flex gap-3 py-2.5 ${dimmed ? "opacity-45" : ""}`}>
        <input
          type="checkbox"
          className="mt-1 h-4 w-4 shrink-0 accent-[var(--accent)]"
          checked={!dimmed}
          disabled={isRoot || (dimmed && !own)}
          onChange={() => props.onToggleExcluded(node.key)}
          aria-label={`Include ${node.title}`}
          title={isRoot ? "The overview note anchors the topic and is always written." : undefined}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className={`font-medium ${dimmed ? "line-through" : ""}`}>{node.title}</span>
            {node.domains.map((slug) => (
              <VerdictBadge key={slug} {...props} slug={slug} showDomain={jobDomains.length > 1} />
            ))}
          </div>
          {node.summary ? <p className="mt-0.5 max-w-prose text-sm text-muted">{node.summary}</p> : null}
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            {jobDomains.length > 1
              ? jobDomains.map((slug) => {
                  const on = node.domains.includes(slug);
                  return (
                    <button
                      key={slug}
                      type="button"
                      aria-pressed={on}
                      onClick={() => props.onToggleDomain(node.key, slug)}
                      className={`rounded-full border px-2 py-0.5 text-xs font-medium transition-colors ${
                        on ? "border-accent/50 bg-accent-soft text-accent" : "border-line-strong text-faint line-through hover:text-muted"
                      }`}
                    >
                      {domainNames[slug] ?? slug}
                    </button>
                  );
                })
              : null}
            {!dimmed ? (
              <button type="button" className="text-xs font-medium text-muted hover:text-accent" onClick={() => setAdding(true)}>
                Add subtopic
              </button>
            ) : null}
          </div>
          {adding ? (
            <form
              className="mt-2 flex max-w-md items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                commit();
              }}
            >
              <TextInput
                autoFocus
                aria-label={`New subtopic under ${node.title}`}
                placeholder="Subtopic title"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => e.key === "Escape" && (setDraft(""), setAdding(false))}
              />
              <Button type="submit" size="sm" variant="primary" disabled={!draft.trim()}>
                Add
              </Button>
              <Button size="sm" variant="ghost" onClick={() => (setDraft(""), setAdding(false))}>
                Cancel
              </Button>
            </form>
          ) : null}
        </div>
      </div>
      {kids.length > 0 ? (
        <ul role="group" className="ml-2 border-l border-line-strong pl-5">
          {kids.map((k) => (
            <NodeRow key={k.key} {...props} node={k} depth={depth + 1} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function VerdictBadge({
  node, slug, showDomain, noteTitles, domainNames, onVerdict,
}: NodeRowProps & { slug: string; showDomain: boolean }) {
  const verdict = node.verdicts[slug];
  const kind: OverlapKind = verdict?.kind ?? "distinct";
  const target = verdict?.target_note_id ? noteTitles.get(verdict.target_note_id) : undefined;
  const hasTarget = Boolean(verdict?.target_note_id);
  const prefix = showDomain ? `${domainNames[slug] ?? slug}: ` : "";
  const label = {
    distinct: "New note",
    same: `Merges into [[${target ?? "an existing note"}]]`,
    partial: `New note, links to [[${target ?? "an existing note"}]]`,
  };

  if (!hasTarget) {
    return <span className={`rounded-full border px-2 py-0.5 text-xs ${KIND_STYLE.distinct}`}>{prefix}New note</span>;
  }
  return (
    <select
      aria-label={`How ${node.title} relates to existing notes${showDomain ? ` in ${domainNames[slug] ?? slug}` : ""}`}
      title={verdict?.reason || undefined}
      value={kind}
      onChange={(e) => onVerdict(node.key, slug, e.target.value as OverlapKind)}
      className={`max-w-full cursor-pointer rounded-full border px-2 py-0.5 text-xs font-medium ${KIND_STYLE[kind]}`}
    >
      <option value="distinct">{prefix}New note</option>
      <option value="same">{prefix}{label.same}</option>
      <option value="partial">{prefix}{label.partial}</option>
    </select>
  );
}
