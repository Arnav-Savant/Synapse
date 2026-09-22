import { apiPost } from "./client";

interface ChatResponse {
  reply: string;
}

export async function sendChatMessage(message: string, conceptSlug: string | null): Promise<string> {
  return (await apiPost<ChatResponse>("/chat", { message, concept_slug: conceptSlug })).reply;
}
