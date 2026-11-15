import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { askChat, createChat, deleteChat, getChat, listChats } from "../../api/chats";

export const CHATS_QUERY_KEY = ["chats"] as const;
const POLL_MS = 1500;

export function useChats() {
  return useQuery({ queryKey: CHATS_QUERY_KEY, queryFn: listChats });
}

/** The open chat, re-read every 1.5 s while an answer is pending and left alone otherwise. */
export function useChatDetail(id: string | null) {
  return useQuery({
    queryKey: ["chat", id],
    queryFn: () => getChat(id as string),
    enabled: id !== null,
    refetchInterval: (query) => (query.state.data?.pending ? POLL_MS : false),
  });
}

function useInvalidateChat() {
  const queryClient = useQueryClient();
  return async (id?: string) => {
    await queryClient.invalidateQueries({ queryKey: CHATS_QUERY_KEY });
    if (id) await queryClient.invalidateQueries({ queryKey: ["chat", id] });
  };
}

export function useCreateChat() {
  const invalidate = useInvalidateChat();
  return useMutation({ mutationFn: (domainSlugs: string[]) => createChat(domainSlugs), onSuccess: (chat) => invalidate(chat.id) });
}

export function useAsk(id: string) {
  const invalidate = useInvalidateChat();
  return useMutation({ mutationFn: (text: string) => askChat(id, text), onSuccess: () => invalidate(id) });
}

export function useDeleteChat() {
  const queryClient = useQueryClient();
  const invalidate = useInvalidateChat();
  return useMutation({
    mutationFn: (id: string) => deleteChat(id),
    onSuccess: async (_data, id) => {
      queryClient.removeQueries({ queryKey: ["chat", id] });
      await invalidate();
    },
  });
}
