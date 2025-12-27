const backendEnvCandidates = [
  process.env.NEXT_PUBLIC_BACKEND_URL,
  process.env.NEXT_PUBLIC_API_BASE,
  process.env.BACKEND_URL,
  process.env.API_BASE,
].filter(Boolean) as string[];

const resolveBackendBase = (): string => {
  if (backendEnvCandidates.length) {
    return backendEnvCandidates[0]!;
  }
  if (typeof window !== "undefined") {
    return window.location.origin;
  }
  return "";
};

const stripApiSuffix = (value: string): string => {
  const trimmed = value.replace(/\/+$/, "");
  return trimmed.replace(/\/api(?:\/v1)?$/i, "");
};

const langgraphBackendBase = (): string => stripApiSuffix(resolveBackendBase());

export const backendBaseUrl = (): string => langgraphBackendBase();

export const backendLangGraphChatEndpoint = (): string =>
  `${langgraphBackendBase()}/api/v1/langgraph/chat/v2`;

export const backendLangGraphStateEndpoint = (): string =>
  `${langgraphBackendBase()}/api/v1/langgraph/state`;
