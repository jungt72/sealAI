"use client";

export type SidebarFormPatch = Record<string, unknown>;

export type V2ParametersPatch = Record<string, string | number | boolean>;

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
}): Promise<void> {
  if (process.env.NEXT_PUBLIC_PARAM_SYNC_DEBUG === "1") {
    console.log("[param-sync] patch_payload", {
      chat_id: opts.chatId,
      parameters: opts.parameters,
    });
  }
  const res = await fetch("/api/v1/langgraph/parameters/patch", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${opts.token}`,
    },
    body: JSON.stringify({ chat_id: opts.chatId, parameters: opts.parameters }),
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => "");
    throw new Error(msg || `HTTP ${res.status}`);
  }
}

export async function fetchV2StateParameters(opts: {
  chatId: string;
  token: string;
  signal?: AbortSignal;
}): Promise<V2ParametersPatch> {
  const url = `/api/v1/langgraph/state?thread_id=${encodeURIComponent(opts.chatId)}`;
  const res = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${opts.token}`,
    },
    signal: opts.signal,
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => "");
    throw new Error(msg || `HTTP ${res.status}`);
  }
  const body = await res.json().catch(() => ({}));
  if (body && typeof body.parameters === "object" && body.parameters) {
    return body.parameters as V2ParametersPatch;
  }
  return {};
}

export async function patchV2ParametersAndFetchState(opts: {
  chatId: string;
  token: string;
  parameters: V2ParametersPatch;
  signal?: AbortSignal;
}): Promise<V2ParametersPatch> {
  await patchV2Parameters(opts);
  return fetchV2StateParameters({ chatId: opts.chatId, token: opts.token, signal: opts.signal });
}
