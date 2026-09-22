import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../../api/client";
import { sendChatMessage } from "../../api/chat";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

interface ChatPanelProps {
  contextSlug: string | null;
  onClearContext: () => void;
}

/** Global chat, answered from the knowledge base — no API key required
 * (docs/PLAN.md Phase 6). `contextSlug`, when set, scopes every message in
 * this session to that concept until cleared. Questions render in the
 * mono/system voice (a raw query); answers render in the serif voice
 * (synthesized from the knowledge base) — the same distinction used
 * everywhere else in the app. */
export function ChatPanel({ contextSlug, onClearContext }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");

  const sendMutation = useMutation({
    mutationFn: (message: string) => sendChatMessage(message, contextSlug),
    onSuccess: (reply) => setMessages((prev) => [...prev, { role: "assistant", text: reply }]),
    onError: (error) => {
      const text = error instanceof ApiError ? error.message : "Something went wrong.";
      setMessages((prev) => [...prev, { role: "assistant", text: `Error: ${text}` }]);
    },
  });

  function handleSend() {
    const trimmed = input.trim();
    if (!trimmed || sendMutation.isPending) return;
    setMessages((prev) => [...prev, { role: "user", text: trimmed }]);
    setInput("");
    sendMutation.mutate(trimmed);
  }

  return (
    <div className="max-w-[720px] space-y-4">
      {contextSlug && (
        <div className="flex items-center gap-2 font-mono text-xs text-graphite">
          <span className="h-1.5 w-1.5 rounded-full bg-spark" />
          asking about <span className="text-spark">{contextSlug}</span>
          <button onClick={onClearContext} className="text-graphite hover:text-paper">
            ×
          </button>
        </div>
      )}

      <div className="min-h-[420px] space-y-5 border border-paper-line bg-paper p-6">
        {messages.length === 0 && (
          <p className="font-mono text-xs text-paper-ink/40">
            ask a question — answered using your knowledge base, no API key required.
          </p>
        )}
        {messages.map((msg, index) =>
          msg.role === "user" ? (
            <p key={index} className="font-mono text-xs text-paper-ink/60">
              <span className="text-spark-dim">›</span> {msg.text}
            </p>
          ) : (
            <p key={index} className="max-w-[65ch] font-serif text-base leading-relaxed text-paper-ink">
              {msg.text}
            </p>
          ),
        )}
        {sendMutation.isPending && <p className="font-mono text-xs text-paper-ink/40">thinking…</p>}
      </div>

      <div className="flex items-center gap-4 font-mono text-xs">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="ask about your knowledge base…"
          className="flex-1 border-b border-ink-line bg-transparent py-2 text-paper placeholder-graphite/60 focus:border-spark focus:outline-none"
        />
        <button onClick={handleSend} disabled={sendMutation.isPending} className="text-spark disabled:opacity-40">
          send
        </button>
      </div>
    </div>
  );
}
