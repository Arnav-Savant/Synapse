import { apiGet, apiPost } from "./client";

/** Mirrors backend/app/schemas/notes.py. */
export interface Note {
  synapse_id: string;
  title: string;
  path: string;
  summary: string;
  domain_slug: string;
  user_modified: boolean;
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

export interface TidyEdit {
  note: NoteRef;
  /** Related entries the rules remove: they repeat the tree, or the pair stays on the other note. */
  remove: string[];
  /** Entries the link reviewer judged not essential; removed only when confirmed. */
  review: string[];
}

export interface TidyPlan {
  domain_slug: string;
  edits: TidyEdit[];
  links: number;
  /** True when the Claude review ran. */
  reviewed: boolean;
  cost_usd: number;
}

export interface TidyResult {
  notes_changed: number;
  links_removed: number;
}

export const previewTidy = (domain: string) => apiGet<TidyPlan>(`/notes/tidy-preview?${new URLSearchParams({ domain })}`);

export const reviewTidy = (domain: string) => apiPost<TidyPlan>(`/notes/tidy-review?${new URLSearchParams({ domain })}`, {});

/** Applies the rule-based removals, plus the reviewed entries when the plan came from the review. */
export const applyTidy = (plan: TidyPlan) =>
  apiPost<TidyResult>("/notes/tidy", {
    domain_slug: plan.domain_slug,
    extra: plan.edits.filter((e) => e.review.length > 0).map((e) => ({ note_id: e.note.synapse_id, titles: e.review })),
  });
