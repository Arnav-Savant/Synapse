import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { fetchAgentConfigs } from "../../api/agentConfig";
import { IconButton } from "../ui/IconButton";
import { XIcon } from "../ui/icons";
import { AgentConfigRow } from "./AgentConfigRow";

interface SettingsModalProps {
  onClose: () => void;
}

// Fixed display order matching the six seeded roles (backend/app/db/seed.py)
// — list_configs doesn't guarantee row order, so it's pinned here rather than
// showing whatever order the DB happens to return.
const ROLE_ORDER = ["orchestrator", "text_agent", "graph_agent", "validation_agent", "naming", "chat"];

/**
 * Centered settings overlay for agent configuration, opened only from the
 * header's gear icon (App.tsx) — deliberately separate from the content
 * workspace (graph/library/panel/chat/quick-add), since operating the agents
 * is a different kind of task from reading/writing knowledge. Reuses
 * QuickAddOverlay's backdrop/close-on-Escape/close-on-backdrop-click idiom
 * for consistency rather than inventing a new modal pattern.
 */
export function SettingsModal({ onClose }: SettingsModalProps) {
  const configsQuery = useQuery({ queryKey: ["agent-configs"], queryFn: fetchAgentConfigs });

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const configs = configsQuery.data
    ? [...configsQuery.data].sort((a, b) => ROLE_ORDER.indexOf(a.agent_role) - ROLE_ORDER.indexOf(b.agent_role))
    : [];

  return (
    <div
      className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-ink/80 p-6 pt-20"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl space-y-6 border border-ink-line bg-ink-soft p-5 font-mono text-xs shadow-[0_20px_60px_-20px_rgba(0,0,0,0.6)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-sm text-graphite">agent settings</h2>
          <IconButton icon={<XIcon />} aria-label="Close" title="Close" onClick={onClose} size="md" />
        </div>

        {configsQuery.isPending && <p className="text-graphite">loading…</p>}
        {configsQuery.isError && <p className="text-signal">failed to load agent configs.</p>}

        {configs.length > 0 && (
          <ul className="divide-y divide-ink-line border-y border-ink-line">
            {configs.map((config) => (
              <AgentConfigRow key={config.agent_role} config={config} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
