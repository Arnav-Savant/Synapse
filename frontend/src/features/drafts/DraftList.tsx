import type { Draft } from "../../api/jobs";
import { Chip } from "../../design/Chip";
import { draftKey } from "./draftDecision";

interface DraftListProps {
  drafts: Draft[];
  domainNames: Record<string, string>;
  selected: ReadonlySet<string>;
  activeKey: string | null;
  onToggle: (key: string) => void;
  onOpen: (key: string) => void;
}

/** Drafts grouped by vault, each group laid out as the topic's tree (children under their first parent). */
export function DraftList({ drafts, domainNames, selected, activeKey, onToggle, onOpen }: DraftListProps) {
  const slugs = [...new Set(drafts.map((d) => d.domain_slug))];
  return (
    <div className="flex flex-col gap-5">
      {slugs.map((slug) => {
        const group = drafts.filter((d) => d.domain_slug === slug);
        const titles = new Set(group.map((d) => d.title));
        const roots = group.filter((d) => !titles.has(d.parents[0] ?? ""));
        return (
          <section key={slug} aria-label={domainNames[slug] ?? slug}>
            {slugs.length > 1 ? <h3 className="mb-1 text-sm font-semibold text-muted">{domainNames[slug] ?? slug}</h3> : null}
            <ul className="flex flex-col">
              {roots.map((d) => (
                <Row key={draftKey(d)} draft={d} group={group} depth={0} {...{ selected, activeKey, onToggle, onOpen }} />
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

type RowProps = Pick<DraftListProps, "selected" | "activeKey" | "onToggle" | "onOpen"> & {
  draft: Draft;
  group: Draft[];
  depth: number;
};

function Row({ draft, group, depth, selected, activeKey, onToggle, onOpen }: RowProps) {
  const key = draftKey(draft);
  const kids = group.filter((d) => d.parents[0] === draft.title);
  const stale = draft.stage === "stale";
  const failed = draft.validator_flags.some((f) => f.code === "commit_failed");
  const flagged = draft.validator_flags.length > 0;
  return (
    <li>
      <div className={`flex items-start gap-2.5 rounded-control px-2 py-1.5 ${activeKey === key ? "bg-accent-soft" : "hover:bg-sunken"}`}>
        <input
          type="checkbox"
          className="mt-1 h-4 w-4 shrink-0 accent-[var(--accent)]"
          checked={selected.has(key)}
          disabled={stale}
          onChange={() => onToggle(key)}
          aria-label={`Approve ${draft.title}`}
        />
        <button type="button" onClick={() => onOpen(key)} className="min-w-0 flex-1 text-left" aria-current={activeKey === key}>
          <span className="block text-sm font-medium leading-snug">{draft.title}</span>
          <span className="mt-1 flex flex-wrap gap-1.5">
            {draft.kind === "merge" ? <Chip tone="info">Merges into existing</Chip> : null}
            {stale ? <Chip tone="info" dot="live">Being rebuilt</Chip> : null}
            {failed ? <Chip tone="danger">Not saved</Chip> : flagged ? <Chip tone="warn">{draft.validator_flags.length} to check</Chip> : null}
          </span>
        </button>
      </div>
      {kids.length > 0 ? (
        <ul className="ml-3 border-l border-line-strong pl-2">
          {kids.map((k) => (
            <Row key={draftKey(k)} draft={k} group={group} depth={depth + 1} {...{ selected, activeKey, onToggle, onOpen }} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}
