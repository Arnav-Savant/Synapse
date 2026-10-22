import { apiDelete, apiGet, apiPost, apiPut } from "./client";

/** Mirrors backend/app/schemas/domains.py. */
export interface DomainProfile {
  objective: string;
  depth_sections: string[];
  scope_include: string;
  scope_mention_only: string;
  style: string;
}

export interface Domain {
  slug: string;
  name: string;
  purpose: string;
  vault_path: string;
  profile: DomainProfile;
  /** Only set on the response to creating a domain: an existing vault folder was reused. */
  folder_existed: boolean;
  created_at: string;
  updated_at: string;
}

export interface DomainInput {
  name: string;
  purpose: string;
  profile: DomainProfile;
}

/** What the form had when "Draft with Claude" was pressed. */
export interface ProfileAnswers {
  name: string;
  purpose: string;
  objective: string;
  depth_sections: string[];
  scope_include: string;
  scope_mention_only: string;
  style: string;
  pasted_prompt: string | null;
}

export async function listDomains(): Promise<Domain[]> {
  return (await apiGet<{ domains: Domain[] }>("/domains")).domains;
}

export const createDomain = (input: DomainInput) => apiPost<Domain>("/domains", input);

export const updateDomain = (slug: string, input: DomainInput) =>
  apiPut<Domain>(`/domains/${encodeURIComponent(slug)}`, input);

export const deleteDomain = (slug: string) => apiDelete(`/domains/${encodeURIComponent(slug)}`);

export const draftProfile = (answers: ProfileAnswers) => apiPost<DomainProfile>("/domains/draft-profile", answers);

export const emptyProfile = (): DomainProfile => ({
  objective: "",
  depth_sections: [],
  scope_include: "",
  scope_mention_only: "",
  style: "",
});
