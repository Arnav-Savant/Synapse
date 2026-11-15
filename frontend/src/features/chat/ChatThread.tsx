import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import { MAX_MESSAGE_CHARS } from "../../api/chats";
import { Button } from "../../design/Button";
import { EmptyState } from "../../design/EmptyState";
import { TextArea } from "../../design/Field";
import { LoadingBlock } from "../../design/Spinner";
import { ChatMessage } from "./ChatMessage";
import { useAsk, useChatDetail } from "./useChat";

const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Could not reach the backend.");

export function ChatThread({ chatId }: { chatId: string }) {
  const detail = useChatDetail(chatId);
  const ask = useAsk(chatId);
  const [text, setText] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  const chat = detail.data;
  const messageCount = chat?.messages.length ?? 0;
  const pending = Boolean(chat?.pending) || ask.isPending;
  const tooLong = text.length > MAX_MESSAGE_CHARS;

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messageCount, chat?.pending]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || pending) return;
    ask.mutate(trimmed, { onSuccess: () => setText("") });
  }

  if (detail.isLoading) return <LoadingBlock label="Opening the chat" />;
  if (detail.isError || !chat) {
    return <EmptyState tone="error" title="Could not open this chat" hint={errorText(detail.error)} />;
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-col gap-4" aria-live="polite">
        {chat.messages.length === 0 ? (
          <EmptyState title="Ask about your notes" hint="Explain a topic, ask what comes before it, or describe a scenario. Answers cite the notes they come from." />
        ) : (
          chat.messages.map((message) => <ChatMessage key={message.id} message={message} />)
        )}
        <div ref={endRef} />
      </div>

      <form onSubmit={submit} className="sticky bottom-0 flex flex-col gap-2 border-t border-line bg-bg pb-3 pt-3">
        <TextArea
          aria-label="Your question"
          rows={3}
          value={text}
          disabled={pending}
          placeholder={pending ? "Waiting for the answer" : "Ask a question"}
          aria-invalid={tooLong || undefined}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e);
          }}
          resizable={false}
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className={`text-xs ${tooLong ? "text-danger" : "text-muted"}`}>
            {text.length.toLocaleString()} of {MAX_MESSAGE_CHARS.toLocaleString()} characters
          </p>
          <Button type="submit" variant="primary" disabled={!text.trim() || pending} loading={ask.isPending}>
            Ask
          </Button>
        </div>
        {ask.isError ? (
          <p className="text-sm text-danger" role="alert">
            {errorText(ask.error)}
          </p>
        ) : null}
      </form>
    </div>
  );
}
