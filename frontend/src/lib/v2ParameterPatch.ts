"use client";

import { dbg, isParamSyncDebug } from "@/lib/paramSyncDebug";
import { fetchWithAuth } from "@/lib/fetchWithAuth";

export type SidebarFormPatch = Record<string, unknown>;

export type V2ParametersPatch = Record<string, string | number | boolean>;

const STATE_FETCH_MAX_ATTEMPTS = 5;
const STATE_FETCH_BASE_BACKOFF_MS = 500;
const STATE_FETCH_MAX_BACKOFF_MS = 30_000;
const STATE_FETCH_MIN_INTERVAL_MS = 2_000;
const stateFetchLastAttemptMsByChat = new Map<string, number>();

export class LanggraphStateFetchError extends Error {
  status: number;
  code: string | null;

  constructor(message: string, status: number, code?: string | null) {
    super(message);
    this.name = "LanggraphStateFetchError";
    this.status = status;
    this.code = code ?? null;
  }
}

const isRetryableStatus = (status: number): boolean => status === 429 || status >= 500;

const parseRetryAfterMs = (raw: string | null): number | null => {
  if (!raw) return null;
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const seconds = Number(trimmed);
  if (Number.isFinite(seconds) && seconds >= 0) {
    return Math.round(seconds * 1000);
  }
  const dateValue = Date.parse(trimmed);
  if (!Number.isFinite(dateValue)) return null;
  const delta = dateValue - Date.now();
  return delta > 0 ? delta : 0;
};

const computeBackoffMs = (attempt: number): number => {
  const exponential = STATE_FETCH_BASE_BACKOFF_MS * (2 ** Math.max(0, attempt - 1));
  return Math.min(STATE_FETCH_MAX_BACKOFF_MS, exponential);
};

const waitForRetry = (ms: number, signal?: AbortSignal): Promise<void> =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = window.setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, Math.max(0, ms));
    const onAbort = () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });

const parseStateErrorResponse = async (res: Response): Promise<{ message: string; code: string | null }> => {
  const fallback = `HTTP ${res.status}`;
  try {
    const body = await res.json();
    const rawDetail =
      body && typeof body === "object"
        ? (body as Record<string, unknown>).detail
        : null;
    const detailString = typeof rawDetail === "string" ? rawDetail : null;
    const detail =
      rawDetail && typeof rawDetail === "object"
        ? (rawDetail as Record<string, unknown>)
        : null;
    const directCode =
      body && typeof body === "object" && typeof (body as Record<string, unknown>).code === "string"
        ? String((body as Record<string, unknown>).code)
        : null;
    const detailCode = detail && typeof detail.code === "string" ? String(detail.code) : null;
    const detailMessage = detail && typeof detail.message === "string" ? String(detail.message) : null;
    const bodyMessage =
      body && typeof body === "object" && typeof (body as Record<string, unknown>).message === "string"
        ? String((body as Record<string, unknown>).message)
        : null;
    return {
      message: detailMessage || bodyMessage || detailString || fallback,
      code: detailCode || directCode || (detailString === "session_expired" ? "session_expired" : null),
    };
  } catch {
    const text = await res.text().catch(() => "");
    return { message: text || fallback, code: null };
  }
};

export const isSessionExpiredStateError = (err: unknown): err is LanggraphStateFetchError =>
  err instanceof LanggraphStateFetchError &&
  err.status === 401 &&
  (err.code === "session_expired" || err.code === "invalid_token" || err.code == null);

const normalizeV2StateParameters = (raw: V2ParametersPatch): V2ParametersPatch => {
  const normalized: V2ParametersPatch = { ...raw };
  if ("pressure" in normalized) {
    if (normalized.pressure !== undefined && normalized.pressure !== null) {
      normalized.pressure_bar = normalized.pressure;
    }
    delete normalized.pressure;
  }
  return normalized;
};

export function normalizeSidebarFormPatchToV2(patch: SidebarFormPatch): V2ParametersPatch {
  const out: V2ParametersPatch = {};

  const setNumber = (key: string, value: unknown) => {
    if (value === null || value === undefined) return;
    if (typeof value === "number" && Number.isFinite(value)) {
      out[key] = value;
      return;
    }
    if (typeof value === "string") {
      const trimmed = value.trim();
      if (!trimmed) return;
      const parsed = Number(trimmed.replace(",", "."));
      if (Number.isFinite(parsed)) out[key] = parsed;
    }
  };

  const setString = (key: string, value: unknown) => {
    if (typeof value !== "string") return;
    const trimmed = value.trim();
    if (!trimmed) return;
    out[key] = trimmed;
  };

  setString("medium", patch["medium"]);
  setNumber("pressure_bar", patch["druck_bar"]);
  setNumber("temperature_C", patch["temp_max_c"]);
  setNumber("speed_rpm", patch["drehzahl_u_min"]);
  setNumber("shaft_diameter", patch["wellen_mm"]);

  // Optional extra mappings (keep minimal; safe to ignore if absent)
  setNumber("housing_diameter", patch["gehause_mm"]);

  return out;
}

