"use client";

import * as React from "react";
import { useAccessToken } from "@/lib/useAccessToken";
import { useChatWs } from "@/lib/useChatWs";

type Props = { embedded?: boolean };

type FormState = {
  // RWDR
  wellen_mm?: number;
  gehause_mm?: number;
  breite_mm?: number;
  medium?: string;
  temp_max_c?: number;
  druck_bar?: number;
  drehzahl_u_min?: number;
  // Hydraulik – Stange
  stange_mm?: number;
  nut_d_mm?: number;
  nut_b_mm?: number;
  geschwindigkeit_m_s?: number;
};

const LABELS: Record<string, string> = {
  falltyp: "Anwendungsfall",
  bauform: "Bauform/Profil",
  wellen_mm: "Welle (mm)",
  gehause_mm: "Gehäuse (mm)",
  breite_mm: "Breite (mm)",
  medium: "Medium",
  temp_max_c: "Tmax (°C)",
  druck_bar: "Druck (bar)",
  drehzahl_u_min: "Drehzahl (U/min)",
  stange_mm: "Stange (mm)",
  nut_d_mm: "Nut-Ø D (mm)",
  nut_b_mm: "Nutbreite B (mm)",
  geschwindigkeit_m_s: "v (m/s)",
};

function toNum(v: string): number | undefined {
  if (v === "" || v == null) return undefined;
  const n = Number(String(v).replace(",", "."));
  return Number.isFinite(n) ? n : undefined;
}

function formatOneLine(f: FormState): string {
  const parts: string[] = [];
  if (f.wellen_mm) parts.push(`Welle ${f.wellen_mm}`);
  if (f.gehause_mm) parts.push(`Gehäuse ${f.gehause_mm}`);
  if (f.breite_mm) parts.push(`Breite ${f.breite_mm}`);
  if (f.stange_mm) parts.push(`Stange ${f.stange_mm}`);
  if (f.nut_d_mm) parts.push(`Nut D ${f.nut_d_mm}`);
  if (f.nut_b_mm) parts.push(`Nut B ${f.nut_b_mm}`);
  if (typeof f.geschwindigkeit_m_s !== "undefined") parts.push(`v ${f.geschwindigkeit_m_s} m/s`);
  if (f.medium) parts.push(`Medium ${f.medium}`);
  if (typeof f.temp_max_c !== "undefined") parts.push(`Tmax ${f.temp_max_c}`);
  if (typeof f.druck_bar !== "undefined") parts.push(`Druck ${f.druck_bar} bar`);
  if (typeof f.drehzahl_u_min !== "undefined") parts.push(`n ${f.drehzahl_u_min}`);
  return parts.join(", ");
}

function filled(v: unknown) {
  return !(v === undefined || v === null || v === "");
}

const baseInput =
  "mt-1 w-full rounded px-3 py-2 text-sm transition border outline-none focus:ring-2 focus:ring-blue-200";
const cls = (isFilled: boolean) =>
  [
    baseInput,
    isFilled ? "text-black font-semibold border-gray-900" : "text-gray-700 border-gray-300 placeholder-gray-400",
  ].join(" ");

