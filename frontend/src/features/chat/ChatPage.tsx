import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import type { Chat } from "../../api/chats";
import { ApiError } from "../../api/client";
import { listDomains } from "../../api/domains";
import { Button } from "../../design/Button";
import { Card } from "../../design/Card";
import { Chip } from "../../design/Chip";
import { EmptyState } from "../../design/EmptyState";
import { LoadingBlock } from "../../design/Spinner";
import { PageFrame } from "../../shell/PageFrame";
import { timeAgo } from "../jobs/jobStatus";
import { ChatThread } from "./ChatThread";
import { useChats, useCreateChat, useDeleteChat } from "./useChat";

const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Could not reach the backend.");

function NewChatPicker({ onCreated, onCancel }: { onCreated: (id: string) => void; onCancel: () => void }) {
  const domains = useQuery({ queryKey: ["domains"], queryFn: listDomains });
  const create = useCreateChat();
  const [picked, setPicked] = useState<string[]>([]);

  const toggle = (slug: string) => setPicked((now) => (now.includes(slug) ? now.filter((s) => s !== slug) : [...now, slug]));

  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-semibold">Which vaults should this chat read?</h2>
      {domains.isLoading ? (
        <LoadingBlock label="Loading domains" />
      ) : domains.isError ? (
        <p className="text-sm text-danger" role="alert">
          {errorText(domains.error)}
        </p>
      ) : (domains.data ?? []).length === 0 ? (
        <p className="text-sm text-muted">No domains yet. Create one in Settings first.</p>
      ) : (
        <fieldset className="flex flex-col gap-1.5">
          <legend className="sr-only">Vaults</legend>
          {domains.data!.map((domain) => (
            <label key={domain.slug} className="flex items-center gap-2.5 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4 accent-[var(--accent)]"
                checked={picked.includes(domain.slug)}
                onChange={() => toggle(domain.slug)}
              />
              {domain.name}
            </label>
          ))}
        </fieldset>
      )}
      {create.isError ? (
        <p className="text-sm text-danger" role="alert">
          {errorText(create.error)}
        </p>
      ) : null}
      <div className="flex gap-2">
        <Button
          variant="primary"
          disabled={picked.length === 0}
          loading={create.isPending}
          onClick={() => create.mutate(picked, { onSuccess: (chat) => onCreated(chat.id) })}
        >
          Start chat
        </Button>
        <Button onClick={onCancel}>Cancel</Button>
      </div>
    </Card>
  );
}

function ChatListItem({ chat, active, onOpen }: { chat: Chat; active: boolean; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-current={active ? "true" : undefined}
      className={`flex w-full flex-col items-start gap-1.5 rounded-control border px-3 py-2.5 text-left transition-colors ${
        active ? "border-accent bg-accent-soft" : "border-line bg-surface hover:bg-sunken"
      }`}
    >
      <span className="line-clamp-2 text-sm font-medium">{chat.title || "New chat"}</span>
      <span className="flex flex-wrap gap-1">
        {chat.domain_slugs.map((slug) => (
          <Chip key={slug}>{slug}</Chip>
        ))}
        {chat.pending ? (
          <Chip tone="info" dot="live">
            Answering
          </Chip>
        ) : null}
      </span>
      <span className="text-xs text-muted">{timeAgo(chat.updated_at)}</span>
    </button>
  );
}

export function ChatPage() {
  const chats = useChats();
  const remove = useDeleteChat();
  const [openId, setOpenId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const open = chats.data?.find((chat) => chat.id === openId) ?? null;
  const activeId = open?.id ?? null;

  function openChat(id: string | null) {
    setOpenId(id);
    setConfirmingDelete(false);
    remove.reset();
  }

  return (
    <PageFrame
      wide
      title="Chat"
      description="Ask questions and get answers drawn from your notes, with the notes and sections they came from."
      actions={
        <Button variant="primary" onClick={() => setCreating(true)} disabled={creating}>
          New chat
        </Button>
      }
    >
      <div className="grid gap-6 md:grid-cols-[18rem_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-2">
          {creating ? (
            <NewChatPicker
              onCancel={() => setCreating(false)}
              onCreated={(id) => {
                setCreating(false);
                openChat(id);
              }}
            />
          ) : null}
          {chats.isLoading ? (
            <LoadingBlock label="Loading chats" />
          ) : chats.isError ? (
            <EmptyState tone="error" title="Could not load your chats" hint={errorText(chats.error)} />
          ) : (chats.data ?? []).length === 0 ? (
            <EmptyState title="No chats yet" hint="Start one to ask questions about a vault." />
          ) : (
            chats.data!.map((chat) => (
              <ChatListItem key={chat.id} chat={chat} active={chat.id === activeId} onOpen={() => openChat(chat.id)} />
            ))
          )}
        </div>

        <div className="min-w-0">
          {open ? (
            <>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <h2 className="min-w-0 truncate text-lg font-semibold">{open.title || "New chat"}</h2>
                {confirmingDelete ? (
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-muted">Delete this chat and its stored passages?</span>
                    <Button
                      variant="danger"
                      size="sm"
                      disabled={open.pending}
                      loading={remove.isPending}
                      onClick={() => remove.mutate(open.id, { onSuccess: () => openChat(null) })}
                    >
                      Delete
                    </Button>
                    <Button size="sm" onClick={() => setConfirmingDelete(false)}>
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <Button size="sm" disabled={open.pending} onClick={() => setConfirmingDelete(true)}>
                    Delete chat
                  </Button>
                )}
              </div>
              {remove.isError ? (
                <p className="mb-3 text-sm text-danger" role="alert">
                  {errorText(remove.error)}
                </p>
              ) : null}
              <ChatThread key={open.id} chatId={open.id} />
            </>
          ) : (
            <EmptyState title="Pick a chat or start a new one" hint="Your conversations and their sources appear here." />
          )}
        </div>
      </div>
    </PageFrame>
  );
}
