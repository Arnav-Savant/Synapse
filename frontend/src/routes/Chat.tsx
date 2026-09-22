import { ChatPanel } from "../components/chat/ChatPanel";

interface ChatProps {
  contextSlug: string | null;
  onClearContext: () => void;
}

export function Chat({ contextSlug, onClearContext }: ChatProps) {
  return <ChatPanel contextSlug={contextSlug} onClearContext={onClearContext} />;
}
