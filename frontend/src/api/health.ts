import { apiGet } from "./client";

export interface HealthStatus {
  status: string;
}

export function fetchHealth(): Promise<HealthStatus> {
  return apiGet<HealthStatus>("/health");
}
