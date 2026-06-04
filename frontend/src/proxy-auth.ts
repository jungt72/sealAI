const CANONICAL_APP_HOST = "sealingai.com";
const LEGACY_APP_HOSTS = new Set(["sealai.net", "www.sealai.net", "www.sealingai.com"]);

export function canonicalizeAppUrl(url: URL): URL | null {
  const host = url.hostname.toLowerCase();
  if (!LEGACY_APP_HOSTS.has(host)) {
    return null;
  }

  const canonicalUrl = new URL(url);
  canonicalUrl.protocol = "https:";
  canonicalUrl.hostname = CANONICAL_APP_HOST;
  canonicalUrl.port = "";
  return canonicalUrl;
}

export function isProtectedPath(pathname: string): boolean {
  return pathname.startsWith("/dashboard") || pathname.startsWith("/goal") || pathname.startsWith("/rag");
}

export function shouldRedirectToSignIn(pathname: string, isLoggedIn: boolean): boolean {
  return isProtectedPath(pathname) && !isLoggedIn;
}
