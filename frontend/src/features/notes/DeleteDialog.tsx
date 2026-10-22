import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import { deleteNotes, previewDelete, type DeleteResult, type DeleteSelector } from "../../api/notes";
import { Button } from "../../design/Button";
import { LoadingBlock } from "../../design/Spinner";

export interface DeleteRequestInfo {
  /** What the owner asked for, as a sentence: "Delete the topic “Isolation levels”". */
  title: string;
  /** The short wording of this option in the Delete menu. */
  label: string;
  selector: DeleteSelector;
}

interface DeleteDialogProps {
  request: DeleteRequestInfo;
  onClose: () => void;
  onDeleted: (result: DeleteResult) => void;
}

/** Shows exactly what a delete will change before it happens. Notes edited in Obsidian need an extra tick. */
export function DeleteDialog({ request, onClose, onDeleted }: DeleteDialogProps) {
  const queryClient = useQueryClient();
  const ref = useRef<HTMLDialogElement>(null);
  const [understood, setUnderstood] = useState(false);

  useEffect(() => {
    ref.current?.showModal();
  }, []);

  const preview = useQuery({
    queryKey: ["delete-preview", request.selector],
    queryFn: () => previewDelete(request.selector),
    gcTime: 0,
    retry: false,
  });
  const plan = preview.data;
  const needsConfirm = (plan?.needs_extra_confirm.length ?? 0) > 0;

  const remove = useMutation({
    mutationFn: () => deleteNotes(request.selector, understood),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["notes"] });
      onDeleted(result);
    },
  });
  const errorText = (e: unknown) => (e instanceof ApiError ? e.message : "Could not reach the backend.");

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      aria-labelledby="delete-title"
      className="m-auto w-[min(40rem,calc(100vw-2rem))] rounded-panel border border-line bg-surface p-0 text-fg shadow-[var(--shadow-pop)] backdrop:bg-black/50"
    >
      <div className="flex max-h-[85vh] flex-col">
        <div className="overflow-y-auto px-6 pt-6">
          <h2 id="delete-title" className="text-lg font-semibold tracking-tight">
            {request.title}
          </h2>
          {preview.isLoading ? (
            <LoadingBlock label="Working out what will change" />
          ) : preview.isError ? (
            <p className="py-6 text-danger" role="alert">
              {errorText(preview.error)}
            </p>
          ) : plan ? (
            <div className="mt-4 flex flex-col gap-5 pb-4 text-sm">
              <section>
                <h3 className="mb-1 font-semibold">
                  {plan.delete_notes.length === 1 ? "This note is deleted from disk" : `These ${plan.delete_notes.length} notes are deleted from disk`}
                </h3>
                <ul className="flex flex-col gap-0.5 text-muted">
                  {plan.delete_notes.map((n) => (
                    <li key={n.synapse_id}>
                      <span className="text-fg">{n.title}</span> <span className="font-mono text-xs">{n.domain_slug}/{n.path}</span>
                    </li>
                  ))}
                </ul>
              </section>
              {plan.edits.length > 0 ? (
                <section>
                  <h3 className="mb-1 font-semibold">Links to them are removed so nothing dangles</h3>
                  <ul className="flex flex-col gap-0.5 text-muted">
                    {plan.edits.map((e) => (
                      <li key={e.note.synapse_id}>
                        <span className="text-fg">{e.note.title}</span>: {e.links_removed} {e.links_removed === 1 ? "link" : "links"}
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
              {plan.reparent.length > 0 ? (
                <section>
                  <h3 className="mb-1 font-semibold">Notes underneath move up</h3>
                  <ul className="flex flex-col gap-0.5 text-muted">
                    {plan.reparent.map((r) => (
                      <li key={r.child.synapse_id}>
                        <span className="text-fg">{r.child.title}</span>{" "}
                        {r.new_parents.length ? `now sits under ${r.new_parents.map((p) => `[[${p}]]`).join(", ")}` : "becomes a top-level note"}
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}
              {plan.edits.length === 0 && plan.reparent.length === 0 ? <p className="text-muted">No other notes link to these, so no other files change.</p> : null}
              {needsConfirm ? (
                <label className="flex items-start gap-2.5 rounded-control bg-warn-soft p-3 text-warn">
                  <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[var(--warn-bar)]" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} />
                  <span>
                    You edited {plan.needs_extra_confirm.map((n) => `“${n.title}”`).join(", ")} in Obsidian. Deleting removes those edits for good.
                  </span>
                </label>
              ) : null}
            </div>
          ) : null}
        </div>
        <div className="flex items-center justify-between gap-3 border-t border-line px-6 py-4">
          <p className="min-w-0 text-sm text-danger" role="alert">
            {remove.error ? errorText(remove.error) : ""}
          </p>
          <div className="flex shrink-0 gap-2">
            <Button onClick={() => ref.current?.close()}>Cancel</Button>
            <Button variant="danger" loading={remove.isPending} disabled={!plan || (needsConfirm && !understood)} onClick={() => remove.mutate()}>
              Delete
            </Button>
          </div>
        </div>
      </div>
    </dialog>
  );
}
