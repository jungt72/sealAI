import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * shadcn/ui helper
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Default callback URL used across auth entrypoints.
 * Keep it relative so it works behind reverse proxies and on different origins.
 */
export const DEFAULT_CALLBACK_URL = "/dashboard";

/**
 * Normalize a callbackUrl to a safe relative URL.
 * - Accepts absolute URLs and strips origin
 * - Accepts relative URLs starting with "/"
 * - Falls back to DEFAULT_CALLBACK_URL for anything else
 */
export function toRelativeCallbackUrl(input?: string | null): string {
  if (!input) return DEFAULT_CALLBACK_URL;

  try {
    const u = new URL(input);
    const rel = `${u.pathname}${u.search}${u.hash}`;
    return rel.startsWith("/") ? rel : DEFAULT_CALLBACK_URL;
  } catch {
    return input.startsWith("/") ? input : DEFAULT_CALLBACK_URL;
  }
}
