import { buildBackendUrl } from "./backend.ts";
import { getAccessToken } from "./auth-token.ts";
import { BffError } from "./errors.ts";

export function buildAuthHeaders(token: string, init?: HeadersInit): Headers {
  const headers = new Headers(init);
  headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

export async function fetchBackend(
  path: string,
  request: Request,
  init?: RequestInit,
): Promise<Response> {
  const token = await getAccessToken(request);
  const headers = buildAuthHeaders(token, init?.headers);
  return fetch(buildBackendUrl(path), {
    ...init,
    headers,
    cache: "no-store",
  });
}

export { BffError };
