import { apiGet, apiPost } from "./client";

/** Mirrors backend/app/schemas/notes.py. */
export interface Note {
  synapse_id: string;
  title: string;
  path: string;
  summary: string;
  domain_slug: string;
  user_modified: boolean;
  /** A note that groups topics. */
  is_hub: boolean;
  /** The job that created it, if any. */
  job_id: string | null;
  /** Other vaults that hold a note on the same subject. */
  twin_domains: string[];
}

export interface NoteRef {
  synapse_id: string;
  title: string;
  path: string;
  domain_slug: string;
  user_modified: boolean;
}

export interface FileEdit {
  note: NoteRef;
  links_removed: number;
}

export interface ReparentChange {
  child: NoteRef;
  new_parents: string[];
}

export interface DeletePlan {
  delete_notes: NoteRef[];
  edits: FileEdit[];
  reparent: ReparentChange[];
  needs_extra_confirm: NoteRef[];
}

/** Exactly one of note_ids, topic_folder or job_id. */
export interface DeleteSelector {
  domain: string;
  note_ids?: string[];
  topic_folder?: string;
  job_id?: string;
  twin_scope?: "this" | "all";
}

export interface DeleteResult {
  deleted: number;
  links_stripped_in: number;
  children_reattached: number;
}

export interface ReconcileReport {
  removed: number;
  added: number;
  modified: number;
  moved: number;
}

export async function listNotes(domain: string, q?: string): Promise<Note[]> {
  const params = new URLSearchParams({ domain });
  if (q?.trim()) params.set("q", q.trim());
  return (await apiGet<{ notes: Note[] }>(`/notes?${params}`)).notes;
}

export const previewDelete = (selector: DeleteSelector) => apiPost<DeletePlan>("/notes/delete-preview", selector);

export const deleteNotes = (selector: DeleteSelector, confirmModified: boolean) =>
  apiPost<DeleteResult>("/notes/delete", { ...selector, confirm_modified: confirmModified });

export async function reconcile(): Promise<Record<string, ReconcileReport>> {
  return (await apiPost<{ domains: Record<string, ReconcileReport> }>("/notes/reconcile", {})).domains;
}
