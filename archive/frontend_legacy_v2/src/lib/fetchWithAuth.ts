export type FetchWithAuthInit = RequestInit & {
  headers?: HeadersInit;
};

export function withAuthHeaders(token: string, headers?: HeadersInit): Headers {
  const next = new Headers(headers ?? undefined);
  next.set("Authorization", `Bearer ${token}`);
  return next;
}

export async function fetchWithAuth(
  input: RequestInfo | URL,
  token: string,
  init: FetchWithAuthInit = {},
): Promise<Response> {
  if (!token) {
    throw new Error("missing_token");
  }
  const headers = withAuthHeaders(token, init.headers);
  return fetch(input, { ...init, headers });
}
