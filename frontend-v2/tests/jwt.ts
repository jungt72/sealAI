/** Unsigned test JWT with the given payload (header.payload.sig, base64url, UTF-8-safe).
 * Test-only — production tokens come from Keycloak and are verified by the backend. */
export function fakeJwt(payload: Record<string, unknown>): string {
  const b64u = (s: string) =>
    btoa(String.fromCharCode(...new TextEncoder().encode(s)))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
  return `${b64u(JSON.stringify({ alg: "none" }))}.${b64u(JSON.stringify(payload))}.sig`;
}
