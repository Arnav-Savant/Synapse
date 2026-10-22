import type { Domain } from "../../api/domains";
import { Button } from "../../design/Button";
import { Card } from "../../design/Card";
import { EmptyState } from "../../design/EmptyState";

interface DomainListProps {
  domains: Domain[];
  onEdit: (domain: Domain) => void;
  onAdd: () => void;
}

export function DomainList({ domains, onEdit, onAdd }: DomainListProps) {
  if (domains.length === 0) {
    return (
      <EmptyState
        title="No domains yet"
        hint="A domain is an area you study, such as System Design. Each one gets its own vault folder and its own rules for how notes are written."
        action={<Button variant="primary" onClick={onAdd}>Add a domain</Button>}
      />
    );
  }
  return (
    <Card padded={false}>
      <ul className="divide-y divide-line">
        {domains.map((d) => (
          <li key={d.slug} className="flex items-center justify-between gap-4 px-5 py-4">
            <div className="min-w-0">
              <p className="font-medium">{d.name}</p>
              <p className="truncate text-sm text-muted">{d.purpose || "No purpose written yet"}</p>
              <p className="mt-0.5 truncate font-mono text-xs text-faint">{d.vault_path}</p>
            </div>
            <Button onClick={() => onEdit(d)}>Edit</Button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
