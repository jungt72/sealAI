const stripApiSuffix = (value: string): string => {
  const trimmed = value.replace(/\/+$/, "");
  return trimmed.replace(/\/api(?:\/v1)?$/i, "");
};

export const getBackendInternalBase = (): string => {
  const raw =
    process.env.BACKEND_INTERNAL_URL ||
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    process.env.NEXT_PUBLIC_API_BASE ||
    "http://backend:8000";

  return stripApiSuffix(raw);
};