function FormInner({
  form,
  setForm,
  missing,
  patch,
  submitAll,
  clearAll,
  containerRef,
}: {
  form: FormState;
  setForm: React.Dispatch<React.SetStateAction<FormState>>;
  missing: string[];
  patch: (k: keyof FormState, v: any) => void;
  submitAll: () => void;
  clearAll: () => void;
  containerRef: React.RefObject<HTMLDivElement>;
}) {
  return (
    <>
      {missing.length > 0 && (
        <div className="mb-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          Fehlend: {missing.join(", ")}
        </div>
      )}

      <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
        {/* RWDR */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.wellen_mm}</label>
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              placeholder="z. B. 25"
              className={cls(filled(form.wellen_mm))}
              value={form.wellen_mm ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, wellen_mm: toNum(e.target.value) }))}
              onBlur={(e) => patch("wellen_mm", toNum(e.target.value))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.gehause_mm}</label>
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              placeholder="z. B. 47"
              className={cls(filled(form.gehause_mm))}
              value={form.gehause_mm ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, gehause_mm: toNum(e.target.value) }))}
              onBlur={(e) => patch("gehause_mm", toNum(e.target.value))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.breite_mm}</label>
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              placeholder="z. B. 7"
              className={cls(filled(form.breite_mm))}
              value={form.breite_mm ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, breite_mm: toNum(e.target.value) }))}
              onBlur={(e) => patch("breite_mm", toNum(e.target.value))}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="md:col-span-1">
            <label className="block text-sm font-medium text-gray-700">{LABELS.medium}</label>
            <input
              type="text"
              placeholder="z. B. Hydrauliköl"
              className={cls(filled(form.medium))}
              value={form.medium ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, medium: e.target.value }))}
              onBlur={(e) => patch("medium", e.target.value.trim() || undefined)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.temp_max_c}</label>
            <input
              type="number"
              inputMode="decimal"
              step="1"
              placeholder="z. B. 80"
              className={cls(filled(form.temp_max_c))}
              value={form.temp_max_c ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, temp_max_c: toNum(e.target.value) }))}
              onBlur={(e) => patch("temp_max_c", toNum(e.target.value))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.druck_bar}</label>
            <input
              type="number"
              inputMode="decimal"
              step="0.1"
              placeholder="z. B. 2"
              className={cls(filled(form.druck_bar))}
              value={form.druck_bar ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, druck_bar: toNum(e.target.value) }))}
              onBlur={(e) => patch("druck_bar", toNum(e.target.value))}
            />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.drehzahl_u_min}</label>
            <input
              type="number"
              inputMode="numeric"
              step="1"
              placeholder="z. B. 1500"
              className={cls(filled(form.drehzahl_u_min))}
              value={form.drehzahl_u_min ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, drehzahl_u_min: toNum(e.target.value) }))}
              onBlur={(e) => patch("drehzahl_u_min", toNum(e.target.value))}
            />
          </div>
        </div>

        {/* Hydraulik – Stange */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.stange_mm}</label>
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              placeholder="z. B. 25"
              className={cls(filled(form.stange_mm))}
              value={form.stange_mm ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, stange_mm: toNum(e.target.value) }))}
              onBlur={(e) => patch("stange_mm", toNum(e.target.value))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.nut_d_mm}</label>
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              placeholder="z. B. 32"
              className={cls(filled(form.nut_d_mm))}
              value={form.nut_d_mm ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, nut_d_mm: toNum(e.target.value) }))}
              onBlur={(e) => patch("nut_d_mm", toNum(e.target.value))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.nut_b_mm}</label>
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              placeholder="z. B. 6"
              className={cls(filled(form.nut_b_mm))}
              value={form.nut_b_mm ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, nut_b_mm: toNum(e.target.value) }))}
              onBlur={(e) => patch("nut_b_mm", toNum(e.target.value))}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">{LABELS.geschwindigkeit_m_s}</label>
            <input
              type="number"
              inputMode="decimal"
              step="0.01"
              placeholder="z. B. 0.3"
              className={cls(filled(form.geschwindigkeit_m_s))}
              value={form.geschwindigkeit_m_s ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, geschwindigkeit_m_s: toNum(e.target.value) }))}
              onBlur={(e) => patch("geschwindigkeit_m_s", toNum(e.target.value))}
            />
          </div>
        </div>
      </form>

      <div className="border-t px-4 py-3 mt-4 flex items-center justify-between gap-2">
        <div className="text-xs text-gray-500">
          {missing.length > 0 ? "Bitte Felder ergänzen und übernehmen." : "\u00A0"}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50"
            onClick={clearAll}
          >
            Zurücksetzen
          </button>
          <button
            type="button"
            className="rounded-md bg-emerald-600 text-white px-3 py-1.5 text-sm hover:bg-emerald-700"
            onClick={submitAll}
          >
            Übernehmen
          </button>
        </div>
      </div>
    </>
  );
}

