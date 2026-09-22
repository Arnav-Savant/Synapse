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

async function parseErrorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? fallback;
  } catch {
    return fallback;
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`);

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorDetail(response, `GET ${path} failed: ${response.status}`));
  }

  return (await response.json()) as T;
}

async function apiSend<T>(method: "POST" | "PUT", path: string, body: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new ApiError(
      response.status,
      await parseErrorDetail(response, `${method} ${path} failed: ${response.status}`),
    );
  }

  return (await response.json()) as T;
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return apiSend<T>("POST", path, body);
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return apiSend<T>("PUT", path, body);
}
