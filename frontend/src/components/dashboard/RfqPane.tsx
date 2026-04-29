"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Info,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";

import { StatusBadge } from "./CockpitElements";
import type { CockpitData } from "@/hooks/useCockpitData";
import {
  buildRfqPreviewConsentReadPath,
  buildRfqPreviewReadPath,
} from "@/lib/bff/workspace";
import { cn } from "@/lib/utils";

interface RfqPaneProps {
  data: CockpitData | null;
  caseId?: string;
}

type RfqPreviewSection = {
  index?: number;
  title?: string;
  content?: unknown;
  status?: string;
};

type RfqFieldStatus = {
  field?: string;
  value?: unknown;
  engineering_value?: Record<string, unknown> | null;
  status?: string;
  provenance?: string | null;
  confidence?: string | null;
  confirmation_required?: boolean;
  evidence_refs?: string[];
};

type RfqFieldGroup = {
  key?: string;
  title?: string;
  fields?: RfqFieldStatus[];
};

type RfqPreviewResponse = {
  preview_id: string;
  case_id: string;
  case_revision: number;
  current_case_revision: number;
  stale: boolean;
  consent_status: string;
  dispatch_enabled: boolean;
  created_at: string | null;
  payload?: {
    rfq_preview?: {
      sections?: RfqPreviewSection[];
      technical_field_groups?: RfqFieldGroup[];
      technical_field_statuses?: RfqFieldStatus[];
      confirmation_required_fields?: string[];
      manufacturer_release_boundary?: string;
    };
    consent_boundary?: {
      status?: string;
      open_points_acknowledgement_required?: boolean;
      no_final_release_acknowledgement_required?: boolean;
      requires_explicit_user_consent_before_sharing?: boolean;
      automatic_dispatch_allowed?: boolean;
    };
    decision_understanding?: {
      key_risks?: string[];
      manufacturer_review_needs?: string[];
      not_yet_decidable?: string[];
    };
  };
};

type ConsentState = {
  noFinalRelease: boolean;
  openPoints: boolean;
  exportSharing: boolean;
};

const EMPTY_SECTIONS: RfqPreviewSection[] = [];
const EMPTY_FIELD_STATUSES: RfqFieldStatus[] = [];
const EMPTY_FIELD_GROUPS: RfqFieldGroup[] = [];