export async function patchV2Parameters(opts: {
  chatId: string;
  token: string;
  parameters: V2ParametersPatch;
  baseVersions?: Record<string, number>;
}): Promise<void> {
  const start = performance.now();
  const baseVersions: Record<string, number> = {};
  for (const key of Object.keys(opts.parameters || {})) {
    const raw = opts.baseVersions?.[key];
    baseVersions[key] = typeof raw === "number" ? raw : 0;
  }
  if (isParamSyncDebug()) {
    const entries = Object.entries(opts.parameters || {}).map(([key, value]) => ({
      key,
      value,
      type: typeof value,
    }));
    dbg("patch_payload", {
      chat_id: opts.chatId,
      keys: entries.map((entry) => entry.key),
      values: entries,
      ts: new Date().toISOString(),
    });
  }
  const res = await fetchWithAuth("/api/v1/langgraph/parameters/patch", opts.token, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      chat_id: opts.chatId,
      parameters: opts.parameters,
      base_versions: baseVersions,
    }),
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => "");
    throw new Error(msg || `HTTP ${res.status}`);
  }
  if (isParamSyncDebug()) {
    dbg("patch_done", { chat_id: opts.chatId, ms: performance.now() - start });
  }
}

export async function fetchV2StateParameters(opts: {
  chatId: string;
  token: string;
  signal?: AbortSignal;
}): Promise<V2ParametersPatch> {
  const body = await fetchV2State(opts);
  if (body && typeof body.parameters === "object" && body.parameters) {
    return normalizeV2StateParameters(body.parameters as V2ParametersPatch);
  }
  return {};
}

export async function fetchV2State(opts: {
  chatId: string;
  token: string;
  signal?: AbortSignal;
}): Promise<Record<string, unknown>> {
  const token = (opts.token || "").trim();
  if (!token) {
    throw new LanggraphStateFetchError("missing_token", 401, "missing_token");
  }
  const chatKey = (opts.chatId || "").trim();
  if (chatKey) {
    const lastAttemptAt = stateFetchLastAttemptMsByChat.get(chatKey) ?? 0;
    const elapsed = Date.now() - lastAttemptAt;
    if (elapsed < STATE_FETCH_MIN_INTERVAL_MS) {
      await waitForRetry(STATE_FETCH_MIN_INTERVAL_MS - elapsed, opts.signal);
    }
    stateFetchLastAttemptMsByChat.set(chatKey, Date.now());
  }
  const url = `/api/langgraph/state?thread_id=${encodeURIComponent(opts.chatId)}`;
  const start = performance.now();
  let body: Record<string, unknown> = {};
  let networkError: Error | null = null;

  for (let attempt = 1; attempt <= STATE_FETCH_MAX_ATTEMPTS; attempt += 1) {
    try {
      const res = await fetchWithAuth(url, token, {
        method: "GET",
        cache: "no-store",
        signal: opts.signal,
      });
      if (res.ok) {
        body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
        networkError = null;
        break;
      }

      const { message, code } = await parseStateErrorResponse(res);
      if (res.status === 404 && code === "state_not_found") {
        throw new LanggraphStateFetchError(message || "state_not_found", 404, "state_not_found");
      }
      if (!isRetryableStatus(res.status) || attempt >= STATE_FETCH_MAX_ATTEMPTS) {
        throw new LanggraphStateFetchError(message || `HTTP ${res.status}`, res.status, code);
      }
      const retryAfterMs = parseRetryAfterMs(res.headers.get("Retry-After"));
      const delayMs = retryAfterMs ?? computeBackoffMs(attempt);
      await waitForRetry(delayMs, opts.signal);
      continue;
    } catch (err: any) {
      if (err?.name === "AbortError") throw err;
      if (err instanceof LanggraphStateFetchError) throw err;
      networkError = err instanceof Error ? err : new Error(String(err));
      if (attempt >= STATE_FETCH_MAX_ATTEMPTS) break;
      await waitForRetry(computeBackoffMs(attempt), opts.signal);
    }
  }

  if (networkError) throw networkError;

  if (isParamSyncDebug()) {
    const rawParams = body && typeof body.parameters === "object" ? body.parameters : {};
    const entries = rawParams && typeof rawParams === "object"
      ? Object.entries(rawParams).map(([key, value]) => ({
        key,
        value,
        type: typeof value,
      }))
      : [];
    dbg("state_payload", {
      chat_id: opts.chatId,
      keys: entries.map((entry) => entry.key),
      values: entries,
      ms: performance.now() - start,
      ts: new Date().toISOString(),
    });
  }
  return body;
}

export async function patchV2ParametersAndFetchState(opts: {
  chatId: string;
  token: string;
  parameters: V2ParametersPatch;
  baseVersions?: Record<string, number>;
  signal?: AbortSignal;
}): Promise<V2ParametersPatch> {
  await patchV2Parameters(opts);
  return fetchV2StateParameters({ chatId: opts.chatId, token: opts.token, signal: opts.signal });
}
