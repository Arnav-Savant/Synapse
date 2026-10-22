import { apiGet, apiPost } from "./client";

/** Mirrors backend/app/schemas/outline.py. */
export type OverlapKind = "same" | "partial" | "distinct";

export interface OverlapVerdict {
  kind: OverlapKind;
  target_note_id: string | null;
  reason: string;
}

export interface OutlineNode {
  key: string;
  title: string;
  summary: string;
  parent_keys: string[];
  /** Domain slugs this node is written for. */
  domains: string[];
  content_slice: string | null;
  /** Keyed by domain slug. */
  verdicts: Record<string, OverlapVerdict>;
}

export interface Outline {
  topic_title: string;
  nodes: OutlineNode[];
}

/** Mirrors backend/app/schemas/jobs.py. */
export type InputKind = "topic" | "content";
export type JobStatus = "queued" | "running" | "awaiting_owner" | "completed" | "failed" | "cancelled";

export interface Job {
  id: string;
  title: string;
  input_kind: InputKind;
  domain_choice: string;
  resolved_domains: string[];
  status: JobStatus;
  current_step: string | null;
  awaiting_owner: boolean;
  error: string | null;
  total_cost_usd: number;
  created_at: string;
  updated_at: string;
}

export interface StepRun {
  step: string;
  agent_role: string | null;
  attempt: number;
  status: string;
  cost_usd: number;
  started_at: string;
  finished_at: string | null;
  error: string | null;
}

export interface JobDetail extends Job {
  steps: StepRun[];
}

export interface OutlineView {
  outline: Outline;
  resolved_domains: string[];
  classifier_confidence: number | null;
  /** Below the classifier threshold: the owner should confirm the domain. */
  low_confidence: boolean;
  /** Why the last edit was rejected, if it was. */
  error: string | null;
}

export interface Issue {
  code: string;
  message: string;
}

export interface Draft {
  node_key: string;
  domain_slug: string;
  title: string;
  kind: "new" | "merge";
  stage: string;
  path: string | null;
  /** Titles of the notes this one sits under. */
  parents: string[];
  body_md: string;
  validator_flags: Issue[];
  /** Merge drafts: unified diff against the file on disk now. */
  diff: string | null;
}

export interface LinkAddition {
  note_title: string;
  domain_slug: string;
  section: string;
  entry_title: string;
}

export interface DraftsResponse {
  drafts: Draft[];
  link_additions: LinkAddition[];
}

/** Mirrors backend/app/workflows/models.py. */
export interface OutlineDecision {
  kind: "approve" | "replan";
  tree: Outline;
  feedback: string | null;
}

export interface NodeFeedback {
  node_key: string;
  domain_slug: string;
  scope: "section" | "note" | "topic";
  section: string | null;
  text: string;
  re_research: boolean;
}

export interface DraftDecision {
  kind: "approve" | "feedback";
  /** `node` selects it in every domain, `node|domain` that one draft. null means all. */
  approve_node_keys: string[] | null;
  feedback: NodeFeedback[];
}

export interface CreateJobInput {
  input_kind: InputKind;
  text: string;
  /** A domain slug, or "auto". */
  domain_choice: string;
}

export const createJob = (input: CreateJobInput) => apiPost<Job>("/jobs", input);

export async function listJobs(): Promise<Job[]> {
  return (await apiGet<{ jobs: Job[] }>("/jobs")).jobs;
}

export const getJob = (id: string) => apiGet<JobDetail>(`/jobs/${encodeURIComponent(id)}`);

export const getOutline = (id: string) => apiGet<OutlineView>(`/jobs/${encodeURIComponent(id)}/outline`);

export const postOutlineDecision = (id: string, decision: OutlineDecision) =>
  apiPost<{ accepted: boolean }>(`/jobs/${encodeURIComponent(id)}/outline-decision`, decision);

export const getDrafts = (id: string) => apiGet<DraftsResponse>(`/jobs/${encodeURIComponent(id)}/drafts`);

export const postDraftDecision = (id: string, decision: DraftDecision) =>
  apiPost<{ accepted: boolean }>(`/jobs/${encodeURIComponent(id)}/draft-decision`, decision);

export const cancelJob = (id: string) => apiPost<{ accepted: boolean }>(`/jobs/${encodeURIComponent(id)}/cancel`, {});
