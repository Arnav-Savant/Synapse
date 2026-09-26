import { apiGet, apiPut } from "./client";

/** Mirrors backend/app/schemas/agent_config.py:AgentConfigOut exactly. */
export interface AgentConfig {
  agent_role: string;
  engine: string;
  provider: string | null;
  model: string;
  effort: string;
  env_key_name: string | null;
  updated_at: string;
}

interface AgentConfigListResponse {
  configs: AgentConfig[];
}

export async function fetchAgentConfigs(): Promise<AgentConfig[]> {
  return (await apiGet<AgentConfigListResponse>("/agent-configs")).configs;
}

/** Mirrors backend/app/schemas/agent_config.py:UpdateAgentConfigRequest. */
export interface UpdateAgentConfigInput {
  engine: string;
  model: string;
  effort: string;
  provider?: string | null;
  env_key_name?: string | null;
}

export function updateAgentConfig(agentRole: string, input: UpdateAgentConfigInput): Promise<AgentConfig> {
  return apiPut<AgentConfig>(`/agent-configs/${encodeURIComponent(agentRole)}`, {
    engine: input.engine,
    model: input.model,
    effort: input.effort,
    provider: input.provider ?? null,
    env_key_name: input.env_key_name ?? null,
  });
}
