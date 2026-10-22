import type { Draft, DraftDecision, NodeFeedback } from "../../api/jobs";

export interface FeedbackForm {
  scope: "section" | "note" | "topic";
  section: string;
  text: string;
  reResearch: boolean;
}

/** Identifies one draft: a note in one domain's vault. */
export const draftKey = (d: Pick<Draft, "node_key" | "domain_slug">) => `${d.node_key}|${d.domain_slug}`;

/** What is wrong with the feedback form, in words for the owner; null when it can be sent. */
export function feedbackProblem(form: FeedbackForm): string | null {
  if (!form.text.trim()) return "Write what should change.";
  if (form.scope === "section" && !form.section.trim()) return "Choose which section to change.";
  return null;
}

interface DecisionState {
  kind: "approve" | "feedback";
  drafts: Draft[];
  selected: ReadonlySet<string>;
  active: Pick<Draft, "node_key" | "domain_slug"> | null;
  feedback: FeedbackForm;
}

/** Builds the payload for the backend. Approving everything sends `null`, which means "all". */
export function buildDraftDecision(state: DecisionState): DraftDecision {
  if (state.kind === "approve") {
    const all = state.drafts.every((d) => state.selected.has(draftKey(d)));
    return { kind: "approve", approve_node_keys: all ? null : [...state.selected], feedback: [] };
  }
  const problem = feedbackProblem(state.feedback);
  if (problem) throw new Error(problem);
  if (!state.active) throw new Error("Pick a note to give feedback on.");
  const item: NodeFeedback = {
    node_key: state.active.node_key,
    domain_slug: state.active.domain_slug,
    scope: state.feedback.scope,
    section: state.feedback.scope === "section" ? state.feedback.section.trim() : null,
    text: state.feedback.text.trim(),
    re_research: state.feedback.reResearch,
  };
  return { kind: "feedback", approve_node_keys: null, feedback: [item] };
}

const FLAG_LABELS: Record<string, string> = {
  scope_creep: "Goes beyond the scope",
  missing_depth_section: "A section is missing",
  unsupported_claim: "A claim has no support",
  contradicts_source: "Contradicts its sources",
  filler: "Contains filler",
  dangling_link: "Links to a note that does not exist",
  unsafe_link: "Has an unsafe link",
  empty_section: "Has an empty section",
  empty_body: "Has no content",
  too_large: "Too long",
  bad_title: "Title has unusable characters",
  title_exists: "A note with this title already exists",
  fence_in_body: "Contains a stray divider line",
  frontmatter_invalid: "Its header is broken",
  frontmatter_missing_keys: "Its header is incomplete",
  frontmatter_forbidden_key: "Its header has a field it should not",
  merge_target_missing: "The note it should merge into was deleted",
  commit_failed: "Could not be saved",
  other: "Needs attention",
};

export const flagLabel = (code: string) => FLAG_LABELS[code] ?? code.replace(/_/g, " ");
