import { apiDelete, apiGet, apiPost } from "./client";

/** Mirrors backend/app/schemas/chats.py. */
export interface Citation {
  ref: number;
  domain: string;
  title: string;
  heading: string;
}

export interface ChatMessage {
  id: string;
  position: number;
  role: "owner" | "assistant" | string;
  kind: "answer" | "question" | string;
  text: string;
  status: "sent" | "pending" | "answered" | "failed" | string;
  step: string | null;
  citations: Citation[];
  gaps: string[];
  flags: string[];
  error: string | null;
  cost_usd: number;
  created_at: string;
}

export interface Chat {
  id: string;
  title: string;
  domain_slugs: string[];
  updated_at: string;
  pending: boolean;
}

export interface ChatDetail extends Chat {
  messages: ChatMessage[];
  total_cost_usd: number;
}

export const MAX_MESSAGE_CHARS = 8_000;

export async function listChats(): Promise<Chat[]> {
  return (await apiGet<{ chats: Chat[] }>("/chats")).chats;
}

export const createChat = (domainSlugs: string[]) => apiPost<Chat>("/chats", { domain_slugs: domainSlugs });

export const getChat = (id: string) => apiGet<ChatDetail>(`/chats/${encodeURIComponent(id)}`);

export const deleteChat = (id: string) => apiDelete(`/chats/${encodeURIComponent(id)}`);

export const askChat = (id: string, text: string) =>
  apiPost<ChatMessage>(`/chats/${encodeURIComponent(id)}/messages`, { text });
