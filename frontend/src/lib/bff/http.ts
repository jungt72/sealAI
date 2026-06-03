import { buildBackendUrl } from "./backend.ts";
import {
  applyBffCookieUpdates,
  getAccessToken,
  getAccessTokenResult,
  type BffCookieUpdate,
} from "./auth-token.ts";
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

export type BackendFetchResult = {
  response: Response;
  cookieUpdates: BffCookieUpdate[];
};

// Cookie-aware variant of fetchBackend. Surfaces the rotated session-cookie
// updates so the calling route can persist them (one Set-Cookie). Required on
// the high-frequency GET pollers (history, workspace): without persisting the
// rotated refresh token, the next refresh reuses the now-rotated token and
// Keycloak revokes the family. Refresh itself is single-flighted in
// getAccessTokenResult -> singleFlightRefresh.
export async function fetchBackendWithAuth(
  path: string,
  request: Request,
  init?: RequestInit,
): Promise<BackendFetchResult> {
  const { accessToken, cookieUpdates } = await getAccessTokenResult(request);
  const headers = buildAuthHeaders(accessToken, init?.headers);
  const response = await fetch(buildBackendUrl(path), {
    ...init,
    headers,
    cache: "no-store",
  });
  return { response, cookieUpdates };
}

export { BffError, applyBffCookieUpdates };
export type { BffCookieUpdate };
