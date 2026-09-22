import { apiGet } from "./client";

export interface HealthStatus {
  status: string;
  knowledge_repo_path: string;
  knowledge_repo_exists: boolean;
}

export function fetchHealth(): Promise<HealthStatus> {
  return apiGet<HealthStatus>("/health");
}
