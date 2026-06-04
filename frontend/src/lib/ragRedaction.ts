export const REDACTED_PATH_LABEL = "interner Pfad redigiert";

const UNIX_INTERNAL_PATH_PATTERN =
  /(?:file:\/\/)?\/(?:Users|home|private|tmp|var|app|srv|mnt|opt|Volumes|data)(?:\/[^\s'"<>),;:]+)+/gi;
const WINDOWS_INTERNAL_PATH_PATTERN = /\b[A-Za-z]:\\(?:[^\\\s'"<>),;:]+\\?)+/g;
const REDACTED_PATH_TOKEN_PATTERN = /\[REDACTED_PATH\]/gi;

const INTERNAL_PATH_KEYS = new Set([
  "path",
  "absolute_path",
  "file_path",
  "filesystem_path",
  "source_path",
  "storage_path",
]);

export function redactInternalPaths(value: string): string {
  return value
    .replace(REDACTED_PATH_TOKEN_PATTERN, REDACTED_PATH_LABEL)
    .replace(UNIX_INTERNAL_PATH_PATTERN, REDACTED_PATH_LABEL)
    .replace(WINDOWS_INTERNAL_PATH_PATTERN, REDACTED_PATH_LABEL);
}

export function sanitizeUserVisibleText(value: unknown, fallback = ""): string {
  if (typeof value !== "string") return fallback;
  return redactInternalPaths(value);
}

export function sanitizeRagPayload<T>(payload: T): T {
  return sanitizeValue(payload) as T;
}

function sanitizeValue(value: unknown): unknown {
  if (typeof value === "string") {
    return redactInternalPaths(value);
  }

  if (Array.isArray(value)) {
    return value.map((item) => sanitizeValue(item));
  }

  if (!value || typeof value !== "object") {
    return value;
  }

  const next: Record<string, unknown> = {};
  for (const [key, rawValue] of Object.entries(value)) {
    const normalizedKey = key.toLowerCase();
    if (INTERNAL_PATH_KEYS.has(normalizedKey) && typeof rawValue === "string") {
      next[key] = REDACTED_PATH_LABEL;
      continue;
    }
    next[key] = sanitizeValue(rawValue);
  }
  return next;
}
