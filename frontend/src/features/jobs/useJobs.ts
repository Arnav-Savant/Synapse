import { useQuery } from "@tanstack/react-query";

import { listJobs } from "../../api/jobs";

export const JOBS_QUERY_KEY = ["jobs"] as const;

/** Every job, refreshed every few seconds: the dashboard and the sidebar's "needs you" count share this one query. */
export function useJobs() {
  return useQuery({ queryKey: JOBS_QUERY_KEY, queryFn: listJobs, refetchInterval: 3000 });
}
