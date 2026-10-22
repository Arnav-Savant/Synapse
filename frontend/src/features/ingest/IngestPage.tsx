import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../../api/client";
import { listDomains } from "../../api/domains";
import { createJob, type InputKind } from "../../api/jobs";
import { Button } from "../../design/Button";
import { Card } from "../../design/Card";
import { EmptyState } from "../../design/EmptyState";
import { Field, SelectInput, TextArea } from "../../design/Field";
import { LoadingBlock } from "../../design/Spinner";
import { PageFrame } from "../../shell/PageFrame";
import { JOBS_QUERY_KEY } from "../jobs/useJobs";

const MAX_CHARS = 200_000;

const MODES: { kind: InputKind; label: string; help: string; placeholder: string; rows: number }[] = [
  {
    kind: "content",
    label: "Paste material",
    help: "Paste notes, an article or a transcript. Synapse works out the topic and splits it into a tree of linked notes.",
    placeholder: "Paste your notes here…",
    rows: 14,
  },
  {
    kind: "topic",
    label: "Topic only",
    help: "Name something you want to learn. Synapse researches it, proposes an outline for you to approve, then writes the notes.",
    placeholder: "For example: database isolation levels",
    rows: 3,
  },
];

export function IngestPage({ onSubmitted }: { onSubmitted: () => void }) {
  const queryClient = useQueryClient();
  const domains = useQuery({ queryKey: ["domains"], queryFn: listDomains });
  const [kind, setKind] = useState<InputKind>("topic");
  const [text, setText] = useState("");
  const [domain, setDomain] = useState("auto");

  const submit = useMutation({
    mutationFn: () => createJob({ input_kind: kind, text, domain_choice: domain }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: JOBS_QUERY_KEY });
      setText("");
      onSubmitted();
    },
  });

  const mode = MODES.find((m) => m.kind === kind)!;
  const tooLong = text.length > MAX_CHARS;
  const empty = text.trim().length === 0;
  const serverError = submit.error ? (submit.error instanceof ApiError ? submit.error.message : "Could not reach the backend.") : null;
  const fieldError = tooLong ? `That is ${text.length.toLocaleString()} characters; the limit is ${MAX_CHARS.toLocaleString()}. Split it into smaller submissions.` : serverError;

  return (
    <PageFrame title="Ingest" description="Turn a topic or some pasted material into linked notes in one of your vaults.">
      {domains.isLoading ? (
        <LoadingBlock label="Loading domains" />
      ) : domains.isError ? (
        <EmptyState tone="error" title="Could not load your domains" hint={`${domains.error.message} Check that the backend is running, then reload.`} />
      ) : domains.data!.length === 0 ? (
        <EmptyState title="Create a domain first" hint="Notes are written into a vault per domain. Add one in Settings, then come back." />
      ) : (
        <Card className="max-w-3xl">
          <form
            className="flex flex-col gap-6"
            onSubmit={(e) => {
              e.preventDefault();
              if (!empty && !tooLong) submit.mutate();
            }}
          >
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1.5 text-sm font-medium">What are you submitting?</legend>
              <div className="inline-flex w-fit rounded-control border border-line-strong p-0.5" role="radiogroup" aria-label="Input type">
                {MODES.map((m) => (
                  <label
                    key={m.kind}
                    className={`cursor-pointer rounded-[4px] px-3.5 py-1.5 text-sm font-medium transition-colors has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent ${
                      kind === m.kind ? "bg-accent text-accent-fg" : "text-muted hover:text-fg"
                    }`}
                  >
                    <input type="radio" name="kind" value={m.kind} checked={kind === m.kind} onChange={() => setKind(m.kind)} className="sr-only" />
                    {m.label}
                  </label>
                ))}
              </div>
              <p className="max-w-prose text-sm text-muted">{mode.help}</p>
            </fieldset>

            <Field label={kind === "topic" ? "Topic" : "Material"} error={fieldError}>
              {(c) => <TextArea {...c} value={text} rows={mode.rows} placeholder={mode.placeholder} onChange={(e) => setText(e.target.value)} />}
            </Field>
            {kind === "content" && text.length > 0 ? (
              <p className={`-mt-4 text-xs ${tooLong ? "text-danger" : "text-faint"}`}>
                {text.length.toLocaleString()} of {MAX_CHARS.toLocaleString()} characters
              </p>
            ) : null}

            <Field label="Domain" hint="Auto-detect picks the vault from what you submit; you can confirm it before anything is written.">
              {(c) => (
                <SelectInput {...c} value={domain} onChange={(e) => setDomain(e.target.value)} className="max-w-xs">
                  <option value="auto">Auto-detect</option>
                  {domains.data!.map((d) => (
                    <option key={d.slug} value={d.slug}>
                      {d.name}
                    </option>
                  ))}
                </SelectInput>
              )}
            </Field>

            <div>
              <Button type="submit" variant="primary" loading={submit.isPending} disabled={empty || tooLong}>
                Start
              </Button>
            </div>
          </form>
        </Card>
      )}
    </PageFrame>
  );
}
