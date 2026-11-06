import { useMutation, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../api/client";
import { applyTidy, previewTidy, reviewTidy } from "../../api/notes";
import { Button } from "../../design/Button";
import { Card } from "../../design/Card";

const errorText = (e: unknown) => (e instanceof ApiError ? e.message : "Could not reach the backend.");

/** Thins Related links in notes already written: preview what the rules remove, optionally let Claude review the rest, then confirm. */
export function TidyLinks({ domain }: { domain: string }) {
  const queryClient = useQueryClient();
  const preview = useMutation({ mutationFn: () => previewTidy(domain) });
  const review = useMutation({ mutationFn: () => reviewTidy(domain) });
  const apply = useMutation({
    mutationFn: applyTidy,
    onSuccess: async () => {
      preview.reset();
      review.reset();
      await queryClient.invalidateQueries({ queryKey: ["notes", domain] });
    },
  });
  const plan = review.data ?? preview.data;
  const busy = preview.isPending || review.isPending;
  const error = preview.error ?? review.error ?? apply.error;

  return (
    <div className="mb-5 flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button loading={preview.isPending} disabled={busy} onClick={() => { review.reset(); preview.mutate(); }}>
          Tidy related links
        </Button>
        <p className="max-w-prose text-sm text-muted">
          Removes Related links that repeat the tree (a note linking to its own parent or child) and the second copy of a pair. Nothing changes until you confirm.
        </p>
      </div>

      {apply.data ? (
        <p className="rounded-control bg-ok-soft px-4 py-2.5 text-sm text-ok" role="status">
          Removed {apply.data.links_removed} link{apply.data.links_removed === 1 ? "" : "s"} from {apply.data.notes_changed} note{apply.data.notes_changed === 1 ? "" : "s"}.
        </p>
      ) : null}
      {error ? (
        <p className="rounded-control bg-danger-soft px-4 py-2.5 text-sm text-danger" role="alert">
          {errorText(error)}
        </p>
      ) : null}

      {plan ? (
        <Card>
          {plan.edits.length === 0 ? (
            <p className="text-sm">Nothing to remove{plan.reviewed ? ": the reviewer found every remaining Related link worth keeping." : "."}</p>
          ) : (
            <>
              <p className="text-sm font-medium">
                {plan.links} link{plan.links === 1 ? "" : "s"} in {plan.edits.length} note{plan.edits.length === 1 ? "" : "s"} would be removed. Only those lines change; the notes themselves stay.
              </p>
              <ul className="mt-3 flex max-h-72 flex-col gap-2 overflow-y-auto text-sm">
                {plan.edits.map((e) => (
                  <li key={e.note.synapse_id}>
                    <span className="font-medium">{e.note.title}</span>
                    {e.remove.length > 0 ? <span className="block text-muted">Repeats the tree or a pair: {e.remove.join(", ")}</span> : null}
                    {e.review.length > 0 ? <span className="block text-muted">Not essential, per the reviewer: {e.review.join(", ")}</span> : null}
                  </li>
                ))}
              </ul>
            </>
          )}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {plan.edits.length > 0 ? (
              <Button variant="primary" loading={apply.isPending} disabled={busy} onClick={() => apply.mutate(plan)}>
                Remove these links
              </Button>
            ) : null}
            {!plan.reviewed ? (
              <Button loading={review.isPending} disabled={busy || apply.isPending} onClick={() => review.mutate()}>
                Also review the rest with Claude
              </Button>
            ) : null}
            <Button variant="ghost" onClick={() => { preview.reset(); review.reset(); }}>
              Cancel
            </Button>
          </div>
          {!plan.reviewed ? (
            <p className="mt-2 text-[13px] text-muted">The review keeps only prerequisites and direct contrasts. It costs a few cents and shows its proposal here first.</p>
          ) : (
            <p className="mt-2 text-[13px] text-muted">Review cost ${plan.cost_usd.toFixed(3)}.</p>
          )}
        </Card>
      ) : null}
    </div>
  );
}
