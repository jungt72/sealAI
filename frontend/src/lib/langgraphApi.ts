import { getBackendInternalBase } from "@/lib/backend-internal";

const backendEnvCandidates = [
  process.env.NEXT_PUBLIC_BACKEND_URL,
  process.env.NEXT_PUBLIC_API_BASE,
].filter(Boolean) as string[];

const resolveBackendBase = (): string => {
  if (typeof window === "undefined") {
    return getBackendInternalBase();
  }
  if (backendEnvCandidates.length) {
    return backendEnvCandidates[0]!;
  }
  return window.location.origin;
};

const stripApiSuffix = (value: string): string => {
  const trimmed = value.replace(/\/+$/, "");
  return trimmed.replace(/\/api(?:\/v1)?$/i, "");
};

const langgraphBackendBase = (): string => stripApiSuffix(resolveBackendBase());

export const backendBaseUrl = (): string => langgraphBackendBase();

export const backendLangGraphChatEndpoint = (): string =>
  `/api/chat`;

export const backendLangGraphStateEndpoint = (): string =>
  `/api/langgraph/state`;
