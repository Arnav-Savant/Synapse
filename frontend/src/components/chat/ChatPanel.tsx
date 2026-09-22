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
 * this session to that concept until cleared. */
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
    <div className="mx-auto max-w-2xl space-y-3">
      {contextSlug && (
        <div className="flex items-center gap-2 rounded-md bg-slate-100 px-3 py-1.5 text-xs text-slate-600">
          <span>
            Asking about: <span className="font-medium">{contextSlug}</span>
          </span>
          <button onClick={onClearContext} className="text-slate-400 hover:text-slate-600">
            ×
          </button>
        </div>
      )}

      <div className="min-h-[420px] space-y-3 rounded-lg border border-slate-200 p-4">
        {messages.length === 0 && (
          <p className="text-sm text-slate-400">
            Ask a question — answered using your knowledge base, no API key required.
          </p>
        )}
        {messages.map((msg, index) => (
          <div key={index} className={msg.role === "user" ? "text-right" : "text-left"}>
            <span
              className={`inline-block max-w-[85%] rounded-lg px-3 py-2 text-left text-sm ${
                msg.role === "user" ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-800"
              }`}
            >
              {msg.text}
            </span>
          </div>
        ))}
        {sendMutation.isPending && <p className="text-sm text-slate-400">Thinking…</p>}
      </div>

      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          placeholder="Ask about your knowledge base…"
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
        />
        <button
          onClick={handleSend}
          disabled={sendMutation.isPending}
          className="rounded-md bg-slate-800 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </div>
  );
}
