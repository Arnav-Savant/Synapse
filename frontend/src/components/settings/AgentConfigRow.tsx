import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { type AgentConfig, updateAgentConfig } from "../../api/agentConfig";

const ENGINES = ["claude_code", "litellm"] as const;
const CLAUDE_CODE_EFFORTS = ["low", "medium", "high", "xhigh", "max"] as const;

const fieldClass =
  "w-full border-b border-ink-line bg-transparent px-1 py-1 text-paper focus:border-spark focus:outline-none";

interface AgentConfigRowProps {
  config: AgentConfig;
}

/**
 * One agent role's engine/model/effort/provider settings, edited inline
 * (per-row save) rather than as part of one big form — each role is an
 * independent PUT /api/agent-configs/{role} (backend/app/api/agent_config.py),
 * so six separate edits matches the backend contract more naturally than a
 * single combined submit.
 *
 * `env_key_name` is the *name* of an env var already set in the backend's
 * .env (e.g. "OPENAI_API_KEY"), never the secret value itself — the backend
 * schema has no field for the actual key, and this component doesn't invent
 * one.
 */
export function AgentConfigRow({ config }: AgentConfigRowProps) {
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [engine, setEngine] = useState(config.engine);
  const [model, setModel] = useState(config.model);
  const [effort, setEffort] = useState(config.effort);
  const [provider, setProvider] = useState(config.provider ?? "");
  const [envKeyName, setEnvKeyName] = useState(config.env_key_name ?? "");

  const updateMutation = useMutation({
    mutationFn: () =>
      updateAgentConfig(config.agent_role, {
        engine,
        model,
        effort,
        provider: provider.trim() || null,
        env_key_name: envKeyName.trim() || null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["agent-configs"] });
      setIsEditing(false);
    },
  });

  function startEditing() {
    setEngine(config.engine);
    setModel(config.model);
    setEffort(config.effort);
    setProvider(config.provider ?? "");
    setEnvKeyName(config.env_key_name ?? "");
    updateMutation.reset();
    setIsEditing(true);
  }

  function cancelEditing() {
    updateMutation.reset();
    setIsEditing(false);
  }

  if (!isEditing) {
    return (
      <li className="flex items-center justify-between gap-4 py-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="text-paper">{config.agent_role}</span>
          <span className="truncate text-graphite">
            {config.engine} · {config.model} · effort: {config.effort}
            {config.provider ? ` · ${config.provider}` : ""}
          </span>
        </div>
        <button
          type="button"
          onClick={startEditing}
          className="shrink-0 border border-ink-line px-3 py-1.5 text-graphite hover:border-spark hover:text-spark"
        >
          edit
        </button>
      </li>
    );
  }

  return (
    <li className="space-y-3 py-3">
      <span className="text-paper">{config.agent_role}</span>

      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-graphite">engine</span>
          <select className={fieldClass} value={engine} onChange={(e) => setEngine(e.target.value)}>
            {ENGINES.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-graphite">model</span>
          <input className={fieldClass} value={model} onChange={(e) => setModel(e.target.value)} required />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-graphite">effort</span>
          {engine === "claude_code" ? (
            <select className={fieldClass} value={effort} onChange={(e) => setEffort(e.target.value)}>
              {CLAUDE_CODE_EFFORTS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          ) : (
            <input className={fieldClass} value={effort} onChange={(e) => setEffort(e.target.value)} required />
          )}
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-graphite">provider (optional)</span>
          <input className={fieldClass} value={provider} onChange={(e) => setProvider(e.target.value)} />
        </label>

        {engine === "litellm" && (
          <label className="col-span-2 flex flex-col gap-1">
            <span className="text-graphite">env var name holding the API key (not the key itself)</span>
            <input className={fieldClass} value={envKeyName} onChange={(e) => setEnvKeyName(e.target.value)} />
          </label>
        )}
      </div>

      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={() => updateMutation.mutate()}
          disabled={updateMutation.isPending}
          className="bg-spark px-4 py-1.5 text-ink disabled:opacity-50"
        >
          {updateMutation.isPending ? "saving…" : "save"}
        </button>
        <button
          type="button"
          onClick={cancelEditing}
          disabled={updateMutation.isPending}
          className="text-graphite hover:text-paper"
        >
          cancel
        </button>
        {updateMutation.isError && (
          <span className="text-signal">
            {updateMutation.error instanceof Error ? updateMutation.error.message : "failed to save"}
          </span>
        )}
      </div>
    </li>
  );
}
