import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../../api/client";
import {
  createDomain, deleteDomain, draftProfile, emptyProfile, updateDomain, type Domain, type DomainProfile,
} from "../../api/domains";
import { Button } from "../../design/Button";
import { Card } from "../../design/Card";
import { Field, TextArea, TextInput } from "../../design/Field";

interface DomainFormProps {
  /** The domain being edited, or null to add a new one. */
  domain: Domain | null;
  onDone: (message?: string) => void;
  onCancel: () => void;
}

const message = (e: unknown) => (e instanceof ApiError ? e.message : "Could not reach the backend.");

export function DomainForm({ domain, onDone, onCancel }: DomainFormProps) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(domain?.name ?? "");
  const [purpose, setPurpose] = useState(domain?.purpose ?? "");
  const [profile, setProfile] = useState<DomainProfile>(domain?.profile ?? emptyProfile());
  const [pasted, setPasted] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const patch = (p: Partial<DomainProfile>) => setProfile((cur) => ({ ...cur, ...p }));
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["domains"] });

  const save = useMutation({
    mutationFn: () => {
      const input = { name: name.trim(), purpose: purpose.trim(), profile: { ...profile, depth_sections: profile.depth_sections.filter((s) => s.trim()) } };
      return domain ? updateDomain(domain.slug, input) : createDomain(input);
    },
    onSuccess: async (saved) => {
      await refresh();
      onDone(saved.folder_existed ? `Saved. The folder ${saved.vault_path} already existed, so Synapse is using it as it is.` : "Saved.");
    },
  });
  const draft = useMutation({
    mutationFn: () => draftProfile({ name, purpose, ...profile, pasted_prompt: pasted.trim() || null }),
    onSuccess: (p) => setProfile(p),
  });
  const remove = useMutation({
    mutationFn: () => deleteDomain(domain!.slug),
    onSuccess: async () => {
      await refresh();
      onDone("Domain deleted. Its notes and folder are still on disk.");
    },
  });

  const sections = profile.depth_sections;
  const move = (i: number, by: -1 | 1) => {
    const next = [...sections];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    patch({ depth_sections: next });
  };

  return (
    <Card className="flex flex-col gap-6">
      <h3 className="text-lg font-semibold tracking-tight">{domain ? `Edit ${domain.name}` : "Add a domain"}</h3>

      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Name" hint={domain ? "Renaming does not rename the vault folder." : "The vault folder is named after it."}>
          {(c) => <TextInput {...c} value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label="Purpose" hint="One line. It is how auto-detect decides whether new material belongs here.">
          {(c) => <TextInput {...c} value={purpose} onChange={(e) => setPurpose(e.target.value)} />}
        </Field>
      </div>

      {domain ? (
        <p className="text-sm text-muted">
          Vault folder <span className="font-mono text-xs text-fg">{domain.vault_path}</span>
        </p>
      ) : null}

      <div className="flex flex-col gap-3 rounded-control border border-dashed border-line-strong p-4">
        <p className="text-sm font-semibold">Draft the profile with Claude</p>
        <p className="text-sm text-muted">
          Fill in whatever you know below (or paste the prompt you already use to study this subject), and Claude fills the gaps. Nothing is saved until you press Save.
        </p>
        <TextArea resizable={false} aria-label="Prompt to learn from" rows={3} placeholder="Optional: paste a study prompt" value={pasted} onChange={(e) => setPasted(e.target.value)} />
        <div className="flex items-center gap-3">
          <Button loading={draft.isPending} disabled={!name.trim() && !purpose.trim() && !pasted.trim() && !profile.objective.trim()} onClick={() => draft.mutate()}>
            Draft with Claude
          </Button>
          {draft.isError ? <span className="text-[13px] text-danger" role="alert">{message(draft.error)}</span> : null}
          {draft.isSuccess ? <span className="text-[13px] text-ok" role="status">Drafted. Read it over, edit it, then save.</span> : null}
        </div>
      </div>

      <Field label="Objective" hint="What the notes are for, and how deep they should go.">
        {(c) => <TextArea resizable={false} {...c} rows={3} value={profile.objective} onChange={(e) => patch({ objective: e.target.value })} />}
      </Field>

      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">Sections of a detailed note, in order</legend>
        <p className="-mt-1 text-[13px] text-muted">Write each as “Heading: what it covers”. A note leaves out a section it has nothing real to say for.</p>
        {sections.map((s, i) => (
          <div key={i} className="flex items-start gap-2">
            <TextArea resizable={false} aria-label={`Section ${i + 1}`} rows={2} className="min-w-0 flex-1" value={s} onChange={(e) => patch({ depth_sections: sections.map((x, j) => (j === i ? e.target.value : x)) })} />
            <Button size="sm" variant="ghost" disabled={i === 0} aria-label={`Move section ${i + 1} up`} onClick={() => move(i, -1)}>Up</Button>
            <Button size="sm" variant="ghost" disabled={i === sections.length - 1} aria-label={`Move section ${i + 1} down`} onClick={() => move(i, 1)}>Down</Button>
            <Button size="sm" variant="ghost" aria-label={`Remove section ${i + 1}`} onClick={() => patch({ depth_sections: sections.filter((_, j) => j !== i) })}>Remove</Button>
          </div>
        ))}
        <div>
          <Button size="sm" onClick={() => patch({ depth_sections: [...sections, ""] })}>Add a section</Button>
        </div>
      </fieldset>

      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="In scope" hint="Including the prerequisites a reader needs.">
          {(c) => <TextArea resizable={false} {...c} rows={4} value={profile.scope_include} onChange={(e) => patch({ scope_include: e.target.value })} />}
        </Field>
        <Field label="Mention only" hint="Gets one line at most, never its own note.">
          {(c) => <TextArea resizable={false} {...c} rows={4} value={profile.scope_mention_only} onChange={(e) => patch({ scope_mention_only: e.target.value })} />}
        </Field>
      </div>
      <Field label="Style" hint="Tone and writing rules.">
        {(c) => <TextArea resizable={false} {...c} rows={3} value={profile.style} onChange={(e) => patch({ style: e.target.value })} />}
      </Field>

      {save.isError || remove.isError ? (
        <p className="rounded-control bg-danger-soft px-4 py-2.5 text-sm text-danger" role="alert">
          {message(save.error ?? remove.error)}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
        <div className="flex gap-2">
          <Button variant="primary" loading={save.isPending} disabled={!name.trim()} onClick={() => save.mutate()}>Save</Button>
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
        </div>
        {domain ? (
          confirmDelete ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-muted">This removes the domain’s settings. Its notes and folder stay on disk.</span>
              <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>Delete domain</Button>
              <Button variant="ghost" onClick={() => setConfirmDelete(false)}>Keep it</Button>
            </div>
          ) : (
            <Button variant="ghost" onClick={() => setConfirmDelete(true)}>Delete domain</Button>
          )
        ) : null}
      </div>
    </Card>
  );
}
