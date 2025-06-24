// Build an absolute WS URL that works in dev & prod.
// Pass only the pathname, e.g.  "/api/v1/ai/ws?foo=bar"
export function buildWsUrl(path: string) {
  if (typeof window === 'undefined') return path;     // SSR
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host  = window.location.host;                 // incl. port
  return `${proto}//${host}${path}`;
}