function valueToText(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "Noch offen";
  }
  if (Array.isArray(value)) {
    return value.map(valueToText).join(", ");
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${key}: ${valueToText(item)}`)
      .join("; ");
  }
  return String(value);
}

function sectionItems(sections: RfqPreviewSection[], matcher: RegExp): string[] {
  return sections
    .filter((section) => matcher.test(section.title || ""))
    .flatMap((section) => {
      const content = section.content;
      if (Array.isArray(content)) {
        return content.map(valueToText);
      }
      if (content && typeof content === "object") {
        return Object.entries(content as Record<string, unknown>).map(
          ([key, value]) => `${key}: ${valueToText(value)}`,
        );
      }
      return content ? [valueToText(content)] : [];
    })
    .filter(Boolean);
}

function getErrorMessage(body: unknown, fallback: string) {
  if (body && typeof body === "object") {
    const record = body as {
      error?: { message?: string };
      detail?: { message?: string; code?: string } | string;
    };
    if (typeof record.detail === "string") {
      return record.detail || fallback;
    }
    return record.error?.message || record.detail?.message || record.detail?.code || fallback;
  }
  return fallback;
}

export default function RfqPane({ data, caseId }: RfqPaneProps) {
  const [preview, setPreview] = useState<RfqPreviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isGrantingConsent, setIsGrantingConsent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [consent, setConsent] = useState<ConsentState>({
    noFinalRelease: false,
    openPoints: false,
    exportSharing: false,
  });

  const loadPreview = async () => {
    if (!caseId) {
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(buildRfqPreviewReadPath(caseId), { cache: "no-store" });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        if (response.status === 404) {
          setPreview(null);
          return;
        }
        throw new Error(getErrorMessage(body, "RFQ-Preview konnte nicht geladen werden."));
      }
      setPreview(body as RfqPreviewResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "RFQ-Preview konnte nicht geladen werden.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadPreview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const sections = useMemo(
    () => preview?.payload?.rfq_preview?.sections ?? EMPTY_SECTIONS,
    [preview?.payload?.rfq_preview?.sections],
  );
  const fieldStatuses =
    preview?.payload?.rfq_preview?.technical_field_statuses ?? EMPTY_FIELD_STATUSES;
  const fieldGroups =
    preview?.payload?.rfq_preview?.technical_field_groups ?? EMPTY_FIELD_GROUPS;
  const openPoints = useMemo(
    () => sectionItems(sections, /Offene Punkte|unbestaetigte Annahmen/i),
    [sections],
  );
  const risks = useMemo(
    () => [
      ...sectionItems(sections, /Risiken/i),
      ...(preview?.payload?.decision_understanding?.key_risks ?? []),
    ],
    [preview?.payload?.decision_understanding?.key_risks, sections],
  );
  const manufacturerReviewNeeds = useMemo(
    () => [
      ...sectionItems(sections, /Fragen an den Hersteller/i),
      ...(preview?.payload?.decision_understanding?.manufacturer_review_needs ?? []),
    ],
    [preview?.payload?.decision_understanding?.manufacturer_review_needs, sections],
  );
  const consentReady =
    consent.noFinalRelease &&
    consent.openPoints &&
    consent.exportSharing &&
    Boolean(preview) &&
    !preview?.stale;

  const createPreview = async () => {
    if (!caseId) {
      return;
    }
    setIsCreating(true);
    setError(null);
    try {
      const response = await fetch(buildRfqPreviewReadPath(caseId), { method: "POST" });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(getErrorMessage(body, "RFQ-Preview konnte nicht vorbereitet werden."));
      }
      setPreview(body as RfqPreviewResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "RFQ-Preview konnte nicht vorbereitet werden.");
    } finally {
      setIsCreating(false);
    }
  };

  const grantConsent = async () => {
    if (!caseId || !preview || !consentReady) {
      return;
    }
    setIsGrantingConsent(true);
    setError(null);
    try {
      const sharedSections = sections
        .map((section) => section.title || `section_${section.index}`)
        .filter(Boolean);
      const response = await fetch(buildRfqPreviewConsentReadPath(caseId, preview.preview_id), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shared_sections: sharedSections.length > 0 ? sharedSections : ["RFQ-Preview"],
          shared_documents: [],
          intended_recipients: ["manual-export-by-user"],
          user_acknowledged_no_final_release: consent.noFinalRelease,
          user_acknowledged_open_points: consent.openPoints,
          user_acknowledged_export_intent: consent.exportSharing,
        }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(getErrorMessage(body, "Nutzerbestätigung konnte nicht gespeichert werden."));
      }
      setPreview(body as RfqPreviewResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nutzerbestätigung konnte nicht gespeichert werden.");
    } finally {
      setIsGrantingConsent(false);
    }
  };

  if (!data || !caseId) {
    return (
      <div className="rounded-[18px] border border-dashed border-[#D1D5DB] bg-white p-4 text-sm text-[#6B7280]">
        RFQ-Preview wird sichtbar, sobald der Fall im Backend gebunden ist.
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      <section className="rounded-[18px] border border-[#E5E7EB] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-[#F0F2F5] pb-3">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#6B7280]">
              Anfragebasis fuer Herstellerpruefung
            </div>
            <h2 className="mt-1 text-base font-semibold tracking-tight text-[#111827]">RFQ-Preview</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {preview && (
              <>
                <StatusBadge label={preview.stale ? "stale preview" : "current preview"} variant={preview.stale ? "warning" : "success"} />
                <StatusBadge label={`frozen revision ${preview.case_revision}`} variant="info" />
                <StatusBadge label={`current revision ${preview.current_case_revision}`} variant="default" />
              </>
            )}
            <button
              type="button"
              onClick={() => void loadPreview()}
              disabled={isLoading}
              className="flex h-9 w-9 items-center justify-center rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] text-[#4B5563] transition-colors hover:bg-[#F0F2F5]"
              aria-label="RFQ-Preview neu laden"
            >
              <RefreshCw size={15} className={cn(isLoading && "animate-spin")} />
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 flex items-start gap-2 rounded-[12px] border border-[#FDECEC] bg-[#FDECEC] px-3 py-2 text-sm text-[#991B1B]">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            {error}
          </div>
        )}

        {!preview ? (
          <div className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-4">
            <div className="flex items-start gap-3">
              <FileText className="mt-0.5 shrink-0 text-[#0B57D0]" size={18} />
              <div className="min-w-0">
                <div className="text-sm font-semibold text-[#111827]">Noch keine Backend-RFQ-Preview fuer diesen Fall geladen.</div>
                <p className="mt-1 text-sm text-[#4B5563]">
                  Die Anfragebasis wird aus dem Backend auf eine Case Revision eingefroren. Lokale Demo-Zusammenfassungen werden hier nicht als Produktwahrheit genutzt.
                </p>
                <button
                  type="button"
                  onClick={() => void createPreview()}
                  disabled={isCreating}
                  className="mt-3 rounded-[14px] bg-[#0B57D0] px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#0847AD] disabled:cursor-not-allowed disabled:bg-[#D1D5DB]"
                >
                  {isCreating ? "RFQ-Preview wird vorbereitet..." : "RFQ-Preview vorbereiten"}
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {preview.stale && (
              <div className="flex items-start gap-2 rounded-[12px] border border-[#FFF4E5] bg-[#FFF4E5] px-3 py-2 text-sm text-[#9A3412]">
                <ShieldAlert size={16} className="mt-0.5 shrink-0" />
                Diese RFQ-Preview ist stale: frozen Revision {preview.case_revision}, aktuelle Revision {preview.current_case_revision}. Bitte neu vorbereiten, bevor Nutzerbestätigung oder Export genutzt wird.
              </div>
            )}

            <div className="grid gap-3 sm:grid-cols-3">
              <MetaTile label="Preview ID" value={preview.preview_id} />
              <MetaTile label="Consent" value={preview.consent_status} />
              <MetaTile label="Weitergabe" value={preview.dispatch_enabled ? "aktiv" : "nicht vorgesehen"} />
            </div>

            <ListPanel title="Offene Punkte" items={openPoints} empty="Keine offenen Punkte in der Preview projiziert." tone="warning" />
            <ListPanel title="Risiken" items={risks} empty="Keine separaten Risiken in der Preview projiziert." tone="warning" />
            <ListPanel title="Herstellerpruefung" items={manufacturerReviewNeeds} empty="Keine separaten Prueffragen in der Preview projiziert." tone="neutral" />

            <section className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
              <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
                <Info size={14} />
                Field Status / Provenance / Evidence
              </div>
              {fieldGroups.length > 0 ? (
                <div className="grid gap-3">
                  {fieldGroups.map((group) => (
                    <div key={group.key || group.title} className="rounded-[12px] border border-[#E5E7EB] bg-white p-3">
                      <div className="mb-2 text-xs font-semibold text-[#111827]">{group.title || group.key}</div>
                      <div className="grid gap-2">
                        {(group.fields ?? []).map((field) => (
                          <FieldEnvelope key={`${group.key}-${field.field}-${field.status}`} field={field} />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : fieldStatuses.length > 0 ? (
                <div className="grid gap-2">
                  {fieldStatuses.map((field) => (
                    <FieldEnvelope key={`${field.field}-${field.status}`} field={field} />
                  ))}
                </div>
              ) : (
                <div className="rounded-[12px] border border-dashed border-[#D1D5DB] bg-white px-3 py-3 text-sm text-[#6B7280]">
                  Backend hat fuer diese Preview noch keine Field-Status-Projektion geliefert.
                </div>
              )}
            </section>

            <section className="rounded-[14px] border border-[#E5E7EB] bg-white p-3">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
                    Nutzerbestätigung erforderlich
                  </div>
                  <div className="mt-1 text-sm font-semibold text-[#111827]">Consent / Export vorbereiten</div>
                </div>
                {preview.consent_status === "granted" && (
                  <StatusBadge label="RFQ-Preview exportbereit" variant="success" />
                )}
              </div>
              <div className="space-y-2">
                <ConsentCheckbox
                  checked={consent.noFinalRelease}
                  onChange={(checked) => setConsent((current) => ({ ...current, noFinalRelease: checked }))}
                  label="Ich verstehe, dass diese RFQ-Preview keine finale technische Freigabe ist."
                />
                <ConsentCheckbox
                  checked={consent.openPoints}
                  onChange={(checked) => setConsent((current) => ({ ...current, openPoints: checked }))}
                  label="Ich verstehe die offenen Punkte und dass diese vom Hersteller geprüft werden müssen."
                />
                <ConsentCheckbox
                  checked={consent.exportSharing}
                  onChange={(checked) => setConsent((current) => ({ ...current, exportSharing: checked }))}
                  label="Ich möchte diese Anfragebasis nur als manuelle, von mir kontrollierte Weitergabe nutzen."
                />
              </div>
              <button
                type="button"
                onClick={() => void grantConsent()}
                disabled={!consentReady || isGrantingConsent}
                className="mt-3 flex items-center gap-2 rounded-[14px] bg-[#0B57D0] px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#0847AD] disabled:cursor-not-allowed disabled:bg-[#D1D5DB]"
              >
                <CheckCircle2 size={16} />
                {isGrantingConsent ? "Nutzerbestätigung wird gespeichert..." : "Nutzerbestätigung speichern"}
              </button>
            </section>
          </div>
        )}
      </section>
    </div>
  );
}

function MetaTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-2.5">
      <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">{label}</div>
      <div className="mt-1 break-all text-sm font-medium text-[#111827]">{value}</div>
    </div>
  );
}

function FieldEnvelope({ field }: { field: RfqFieldStatus }) {
  const unit = field.engineering_value?.unit;
  const value = valueToText(field.value);
  return (
    <div className="rounded-[12px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-semibold text-[#111827]">{field.field || "field"}</div>
        <StatusBadge label={field.status || "unspecified"} variant={field.confirmation_required ? "warning" : "info"} />
      </div>
      {field.value !== undefined ? (
        <div className="mt-1 text-sm text-[#111827]">
          Value: {value}
          {unit ? ` ${valueToText(unit)}` : ""}
        </div>
      ) : null}
      <div className="mt-1 text-xs text-[#4B5563]">
        Provenance: {field.provenance || "nicht geliefert"} · Confidence: {field.confidence || "nicht geliefert"}
      </div>
      {field.evidence_refs?.length ? (
        <div className="mt-1 text-xs text-[#4B5563]">Evidence: {field.evidence_refs.join(", ")}</div>
      ) : null}
      {field.confirmation_required ? (
        <div className="mt-1 text-xs font-medium text-[#B45309]">Confirmation erforderlich</div>
      ) : null}
    </div>
  );
}

function ListPanel({
  title,
  items,
  empty,
  tone,
}: {
  title: string;
  items: string[];
  empty: string;
  tone: "warning" | "neutral";
}) {
  return (
    <section className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">{title}</div>
      {items.length > 0 ? (
        <div className="space-y-2">
          {items.slice(0, 8).map((item) => (
            <div
              key={item}
              className={cn(
                "rounded-[12px] border px-3 py-2 text-sm",
                tone === "warning"
                  ? "border-[#FFF4E5] bg-[#FFF4E5] text-[#9A3412]"
                  : "border-[#E5E7EB] bg-white text-[#4B5563]",
              )}
            >
              {item}
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-[12px] border border-dashed border-[#D1D5DB] bg-white px-3 py-3 text-sm text-[#6B7280]">
          {empty}
        </div>
      )}
    </section>
  );
}

function ConsentCheckbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex items-start gap-3 rounded-[12px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-2 text-sm text-[#111827]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-1 h-4 w-4 rounded border-[#D1D5DB]"
      />
      <span>{label}</span>
    </label>
  );
}