export default function SidebarForm({ embedded = false }: Props) {
  const token = useAccessToken();
  const { send } = useChatWs({ chatId: "default", token });

  const [open, setOpen] = React.useState(false);
  const [missing, setMissing] = React.useState<string[]>([]);
  const [form, setForm] = React.useState<FormState>({});
  const containerRef = React.useRef<HTMLDivElement>(null);
  const patchTimer = React.useRef<number | null>(null);

  const mergePrefill = React.useCallback((ua: any) => {
    const pre = ua?.prefill ?? ua?.params ?? {};
    const miss = Array.isArray(ua?.missing) ? ua.missing : undefined;
    if (miss) setMissing(miss);
    if (pre && typeof pre === "object") setForm((prev) => ({ ...prev, ...pre }));
  }, []);

  React.useEffect(() => {
    const onUi = (ev: Event) => {
      const ua: any = (ev as CustomEvent<any>).detail ?? (ev as any);
      const action = ua?.ui_action ?? ua?.action;
      if (action === "open_form" || ua?.prefill || ua?.params) {
        mergePrefill(ua);
        if (!embedded && action === "open_form") setOpen(true);
        setTimeout(() => {
          const root = containerRef.current;
          const first =
            root?.querySelector<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>(
              "input, textarea, select",
            );
          first?.focus();
        }, 0);
      }
    };
    // Neuer Standard-Eventname
    window.addEventListener("sealai:ui", onUi as EventListener);
    // Abwärtskompatibel
    window.addEventListener("sealai:ui_action", onUi as EventListener);
    window.addEventListener("sai:need-params", onUi as EventListener);
    window.addEventListener("sealai:form:patch", onUi as EventListener);
    return () => {
      window.removeEventListener("sealai:ui", onUi as EventListener);
      window.removeEventListener("sealai:ui_action", onUi as EventListener);
      window.removeEventListener("sai:need-params", onUi as EventListener);
      window.removeEventListener("sealai:form:patch", onUi as EventListener);
    };
  }, [embedded, mergePrefill]);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const patch = React.useCallback(
    (k: keyof FormState, v: any) => {
      setForm((cur) => ({ ...cur, [k]: v }));
      const payloadValue =
        typeof v === "number"
          ? Number.isFinite(v)
            ? v
            : undefined
          : (v && String(v).trim()) || undefined;
      if (patchTimer.current) window.clearTimeout(patchTimer.current);
      patchTimer.current = window.setTimeout(() => {
        if (typeof payloadValue !== "undefined") {
          send("📝 form patch", { params: { [k]: payloadValue } });
        }
      }, 180);
    },
    [send],
  );

  const submitAll = () => {
    const cleaned: Record<string, any> = {};
    for (const [k, v] of Object.entries(form)) {
      if (v === "" || v == null) continue;
      cleaned[k] = v;
    }
    send("📝 form submit", { params: cleaned });
    const summary = formatOneLine(cleaned as FormState);
    if (summary) {
      window.dispatchEvent(
        new CustomEvent("sealai:chat:add", {
          detail: { text: summary, source: "sidebar_form", action: "submit", params: cleaned },
        }),
      );
    }
    if (!embedded) setOpen(false);
  };

  const clearAll = () => setForm({});

  if (embedded) {
    return (
      <div className="p-2" ref={containerRef}>
        <FormInner
          form={form}
          setForm={setForm}
          missing={missing}
          patch={patch}
          submitAll={submitAll}
          clearAll={clearAll}
          containerRef={containerRef}
        />
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-40 pointer-events-none" aria-hidden={!open}>
      <div
        className={[
          "pointer-events-auto absolute right-0 top-0 h-full w-[360px] max-w-[90vw]",
          "bg-white shadow-xl border-l border-gray-200",
          "transition-transform duration-300 ease-out",
          open ? "translate-x-0" : "translate-x-full",
        ].join(" ")}
        role="dialog"
        aria-modal="false"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <div className="font-semibold">Beratungs-Formular</div>
          <button
            type="button"
            className="rounded px-2 py-1 text-sm hover:bg-gray-100"
            onClick={() => setOpen(false)}
            aria-label="Schließen"
          >
            ✕
          </button>
        </div>
        <div className="p-4 overflow-y-auto h-[calc(100%-56px)]" ref={containerRef}>
          <FormInner
            form={form}
            setForm={setForm}
            missing={missing}
            patch={patch}
            submitAll={submitAll}
            clearAll={clearAll}
            containerRef={containerRef}
          />
        </div>
      </div>
    </div>
  );
}
