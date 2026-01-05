// 📁 frontend/app/lib/utils.ts
export function cn(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

const LOCALHOST_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);
export const DEFAULT_CALLBACK_URL = "/dashboard";

export function toRelativeCallbackUrl(
  value: string,
  baseOrigin?: string,
  fallbackPath = DEFAULT_CALLBACK_URL,
): string {
  if (!value) return fallbackPath;
  if (value.startsWith("//")) return fallbackPath;
  if (value.startsWith("/")) return value;
  try {
    const url = new URL(value);
    if (LOCALHOST_HOSTS.has(url.hostname)) return fallbackPath;
    const resolvedBase =
      baseOrigin || (typeof window !== "undefined" ? window.location.origin : "");
    if (!resolvedBase) return fallbackPath;
    const base = new URL(resolvedBase);
    if (url.origin !== base.origin) return fallbackPath;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return fallbackPath;
  }
}
