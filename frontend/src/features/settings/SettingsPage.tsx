import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchAgentConfigs, fetchModels } from "../../api/agentConfig";
import { listDomains, type Domain } from "../../api/domains";
import { Button } from "../../design/Button";
import { Card } from "../../design/Card";
import { EmptyState } from "../../design/EmptyState";
import { LoadingBlock } from "../../design/Spinner";
import { PageFrame } from "../../shell/PageFrame";
import { DomainForm } from "./DomainForm";
import { DomainList } from "./DomainList";
import { ModelConfigRow } from "./ModelConfigRow";
import { ROLE_INFO } from "./roles";

type Section = "domains" | "models";
type Editing = { domain: Domain | null } | null;

export function SettingsPage() {
  const [section, setSection] = useState<Section>("domains");
  const [editing, setEditing] = useState<Editing>(null);
  const [notice, setNotice] = useState<string | null>(null);

  return (
    <PageFrame title="Settings" description="Which vaults exist and how their notes are written, and which Claude model does each job.">
      <div className="mb-6 inline-flex rounded-control border border-line-strong p-0.5" role="tablist" aria-label="Settings sections">
        {([["domains", "Domains"], ["models", "Models"]] as [Section, string][]).map(([id, label]) => (
          <button
            key={id}
            role="tab"
            type="button"
            aria-selected={section === id}
            onClick={() => {
              setSection(id);
              setNotice(null);
            }}
            className={`rounded-[4px] px-4 py-1.5 text-sm font-medium transition-colors ${section === id ? "bg-accent text-accent-fg" : "text-muted hover:text-fg"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {notice ? (
        <p className="mb-4 rounded-control bg-ok-soft px-4 py-2.5 text-sm text-ok" role="status">{notice}</p>
      ) : null}
      {section === "models" ? <Models /> : <Domains editing={editing} setEditing={setEditing} setNotice={setNotice} />}
    </PageFrame>
  );
}

function Models() {
  const configs = useQuery({ queryKey: ["agent-configs"], queryFn: fetchAgentConfigs });
  const models = useQuery({ queryKey: ["agent-models"], queryFn: fetchModels, staleTime: Infinity });
  if (configs.isLoading || models.isLoading) return <LoadingBlock label="Loading model settings" />;
  if (configs.isError || models.isError) {
    const error = configs.error ?? models.error;
    return <EmptyState tone="error" title="Could not load the model settings" hint={`${error?.message} Check that the backend is running.`} action={<Button onClick={() => { configs.refetch(); models.refetch(); }}>Try again</Button>} />;
  }
  const order = Object.keys(ROLE_INFO);
  const rows = [...configs.data!].sort((a, b) => order.indexOf(a.agent_role) - order.indexOf(b.agent_role));
  return (
    <Card padded={false}>
      <ul className="divide-y divide-line">
        {rows.map((c) => (
          <ModelConfigRow key={c.agent_role} config={c} models={models.data!} />
        ))}
      </ul>
    </Card>
  );
}

function Domains({ editing, setEditing, setNotice }: { editing: Editing; setEditing: (e: Editing) => void; setNotice: (m: string | null) => void }) {
  const domains = useQuery({ queryKey: ["domains"], queryFn: listDomains });
  if (editing) {
    return (
      <DomainForm
        key={editing.domain?.slug ?? "new"}
        domain={editing.domain}
        onCancel={() => setEditing(null)}
        onDone={(m) => {
          setEditing(null);
          setNotice(m ?? null);
        }}
      />
    );
  }
  if (domains.isLoading) return <LoadingBlock label="Loading domains" />;
  if (domains.isError) {
    return <EmptyState tone="error" title="Could not load your domains" hint={`${domains.error.message} Check that the backend is running.`} action={<Button onClick={() => domains.refetch()}>Try again</Button>} />;
  }
  return (
    <div className="flex flex-col gap-4">
      <div>
        <Button variant="primary" onClick={() => { setNotice(null); setEditing({ domain: null }); }}>
          Add a domain
        </Button>
      </div>
      <DomainList domains={domains.data!} onAdd={() => setEditing({ domain: null })} onEdit={(d) => { setNotice(null); setEditing({ domain: d }); }} />
    </div>
  );
}
