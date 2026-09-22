/**
 * Thin fetch wrapper: the only module that talks HTTP to the backend.
 * Endpoint-specific modules (e.g. `health.ts`) build on top of this rather
 * than calling `fetch` themselves.
 */

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`);

  if (!response.ok) {
    throw new ApiError(response.status, `GET ${path} failed: ${response.status}`);
  }

  return (await response.json()) as T;
}
