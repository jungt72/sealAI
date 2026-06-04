const FALLBACK_BACKEND_ORIGIN = "http://127.0.0.1:8000";

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

export function getBackendOrigin(): string {
  const explicit = (process.env.SEALAI_BACKEND_ORIGIN || "").trim();
  if (explicit) {
    return trimTrailingSlash(explicit);
  }

  const publicBase = (process.env.NEXT_PUBLIC_API_BASE || "").trim();
  if (!publicBase) {
    return FALLBACK_BACKEND_ORIGIN;
  }

  const normalized = trimTrailingSlash(publicBase);
  if (normalized.endsWith("/api")) {
    return normalized.slice(0, -4);
  }
  if (normalized.endsWith("/api/v1")) {
    return normalized.slice(0, -7);
  }
  return normalized;
}

export function buildBackendUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${getBackendOrigin()}${normalizedPath}`;
}
