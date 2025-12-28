export type TelemetryEvent =
  | { type: "chat_ttft"; chatId: string; ms: number }
  | { type: "chat_stream_done"; chatId: string; ms: number }
  | { type: "chat_retry"; chatId: string; attempt: number; reason: string }
  | { type: "chat_error"; chatId: string; code: number }
  | { type: "param_patch"; fields: number; ms: number; ok: boolean };

type TelemetrySink = {
  push?: (event: TelemetryEvent) => void;
};

export function emit(event: TelemetryEvent): void {
  if (typeof console !== "undefined" && console.debug) {
    console.debug("[telemetry]", event);
  }
  if (typeof window === "undefined") return;
  const sink = (window as typeof window & { __SEALAI_TELEMETRY__?: TelemetrySink })
    .__SEALAI_TELEMETRY__;
  sink?.push?.(event);
}
