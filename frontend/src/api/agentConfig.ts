import { apiGet, apiPut } from "./client";

/** Mirrors backend/app/schemas/agent_config.py. There is only Claude Code, so no engine or provider. */
export interface AgentConfig {
  agent_role: string;
  model: string;
  effort: string;
  /** Role-specific settings, such as the researcher's search budget. */
  params: Record<string, number>;
  updated_at: string;
}

export interface UpdateAgentConfigInput {
  model: string;
  effort: string;
  params: Record<string, number>;
}

export async function fetchAgentConfigs(): Promise<AgentConfig[]> {
  return (await apiGet<{ configs: AgentConfig[] }>("/agent-configs")).configs;
}

export function updateAgentConfig(agentRole: string, input: UpdateAgentConfigInput): Promise<AgentConfig> {
  return apiPut<AgentConfig>(`/agent-configs/${encodeURIComponent(agentRole)}`, input);
}
