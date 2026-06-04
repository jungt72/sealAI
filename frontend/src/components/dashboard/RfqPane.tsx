"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileText,
  Info,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";

import { StatusBadge } from "./CockpitElements";
import type { WorkspaceRfqReadinessProjection, WorkspaceView } from "@/lib/contracts/workspace";
import {
  buildRfqPreviewConsentReadPath,
  buildRfqPreviewExportReadPath,
  buildRfqPreviewReadPath,
  buildRwdrAnalyzeReadPath,
  buildRwdrCaseBriefReadPath,
  buildRwdrCaseDiffReadPath,
  buildRwdrCaseExportReadPath,
  buildRwdrCasePdfReadPath,
  buildRwdrCaseReadPath,
  buildRwdrCaseSnapshotsReadPath,
  buildRwdrConfirmationsReadPath,
} from "@/lib/bff/workspace";
import { trackProductEvent, trackSeoEvent } from "@/lib/analytics/events";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";
import { cn } from "@/lib/utils";

interface RfqPaneProps {
  data: unknown | null;
  caseId?: string;
  workspace?: WorkspaceView | null;
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

type TechnicalRwdrBriefField = {
  field?: string;
  value?: unknown;
  unit?: string | null;
  status?: string | null;
  provenance?: string | null;
  source_type?: string | null;
  validation_status?: string | null;
  evidence_refs?: string[];
  source_span?: string | null;
  origin?: string | null;
  confirmation_status?: string | null;
  liability_bearing?: boolean;
  allowed_in_brief?: boolean;
  blocked_reason?: string | null;
};

type RwdrCandidateField = TechnicalRwdrBriefField & {
  field: string;
  confirmation_required?: boolean;
  previous_value?: unknown;
  user_action_timestamp?: string | null;
};

type RwdrCaseState = {
  case_id?: string;
  raw_inquiry_text?: string;
  evidence_fields?: RwdrCandidateField[];
  candidate_fields?: RwdrCandidateField[];
  technical_rwdr_rfq_brief?: TechnicalRwdrBrief;
  export_markdown?: string;
  missing_critical_fields?: string[];
  missing_helpful_fields?: string[];
};

type RwdrSnapshotSummary = {
  revision_number?: number;
  event_type?: string;
  created_at?: string | null;
  deterministic_payload_hash?: string | null;
};

type RwdrRevisionDiff = {
  case_id?: string;
  from_revision?: number;
  to_revision?: number;
  from_event_type?: string;
  to_event_type?: string;
  summary?: {
    changed_fields_count?: number;
    added_missing_fields_count?: number;
    removed_missing_fields_count?: number;
    status_changed?: boolean;
    brief_changed?: boolean;
    export_changed?: boolean;
  };
  status_diff?: { from?: string | null; to?: string | null };
  evidence_field_diffs?: Array<{
    field?: string;
    change_type?: string;
    from?: Record<string, unknown>;
    to?: Record<string, unknown>;
    source_span_changed?: boolean;
  }>;
  missing_critical_fields_diff?: { added?: string[]; removed?: string[]; unchanged?: string[] };
  missing_helpful_fields_diff?: { added?: string[]; removed?: string[]; unchanged?: string[] };
  computed_values_diff?: DiffList;
  review_flags_diff?: DiffList;
  manufacturer_questions_diff?: DiffList;
  measurement_recommendations_diff?: DiffList;
  brief_diff?: { brief_present_from?: boolean; brief_present_to?: boolean; section_changes?: Array<Record<string, unknown>> };
  export_diff?: {
    markdown_export_changed?: boolean;
    pdf_export_changed?: boolean;
    from_export_reference?: Record<string, unknown>;
    to_export_reference?: Record<string, unknown>;
    export_metadata_changed?: boolean;
  };
  audit_metadata?: { audit_metadata_excluded_from_deterministic_diff?: boolean };
};

type DiffList = {
  added?: unknown[];
  changed?: unknown[];
  removed?: unknown[];
};

type TechnicalRwdrBrief = {
  artifact_title?: string;
  artifact_type?: string;
  schema_version?: string;
  status?: "COMPLETE" | "NEEDS_CLARIFICATION" | "OUT_OF_SCOPE" | string;
  no_final_technical_release?: boolean;
  dispatch_enabled?: boolean;
  manufacturer_matching_enabled?: boolean;
  evaluation?: {
    complete_enough_for_manufacturer_evaluation?: boolean;
    open_points?: string[];
    out_of_scope_reasons?: string[];
  };
  confirmed_case_fields?: TechnicalRwdrBriefField[];
  calculation_fields?: TechnicalRwdrBriefField[];
  open_fields?: TechnicalRwdrBriefField[];
  sections?: Array<{ id?: string; title?: string; items?: unknown[] }>;
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
      technical_rwdr_rfq_brief?: TechnicalRwdrBrief;
      confirmation_required_fields?: string[];
      manufacturer_release_boundary?: string;
    };
    technical_rwdr_rfq_brief?: TechnicalRwdrBrief;
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
const RWDR_LIABILITY_FIELDS = new Set([
  "shaft_diameter_d1_mm",
  "housing_bore_D_mm",
  "seal_width_b_mm",
  "sealing_function",
  "inside_medium",
  "concentration",
  "temperature_min_c",
  "temperature_max_c",
  "transient_temperature_c",
  "pressure_differential",
  "max_speed_rpm",
  "rotation_direction",
  "material",
  "standards",
  "manufacturer_code",
  "old_part_number",
  "hazardous_chemical_indication",
  "food_hygiene_requirement",
  "application",
  "seal_family",
  "sealing_type",
]);

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

function uniqueTexts(items: string[], limit = 12): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  for (const item of items) {
    const text = item.trim();
    if (!text || seen.has(text)) {
      continue;
    }
    seen.add(text);
    result.push(text);
    if (result.length >= limit) {
      break;
    }
  }
  return result;
}

function rwdrStatusLabel(status: string | undefined): string {
  if (status === "COMPLETE") {
    return "vollständig für Herstellerprüfung";
  }
  if (status === "OUT_OF_SCOPE") {
    return "außerhalb RWDR-MVP";
  }
  return "Klärung erforderlich";
}

function rwdrStatusVariant(status: string | undefined): "success" | "warning" | "info" {
  if (status === "COMPLETE") {
    return "success";
  }
  if (status === "OUT_OF_SCOPE") {
    return "warning";
  }
  return "info";
}

function briefFieldText(field: TechnicalRwdrBriefField): string {
  const value = valueToText(field.value);
  const unit = field.unit ? ` ${field.unit}` : "";
  return `${field.field || "field"}: ${value}${unit}`;
}

function diffValue(value: unknown): string {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    if (record.field) {
      return `${String(record.field)}: ${valueToText(record.value ?? record.method ?? record.question ?? record.flag ?? record)}`;
    }
    if (record.section_id) {
      return `${String(record.section_id)}: ${valueToText(record.change_type)}`;
    }
  }
  return valueToText(value);
}

function fieldLabel(field: string | undefined): string {
  const labels: Record<string, string> = {
    shaft_diameter_d1_mm: "Wellendurchmesser d1",
    housing_bore_D_mm: "Gehäusebohrung D",
    seal_width_b_mm: "Dichtungsbreite b",
    sealing_function: "Abdichtfunktion",
    inside_medium: "Innenmedium",
    temperature_min_c: "Minimale Temperatur",
    temperature_max_c: "Maximale Temperatur",
    pressure_differential: "Druckdifferenz",
    max_speed_rpm: "Drehzahl",
    application: "Anwendung",
    seal_family: "Dichtungsfamilie",
  };
  return field ? labels[field] || field.replace(/_/g, " ") : "Feld";
}

function sectionTitle(sectionId: string | undefined, fallback: string | undefined): string {
  const titles: Record<string, string> = {
    status: "Status",
    case_type: "Anfrageart",
    confirmed_data: "Bestätigte Angaben",
    unconfirmed_data: "Nicht bestätigte Angaben",
    missing_critical_fields: "Kritisch fehlende Angaben",
    missing_helpful_fields: "Hilfreich fehlende Angaben",
    computed_values: "Berechnete Werte",
    engineering_review_flags: "Engineering Review-Themen",
    recommended_measurement_and_verification_data: "Empfohlene Mess- und Prüfangaben für Herstellerbewertung",
    manufacturer_questions: "Herstellerfragen",
    regulatory_and_documentation_requirements: "Dokumentations-/Regulatorikanforderungen",
    leakage_and_service_life_expectations: "Leckage- und Standzeiterwartungen",
    source_evidence_summary: "Quellenübersicht",
    disclaimer: "Disclaimer",
  };
  return sectionId ? titles[sectionId] || fallback || sectionId : fallback || "Section";
}

function briefToMarkdown(brief: TechnicalRwdrBrief): string {
  const lines = ["# Technical RWDR RFQ Brief", "", `Status: ${brief.status || "NEEDS_CLARIFICATION"}`, ""];
  for (const section of brief.sections ?? []) {
    if (section.id === "header" || section.id === "export_metadata") {
      continue;
    }
    lines.push(`## ${sectionTitle(section.id, section.title)}`);
    const items = section.items ?? [];
    if (items.length === 0) {
      lines.push("- Keine Angaben gemeldet.");
    } else {
      for (const item of items) {
        lines.push(`- ${valueToText(item)}`);
      }
    }
    lines.push("");
  }
  return lines.join("\n").trim();
}

function copyTextToClipboard(text: string): Promise<void> | undefined {
  return globalThis.navigator?.clipboard?.writeText(text);
}

function applyRwdrCaseState(state: RwdrCaseState, setters: {
  setCaseId: (value: string | null) => void;
  setRawInquiry: (value: string) => void;
  setCandidates: (value: RwdrCandidateField[]) => void;
  setBrief: (value: TechnicalRwdrBrief | null) => void;
  setExportMarkdown: (value: string) => void;
}) {
  setters.setCaseId(state.case_id || null);
  setters.setRawInquiry(state.raw_inquiry_text || "");
  setters.setCandidates(state.evidence_fields ?? state.candidate_fields ?? []);
  setters.setBrief(state.technical_rwdr_rfq_brief ?? null);
  setters.setExportMarkdown(state.export_markdown || "");
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

function friendlyRfqError(message: string) {
  if (
    message.includes("rfq_preview_case_not_found") ||
    message.includes("rfq_preview_create_failed:404") ||
    message.includes("case not found") ||
    message.includes("404")
  ) {
    return "Die Anfragevorschau kann erst erstellt werden, wenn der Fall gespeichert ist. Bitte übernimm zuerst die vorgeschlagenen Angaben.";
  }
  return message;
}

function readExpectedCaseRevision(workspace: WorkspaceView | null | undefined): number | null {
  const revision = workspace?.summary?.stateRevision;
  return typeof revision === "number" && Number.isFinite(revision) ? revision : null;
}

function readDataReadinessProjection(data: unknown): WorkspaceRfqReadinessProjection | null {
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return null;
  }
  const projection = (data as { rfqReadinessProjection?: WorkspaceRfqReadinessProjection | null }).rfqReadinessProjection;
  return projection ?? null;
}

function previewActionIsAvailable(readiness: WorkspaceRfqReadinessProjection | null): boolean {
  if (!readiness) {
    return true;
  }
  return Boolean(readiness.preview_action_available && readiness.preview_possible);
}

export default function RfqPane({ data, caseId, workspace }: RfqPaneProps) {
  const streamReadiness = useWorkspaceStore((state) => state.streamWorkspace?.rfqReadinessProjection ?? null);
  const [preview, setPreview] = useState<RfqPreviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isGrantingConsent, setIsGrantingConsent] = useState(false);
  const [rwdrRawInquiry, setRwdrRawInquiry] = useState("");
  const [rwdrCaseId, setRwdrCaseId] = useState<string | null>(null);
  const [rwdrCandidates, setRwdrCandidates] = useState<RwdrCandidateField[]>([]);
  const [rwdrBrief, setRwdrBrief] = useState<TechnicalRwdrBrief | null>(null);
  const [rwdrExportMarkdown, setRwdrExportMarkdown] = useState("");
  const [rwdrSnapshots, setRwdrSnapshots] = useState<RwdrSnapshotSummary[]>([]);
  const [rwdrRestored, setRwdrRestored] = useState(false);
  const [rwdrDiffFromRevision, setRwdrDiffFromRevision] = useState<number | null>(null);
  const [rwdrDiffToRevision, setRwdrDiffToRevision] = useState<number | null>(null);
  const [rwdrRevisionDiff, setRwdrRevisionDiff] = useState<RwdrRevisionDiff | null>(null);
  const [isRwdrDiffLoading, setIsRwdrDiffLoading] = useState(false);
  const [rwdrEditField, setRwdrEditField] = useState<string | null>(null);
  const [rwdrEditValue, setRwdrEditValue] = useState("");
  const [isRwdrAnalyzing, setIsRwdrAnalyzing] = useState(false);
  const [isRwdrBriefCreating, setIsRwdrBriefCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [consent, setConsent] = useState<ConsentState>({
    noFinalRelease: false,
    openPoints: false,
    exportSharing: false,
  });
  const readinessProjection =
    workspace?.rfqReadinessProjection ?? readDataReadinessProjection(data) ?? streamReadiness;
  const expectedCaseRevision = readExpectedCaseRevision(workspace);
  const canCreatePreview = previewActionIsAvailable(readinessProjection);
  const exportHref =
    caseId && preview ? buildRfqPreviewExportReadPath(caseId, preview.preview_id) : null;

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
        throw new Error(getErrorMessage(body, "Anfragevorschau konnte nicht geladen werden."));
      }
      setPreview(body as RfqPreviewResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Anfragevorschau konnte nicht geladen werden.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadPreview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  useEffect(() => {
    if (!caseId) {
      return;
    }
    trackProductEvent("case_summary_viewed", {
      case_present: true,
      source: "rfq_pane",
    });
  }, [caseId]);

  const persistRwdrCaseReference = (nextCaseId: string | null) => {
    if (!nextCaseId || typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem("sealai_rwdr_case_id", nextCaseId);
    const url = new URL(window.location.href);
    url.searchParams.set("rwdr_case_id", nextCaseId);
    window.history.replaceState({}, "", url.toString());
  };

  const loadRwdrSnapshots = async (nextCaseId: string) => {
    const response = await fetch(buildRwdrCaseSnapshotsReadPath(nextCaseId), { cache: "no-store" });
    const body = await response.json().catch(() => null);
    if (response.ok && Array.isArray(body?.snapshots)) {
      const snapshots = body.snapshots as RwdrSnapshotSummary[];
      setRwdrSnapshots(snapshots);
      const revisions = snapshots
        .map((snapshot) => snapshot.revision_number)
        .filter((revision): revision is number => typeof revision === "number");
      if (revisions.length >= 2) {
        setRwdrDiffFromRevision((current) => current ?? revisions[0]);
        setRwdrDiffToRevision((current) => current ?? revisions[revisions.length - 1]);
      }
    }
  };

  const loadRwdrCase = async (nextCaseId: string, restored = false) => {
    setError(null);
    try {
      const response = await fetch(buildRwdrCaseReadPath(nextCaseId), { cache: "no-store" });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(getErrorMessage(body, "RWDR Case konnte nicht wiederhergestellt werden."));
      }
      applyRwdrCaseState(body as RwdrCaseState, {
        setCaseId: setRwdrCaseId,
        setRawInquiry: setRwdrRawInquiry,
        setCandidates: setRwdrCandidates,
        setBrief: setRwdrBrief,
        setExportMarkdown: setRwdrExportMarkdown,
      });
      const restoredCaseId = (body as RwdrCaseState).case_id || nextCaseId;
      persistRwdrCaseReference(restoredCaseId);
      setRwdrRestored(restored);
      await loadRwdrSnapshots(restoredCaseId);
    } catch (err) {
      setRwdrRestored(false);
      setError(err instanceof Error ? err.message : "RWDR Case konnte nicht wiederhergestellt werden.");
    }
  };

  useEffect(() => {
    if (rwdrCaseId || typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get("rwdr_case_id");
    const fromStorage = window.localStorage.getItem("sealai_rwdr_case_id");
    const nextCaseId = fromUrl || fromStorage;
    if (nextCaseId) {
      void loadRwdrCase(nextCaseId, true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sections = useMemo(
    () => preview?.payload?.rfq_preview?.sections ?? EMPTY_SECTIONS,
    [preview?.payload?.rfq_preview?.sections],
  );
  const fieldStatuses =
    preview?.payload?.rfq_preview?.technical_field_statuses ?? EMPTY_FIELD_STATUSES;
  const fieldGroups =
    preview?.payload?.rfq_preview?.technical_field_groups ?? EMPTY_FIELD_GROUPS;
  const technicalRwdrBrief =
    rwdrBrief ??
    preview?.payload?.rfq_preview?.technical_rwdr_rfq_brief ??
    preview?.payload?.technical_rwdr_rfq_brief ??
    null;
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
    () =>
      uniqueTexts([
        ...sectionItems(sections, /Fragen an den Hersteller/i),
        ...(preview?.payload?.decision_understanding?.manufacturer_review_needs ?? []),
        ...(workspace?.manufacturerQuestions?.mandatory ?? []),
        ...(workspace?.manufacturerQuestions?.openQuestions ?? []).map((item) =>
          item.reason ? `${item.question} — ${item.reason}` : item.question,
        ),
        ...(workspace?.rfq?.package?.manufacturerQuestionsMandatory ?? []),
        ...(workspace?.matching?.openManufacturerQuestions ?? []),
      ]),
    [
      preview?.payload?.decision_understanding?.manufacturer_review_needs,
      sections,
      workspace?.manufacturerQuestions?.mandatory,
      workspace?.manufacturerQuestions?.openQuestions,
      workspace?.matching?.openManufacturerQuestions,
      workspace?.rfq?.package?.manufacturerQuestionsMandatory,
    ],
  );
  const consentReady =
    consent.noFinalRelease &&
    consent.openPoints &&
    consent.exportSharing &&
    Boolean(preview) &&
    !preview?.stale;

  const analyzeRwdrInquiry = async () => {
    if (!rwdrRawInquiry.trim()) {
      return;
    }
    setIsRwdrAnalyzing(true);
    setError(null);
    try {
      const response = await fetch(buildRwdrAnalyzeReadPath(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_inquiry: rwdrRawInquiry }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(getErrorMessage(body, "RWDR-Anfrage konnte nicht strukturiert werden."));
      }
      applyRwdrCaseState(body as RwdrCaseState, {
        setCaseId: setRwdrCaseId,
        setRawInquiry: setRwdrRawInquiry,
        setCandidates: setRwdrCandidates,
        setBrief: setRwdrBrief,
        setExportMarkdown: setRwdrExportMarkdown,
      });
      const nextCaseId = (body as RwdrCaseState).case_id || null;
      persistRwdrCaseReference(nextCaseId);
      if (nextCaseId) {
        await loadRwdrSnapshots(nextCaseId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "RWDR-Anfrage konnte nicht strukturiert werden.");
    } finally {
      setIsRwdrAnalyzing(false);
    }
  };

  const generateRwdrBrief = async () => {
    if (!rwdrCaseId) {
      return;
    }
    setIsRwdrBriefCreating(true);
    setError(null);
    try {
      const response = await fetch(buildRwdrCaseBriefReadPath(rwdrCaseId), { method: "POST" });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(getErrorMessage(body, "Technical RWDR RFQ Brief konnte nicht erstellt werden."));
      }
      setRwdrBrief(body as TechnicalRwdrBrief);
      const exportResponse = await fetch(buildRwdrCaseExportReadPath(rwdrCaseId), { cache: "no-store" });
      const exportBody = await exportResponse.json().catch(() => null);
      if (exportResponse.ok && exportBody?.content) {
        setRwdrExportMarkdown(String(exportBody.content));
      }
      await loadRwdrSnapshots(rwdrCaseId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Technical RWDR RFQ Brief konnte nicht erstellt werden.");
    } finally {
      setIsRwdrBriefCreating(false);
    }
  };

  const applyRwdrDecision = async (decision: Record<string, unknown>) => {
    if (!rwdrCaseId) {
      return;
    }
    setError(null);
    try {
      const response = await fetch(buildRwdrConfirmationsReadPath(rwdrCaseId), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decisions: [decision] }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(getErrorMessage(body, "RWDR-Bestätigung konnte nicht gespeichert werden."));
      }
      applyRwdrCaseState(body as RwdrCaseState, {
        setCaseId: setRwdrCaseId,
        setRawInquiry: setRwdrRawInquiry,
        setCandidates: setRwdrCandidates,
        setBrief: setRwdrBrief,
        setExportMarkdown: setRwdrExportMarkdown,
      });
      await loadRwdrSnapshots(rwdrCaseId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "RWDR-Bestätigung konnte nicht gespeichert werden.");
    }
  };

  const compareRwdrRevisions = async () => {
    if (!rwdrCaseId || rwdrDiffFromRevision === null || rwdrDiffToRevision === null) {
      return;
    }
    setIsRwdrDiffLoading(true);
    setError(null);
    try {
      const response = await fetch(
        buildRwdrCaseDiffReadPath(rwdrCaseId, rwdrDiffFromRevision, rwdrDiffToRevision),
        { cache: "no-store" },
      );
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(getErrorMessage(body, "Versionsvergleich konnte nicht geladen werden."));
      }
      setRwdrRevisionDiff(body as RwdrRevisionDiff);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Versionsvergleich konnte nicht geladen werden.");
    } finally {
      setIsRwdrDiffLoading(false);
    }
  };

  const createPreview = async () => {
    if (!caseId) {
      return;
    }
    setIsCreating(true);
    setError(null);
    try {
      const createInit: RequestInit = { method: "POST" };
      if (expectedCaseRevision !== null) {
        createInit.headers = { "Content-Type": "application/json" };
        createInit.body = JSON.stringify({ expected_case_revision: expectedCaseRevision });
      }
      const response = await fetch(buildRfqPreviewReadPath(caseId), createInit);
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(getErrorMessage(body, "Anfragevorschau konnte nicht vorbereitet werden."));
      }
      const nextPreview = body as RfqPreviewResponse;
      setPreview(nextPreview);
      trackSeoEvent("rfq_preview_generated", {
        case_revision: nextPreview.case_revision,
        dispatch_enabled: nextPreview.dispatch_enabled,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Anfragevorschau konnte nicht vorbereitet werden.";
      setError(friendlyRfqError(message));
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
          shared_sections: sharedSections.length > 0 ? sharedSections : ["Anfragevorschau"],
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
      trackProductEvent("handover_clicked", {
        case_present: true,
        consent_status: "granted",
        source: "rfq_manual_export_consent",
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nutzerbestätigung konnte nicht gespeichert werden.");
    } finally {
      setIsGrantingConsent(false);
    }
  };

  if (!data && !workspace && !caseId) {
    return (
      <div className="grid gap-4" data-private>
        {!preview ? (
          <RwdrConfirmationFlow
            rawInquiry={rwdrRawInquiry}
            candidates={rwdrCandidates}
            brief={technicalRwdrBrief}
            editField={rwdrEditField}
            editValue={rwdrEditValue}
            isAnalyzing={isRwdrAnalyzing}
            isBriefCreating={isRwdrBriefCreating}
            caseId={rwdrCaseId}
            exportMarkdown={rwdrExportMarkdown}
            restored={rwdrRestored}
            snapshots={rwdrSnapshots}
            diffFromRevision={rwdrDiffFromRevision}
            diffToRevision={rwdrDiffToRevision}
            revisionDiff={rwdrRevisionDiff}
            isDiffLoading={isRwdrDiffLoading}
            onDiffFromRevisionChange={setRwdrDiffFromRevision}
            onDiffToRevisionChange={setRwdrDiffToRevision}
            onCompareRevisions={() => void compareRwdrRevisions()}
            onRawInquiryChange={setRwdrRawInquiry}
            onAnalyze={() => void analyzeRwdrInquiry()}
            onGenerateBrief={() => void generateRwdrBrief()}
            onConfirm={(field) => void applyRwdrDecision({
              field: field.field,
              action: "confirm",
              source_span: field.source_span || undefined,
              unit: field.unit || undefined,
            })}
            onReject={(field) => void applyRwdrDecision({
              field: field.field,
              action: "reject",
            })}
            onUnknown={(field) => void applyRwdrDecision({
              field: field.field,
              action: "explicitly_unknown",
            })}
            onStartEdit={(field) => {
              setRwdrEditField(field.field);
              setRwdrEditValue(valueToText(field.value) === "Noch offen" ? "" : valueToText(field.value));
            }}
            onEditValueChange={setRwdrEditValue}
            onSaveEdit={(field) => {
              void applyRwdrDecision({
                field: field.field,
                action: "edit",
                value: rwdrEditValue,
                unit: field.unit || undefined,
              });
              setRwdrEditField(null);
              setRwdrEditValue("");
            }}
          />
        ) : null}
        {error ? (
          <div className="rounded-[12px] border border-[#FDECEC] bg-[#FDECEC] px-3 py-2 text-sm text-[#991B1B]">
            {error}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="grid gap-4" data-private>
      <section className="rounded-[18px] border border-[#E5E7EB] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-[#F0F2F5] pb-3">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[#6B7280]">
              Anfragevorschau
            </div>
            <h2 className="mt-1 text-base font-semibold tracking-tight text-[#111827]">Anfragevorschau</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {preview && (
              <>
                <StatusBadge label={preview.stale ? "veraltet" : "aktuell"} variant={preview.stale ? "warning" : "success"} />
                <StatusBadge label={`Stand ${preview.case_revision}`} variant="info" />
                <StatusBadge label={`jetzt ${preview.current_case_revision}`} variant="default" />
              </>
            )}
            <button
              type="button"
              onClick={() => void loadPreview()}
              disabled={isLoading}
              className="flex h-9 w-9 items-center justify-center rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] text-[#4B5563] transition-colors hover:bg-[#F0F2F5]"
              aria-label="Anfragevorschau neu laden"
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

        <RfqReadinessPanel
          readiness={readinessProjection}
          expectedCaseRevision={expectedCaseRevision}
        />

        {!preview ? (
          <RwdrConfirmationFlow
            rawInquiry={rwdrRawInquiry}
            candidates={rwdrCandidates}
            brief={technicalRwdrBrief}
            editField={rwdrEditField}
            editValue={rwdrEditValue}
            isAnalyzing={isRwdrAnalyzing}
            isBriefCreating={isRwdrBriefCreating}
            caseId={rwdrCaseId}
            exportMarkdown={rwdrExportMarkdown}
            restored={rwdrRestored}
            snapshots={rwdrSnapshots}
            diffFromRevision={rwdrDiffFromRevision}
            diffToRevision={rwdrDiffToRevision}
            revisionDiff={rwdrRevisionDiff}
            isDiffLoading={isRwdrDiffLoading}
            onDiffFromRevisionChange={setRwdrDiffFromRevision}
            onDiffToRevisionChange={setRwdrDiffToRevision}
            onCompareRevisions={() => void compareRwdrRevisions()}
            onRawInquiryChange={setRwdrRawInquiry}
            onAnalyze={() => void analyzeRwdrInquiry()}
            onGenerateBrief={() => void generateRwdrBrief()}
            onConfirm={(field) => void applyRwdrDecision({
              field: field.field,
              action: "confirm",
              source_span: field.source_span || undefined,
              unit: field.unit || undefined,
            })}
            onReject={(field) => void applyRwdrDecision({
              field: field.field,
              action: "reject",
            })}
            onUnknown={(field) => void applyRwdrDecision({
              field: field.field,
              action: "explicitly_unknown",
            })}
            onStartEdit={(field) => {
              setRwdrEditField(field.field);
              setRwdrEditValue(valueToText(field.value) === "Noch offen" ? "" : valueToText(field.value));
            }}
            onEditValueChange={setRwdrEditValue}
            onSaveEdit={(field) => {
              void applyRwdrDecision({
                field: field.field,
                action: "edit",
                value: rwdrEditValue,
                unit: field.unit || undefined,
              });
              setRwdrEditField(null);
              setRwdrEditValue("");
            }}
          />
        ) : null}

        {manufacturerReviewNeeds.length > 0 ? (
          <div className="mb-4">
            <ListPanel
              title="Automatisch vorbereitete Herstellerfragen"
              items={manufacturerReviewNeeds}
              empty="Noch keine Herstellerfragen aus dem Challenger vorbereitet."
              tone="neutral"
            />
          </div>
        ) : null}

        {!preview ? (
          <div className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-4">
            <div className="flex items-start gap-3">
              <FileText className="mt-0.5 shrink-0 text-seal-blue" size={18} />
              <div className="min-w-0">
                <div className="text-sm font-semibold text-[#111827]">Für diesen Fall gibt es noch keine Anfragevorschau.</div>
                <p className="mt-1 text-sm text-[#4B5563]">
                  SeaLAI erstellt die Vorschau aus dem gespeicherten Fallstand. Demo- oder lokale Platzhalter werden hier nicht als Wahrheit verwendet.
                </p>
                {readinessProjection && !canCreatePreview ? (
                  <p className="mt-2 text-sm font-medium text-[#9A3412]">
                    Die Vorschau-Aktion ist aktuell noch nicht verfügbar. Kläre zuerst die offenen Punkte oder Blocker.
                  </p>
                ) : null}
                <button
                  type="button"
                  onClick={() => void createPreview()}
                  disabled={isCreating || !canCreatePreview}
                  className="mt-3 rounded-[14px] bg-seal-blue px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-seal-blue disabled:cursor-not-allowed disabled:bg-[#D1D5DB]"
                >
                  {isCreating ? "Anfragevorschau wird vorbereitet..." : "Anfragevorschau vorbereiten"}
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {preview.stale && (
              <div className="flex items-start gap-2 rounded-[12px] border border-[#FFF4E5] bg-[#FFF4E5] px-3 py-2 text-sm text-[#9A3412]">
                <ShieldAlert size={16} className="mt-0.5 shrink-0" />
                Diese Anfragevorschau ist veraltet: Sie basiert auf Stand {preview.case_revision}, der Fall ist inzwischen bei Stand {preview.current_case_revision}. Bitte erst neu vorbereiten.
              </div>
            )}

            <div className="grid gap-3 sm:grid-cols-3">
              <MetaTile label="Vorschau-ID" value={preview.preview_id} />
              <MetaTile label="Bestätigung" value={preview.consent_status} />
              <MetaTile label="Weitergabe" value={preview.dispatch_enabled ? "aktiv" : "nicht vorgesehen"} />
            </div>

            {technicalRwdrBrief ? (
              <TechnicalRwdrBriefPanel brief={technicalRwdrBrief} exportMarkdown={rwdrExportMarkdown} caseId={rwdrCaseId} />
            ) : null}

            <ListPanel title="Offene Punkte" items={openPoints} empty="Keine offenen Punkte in der Vorschau gemeldet." tone="warning" />
            <ListPanel title="Risiken" items={risks} empty="Keine separaten Risiken in der Vorschau gemeldet." tone="warning" />
            <ListPanel title="Was der Hersteller prüfen muss" items={manufacturerReviewNeeds} empty="Keine separaten Prüffragen gemeldet." tone="neutral" />

            <section className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
              <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
                <Info size={14} />
                Feldstatus und Belege
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
                  Für diese Vorschau wurden noch keine Feldstatus-Details geliefert.
                </div>
              )}
            </section>

            <section className="rounded-[14px] border border-[#E5E7EB] bg-white p-3">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
                    Nutzerbestätigung erforderlich
                  </div>
                  <div className="mt-1 text-sm font-semibold text-[#111827]">Bestätigung für manuellen Export</div>
                </div>
                {preview.consent_status === "granted" && (
                  <StatusBadge label="Anfragevorschau exportbereit" variant="success" />
                )}
              </div>
              <div className="space-y-2">
                <ConsentCheckbox
                  checked={consent.noFinalRelease}
                  onChange={(checked) => setConsent((current) => ({ ...current, noFinalRelease: checked }))}
                  label="Ich verstehe, dass diese Anfragevorschau keine Auslegungsfreigabe ist."
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
                className="mt-3 flex items-center gap-2 rounded-[14px] bg-seal-blue px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-seal-blue disabled:cursor-not-allowed disabled:bg-[#D1D5DB]"
              >
                <CheckCircle2 size={16} />
                {isGrantingConsent ? "Nutzerbestätigung wird gespeichert..." : "Nutzerbestätigung speichern"}
              </button>
              {preview.consent_status === "granted" && exportHref ? (
                <div className="mt-3 rounded-[12px] border border-[#DCEBE3] bg-[#F4FBF7] px-3 py-3">
                  <div className="text-sm font-semibold text-[#14532D]">
                    Fertige Anfrage als PDF bereit
                  </div>
                  <p className="mt-1 text-sm text-[#315B43]">
                    Die Anfragebasis ist eingefroren und kann kontrolliert als PDF an Hersteller weitergegeben werden.
                  </p>
                  <a
                    href={exportHref}
                    className="mt-3 inline-flex items-center gap-2 rounded-[14px] bg-seal-blue px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-seal-blue"
                  >
                    <Download size={16} />
                    Anfrage als PDF herunterladen
                  </a>
                </div>
              ) : null}
            </section>
          </div>
        )}
      </section>
    </div>
  );
}

function RwdrConfirmationFlow({
  rawInquiry,
  candidates,
  brief,
  editField,
  editValue,
  isAnalyzing,
  isBriefCreating,
  caseId,
  exportMarkdown,
  restored,
  snapshots,
  diffFromRevision,
  diffToRevision,
  revisionDiff,
  isDiffLoading,
  onRawInquiryChange,
  onAnalyze,
  onGenerateBrief,
  onDiffFromRevisionChange,
  onDiffToRevisionChange,
  onCompareRevisions,
  onConfirm,
  onReject,
  onUnknown,
  onStartEdit,
  onEditValueChange,
  onSaveEdit,
}: {
  rawInquiry: string;
  candidates: RwdrCandidateField[];
  brief: TechnicalRwdrBrief | null;
  editField: string | null;
  editValue: string;
  isAnalyzing: boolean;
  isBriefCreating: boolean;
  caseId: string | null;
  exportMarkdown: string;
  restored: boolean;
  snapshots: RwdrSnapshotSummary[];
  diffFromRevision: number | null;
  diffToRevision: number | null;
  revisionDiff: RwdrRevisionDiff | null;
  isDiffLoading: boolean;
  onRawInquiryChange: (value: string) => void;
  onAnalyze: () => void;
  onGenerateBrief: () => void;
  onDiffFromRevisionChange: (value: number | null) => void;
  onDiffToRevisionChange: (value: number | null) => void;
  onCompareRevisions: () => void;
  onConfirm: (field: RwdrCandidateField) => void;
  onReject: (field: RwdrCandidateField) => void;
  onUnknown: (field: RwdrCandidateField) => void;
  onStartEdit: (field: RwdrCandidateField) => void;
  onEditValueChange: (value: string) => void;
  onSaveEdit: (field: RwdrCandidateField) => void;
}) {
  const liabilityCandidates = candidates.filter((field) =>
    field.liability_bearing !== false && RWDR_LIABILITY_FIELDS.has(field.field),
  );
  const unresolvedCritical = (brief?.sections ?? [])
    .find((section) => section.id === "missing_critical_fields")
    ?.items?.map(valueToText) ?? [];
  const unresolvedCandidates = liabilityCandidates.filter((field) =>
    !["confirmed", "edited_by_user", "explicitly_unknown", "rejected"].includes(field.confirmation_status || ""),
  );
  const canGenerate = Boolean(caseId) && candidates.length > 0 && unresolvedCandidates.length === 0;

  return (
    <section className="rounded-[18px] border border-[#D7E4F5] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3 border-b border-[#F0F2F5] pb-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-seal-blue">
            Technical RWDR RFQ Brief
          </div>
          <h2 className="mt-1 text-base font-semibold tracking-tight text-[#111827]">
            RWDR-Angaben bestätigen
          </h2>
        </div>
        <StatusBadge label="kein Hersteller-Routing" variant="info" />
      </div>
      {caseId ? (
        <div className="mb-3 rounded-[10px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-2 text-xs text-[#4B5563]">
          RWDR Case: {caseId.slice(0, 8)}
          {restored ? " · aus Backend wiederhergestellt" : ""}
        </div>
      ) : null}
      {snapshots.length > 0 ? (
        <div className="mb-3 rounded-[12px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-2">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
            Versionsverlauf
          </div>
          <div className="mt-2 grid gap-1 text-xs text-[#4B5563]">
            {snapshots.slice(-5).map((snapshot) => (
              <div key={`${snapshot.revision_number}-${snapshot.event_type}`}>
                Rev. {snapshot.revision_number}: {snapshot.event_type || "rwdr_snapshot"}
              </div>
            ))}
          </div>
          {snapshots.length >= 2 ? (
            <div className="mt-3 border-t border-[#E5E7EB] pt-3">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
                Versionsvergleich
              </div>
              <div className="flex flex-wrap items-end gap-2">
                <label className="grid gap-1 text-xs font-medium text-[#4B5563]">
                  Von Revision
                  <select
                    value={diffFromRevision ?? ""}
                    onChange={(event) => onDiffFromRevisionChange(Number.parseInt(event.target.value, 10))}
                    className="rounded-[10px] border border-[#D1D5DB] bg-white px-2 py-1 text-xs text-[#111827]"
                  >
                    {snapshots.map((snapshot) => (
                      <option key={`from-${snapshot.revision_number}`} value={snapshot.revision_number}>
                        Rev. {snapshot.revision_number}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="grid gap-1 text-xs font-medium text-[#4B5563]">
                  Bis Revision
                  <select
                    value={diffToRevision ?? ""}
                    onChange={(event) => onDiffToRevisionChange(Number.parseInt(event.target.value, 10))}
                    className="rounded-[10px] border border-[#D1D5DB] bg-white px-2 py-1 text-xs text-[#111827]"
                  >
                    {snapshots.map((snapshot) => (
                      <option key={`to-${snapshot.revision_number}`} value={snapshot.revision_number}>
                        Rev. {snapshot.revision_number}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  onClick={onCompareRevisions}
                  disabled={isDiffLoading || diffFromRevision === null || diffToRevision === null}
                  className="rounded-[12px] border border-[#D1D5DB] bg-white px-3 py-1.5 text-xs font-semibold text-[#111827] transition-colors hover:bg-[#F3F4F6] disabled:cursor-not-allowed disabled:text-[#9CA3AF]"
                >
                  {isDiffLoading ? "Vergleich wird geladen..." : "Revisionen vergleichen"}
                </button>
              </div>
              <p className="mt-2 text-xs text-[#6B7280]">
                Nur Lesen: Der Vergleich ändert keine RWDR-Daten und keine Snapshots.
              </p>
            </div>
          ) : null}
        </div>
      ) : null}
      {revisionDiff ? <RwdrRevisionDiffPanel diff={revisionDiff} /> : null}

      <label className="grid gap-2 text-sm font-medium text-[#111827]">
        RWDR-Anfrage einfügen
        <textarea
          value={rawInquiry}
          onChange={(event) => onRawInquiryChange(event.target.value)}
          rows={4}
          className="min-h-[104px] rounded-[12px] border border-[#D1D5DB] bg-[#FAFAFB] px-3 py-2 text-sm font-normal text-[#111827] outline-none focus:border-seal-blue"
          placeholder="Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min, staubige Umgebung."
        />
      </label>
      <button
        type="button"
        onClick={onAnalyze}
        disabled={isAnalyzing || !rawInquiry.trim()}
        className="mt-3 rounded-[14px] bg-seal-blue px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-seal-blue disabled:cursor-not-allowed disabled:bg-[#D1D5DB]"
      >
        {isAnalyzing ? "Angaben werden strukturiert..." : "Angaben strukturieren"}
      </button>

      {liabilityCandidates.length > 0 ? (
        <div className="mt-4 grid gap-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
            Haftungstragende Felder
          </div>
          {liabilityCandidates.map((field) => (
            <RwdrConfirmationCard
              key={field.field}
              field={field}
              isEditing={editField === field.field}
              editValue={editValue}
              onConfirm={onConfirm}
              onReject={onReject}
              onUnknown={onUnknown}
              onStartEdit={onStartEdit}
              onEditValueChange={onEditValueChange}
              onSaveEdit={onSaveEdit}
            />
          ))}
        </div>
      ) : (
        <div className="mt-4 rounded-[12px] border border-dashed border-[#D1D5DB] bg-[#FAFAFB] px-3 py-3 text-sm text-[#6B7280]">
          Noch keine extrahierten RWDR-Felder vorhanden.
        </div>
      )}

      {unresolvedCritical.length > 0 ? (
        <div className="mt-4">
          <MissingCriticalPanel brief={brief} />
        </div>
      ) : null}

      <button
        type="button"
        onClick={onGenerateBrief}
        disabled={!canGenerate || isBriefCreating}
        className="mt-4 rounded-[14px] bg-[#111827] px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#111827] disabled:cursor-not-allowed disabled:bg-[#D1D5DB]"
      >
        {isBriefCreating ? "Technical RWDR RFQ Brief wird erstellt..." : "Technical RWDR RFQ Brief erstellen"}
      </button>
      {!canGenerate && candidates.length > 0 ? (
        <p className="mt-2 text-sm text-[#9A3412]">
          Bitte alle haftungstragenden Felder bestätigen, bearbeiten, als unbekannt markieren oder verwerfen.
        </p>
      ) : null}

      {brief ? (
        <div className="mt-4">
          <TechnicalRwdrBriefPanel brief={brief} exportMarkdown={exportMarkdown} caseId={caseId} />
        </div>
      ) : null}
    </section>
  );
}

function RwdrConfirmationCard({
  field,
  isEditing,
  editValue,
  onConfirm,
  onReject,
  onUnknown,
  onStartEdit,
  onEditValueChange,
  onSaveEdit,
}: {
  field: RwdrCandidateField;
  isEditing: boolean;
  editValue: string;
  onConfirm: (field: RwdrCandidateField) => void;
  onReject: (field: RwdrCandidateField) => void;
  onUnknown: (field: RwdrCandidateField) => void;
  onStartEdit: (field: RwdrCandidateField) => void;
  onEditValueChange: (value: string) => void;
  onSaveEdit: (field: RwdrCandidateField) => void;
}) {
  const hasSourceSpan = Boolean(field.source_span?.trim());
  const status = field.confirmation_status || "unconfirmed";
  const confirmDisabled = field.origin === "llm_extracted" && !hasSourceSpan;
  return (
    <article className="rounded-[12px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-[#111827]">{fieldLabel(field.field)}</div>
          <div className="mt-1 text-xs text-[#6B7280]">
            Origin: {field.origin || "llm_extracted"} · Status: {status}
          </div>
        </div>
        <StatusBadge label="prüfpflichtig" variant="warning" />
      </div>

      <div className="mt-3 grid gap-2 text-sm">
        <div className="rounded-[10px] border border-[#E5E7EB] bg-white px-3 py-2">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">Gefundener Wert</div>
          <div className="mt-1 text-[#111827]">
            {valueToText(field.value)}
            {field.unit ? ` ${field.unit}` : ""}
          </div>
        </div>
        <div className="rounded-[10px] border border-[#E5E7EB] bg-white px-3 py-2">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">Quelle</div>
          <div className="mt-1 text-[#111827]">{hasSourceSpan ? `"${field.source_span}"` : "Keine exakte Quellenstelle verfügbar. Dieser Wert muss manuell bestätigt oder bearbeitet werden."}</div>
        </div>
      </div>

      {isEditing ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <input
            aria-label={`${fieldLabel(field.field)} bearbeiten`}
            value={editValue}
            onChange={(event) => onEditValueChange(event.target.value)}
            className="min-w-[180px] flex-1 rounded-[10px] border border-[#D1D5DB] px-3 py-2 text-sm outline-none focus:border-seal-blue"
          />
          <button type="button" onClick={() => onSaveEdit(field)} className="rounded-[12px] bg-seal-blue px-3 py-2 text-sm font-semibold text-white">
            Bearbeitung übernehmen
          </button>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onConfirm(field)}
            disabled={confirmDisabled}
            className="rounded-[12px] border border-[#BDECCB] bg-[#EAF7EE] px-3 py-2 text-sm font-semibold text-[#166534] disabled:cursor-not-allowed disabled:border-[#E5E7EB] disabled:bg-[#F3F4F6] disabled:text-[#6B7280]"
          >
            Bestätigen
          </button>
          <button type="button" onClick={() => onStartEdit(field)} className="rounded-[12px] border border-[#D7E4F5] bg-white px-3 py-2 text-sm font-semibold text-seal-blue">
            Bearbeiten
          </button>
          <button type="button" onClick={() => onUnknown(field)} className="rounded-[12px] border border-[#FDE2B8] bg-[#FFF4E5] px-3 py-2 text-sm font-semibold text-[#9A3412]">
            Nicht angegeben / unbekannt
          </button>
          <button type="button" onClick={() => onReject(field)} className="rounded-[12px] border border-[#FDECEC] bg-white px-3 py-2 text-sm font-semibold text-[#991B1B]">
            Verwerfen
          </button>
        </div>
      )}
    </article>
  );
}

function RwdrRevisionDiffPanel({ diff }: { diff: RwdrRevisionDiff }) {
  const evidenceDiffs = diff.evidence_field_diffs ?? [];
  const critical = diff.missing_critical_fields_diff ?? {};
  const computed = diff.computed_values_diff ?? {};
  const reviewFlags = diff.review_flags_diff ?? {};
  const questions = diff.manufacturer_questions_diff ?? {};
  const exportDiff = diff.export_diff ?? {};
  return (
    <section className="mb-3 rounded-[12px] border border-[#D7E4F5] bg-white px-3 py-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-seal-blue">
            Versionsvergleich
          </div>
          <div className="mt-1 text-sm font-semibold text-[#111827]">
            Rev. {diff.from_revision} → Rev. {diff.to_revision}
          </div>
        </div>
        <StatusBadge label="Nur Lesen" variant="info" />
      </div>

      {diff.status_diff && (diff.status_diff.from || diff.status_diff.to) ? (
        <div className="mt-3 rounded-[10px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-2 text-sm text-[#111827]">
          Status: {valueToText(diff.status_diff.from)} → {valueToText(diff.status_diff.to)}
        </div>
      ) : null}

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <DiffListPanel
          title="Geänderte Felder"
          items={evidenceDiffs.map((item) =>
            `${fieldLabel(item.field)}: ${diffChangeLabel(item.change_type)} (${valueToText(item.from?.confirmation_status)} → ${valueToText(item.to?.confirmation_status)})`,
          )}
        />
        <DiffListPanel
          title="Kritisch fehlende Angaben"
          items={[
            ...(critical.added ?? []).map((item) => `Hinzugekommen: ${fieldLabel(item)}`),
            ...(critical.removed ?? []).map((item) => `Entfallen: ${fieldLabel(item)}`),
          ]}
        />
        <DiffListPanel
          title="Berechnete Werte"
          items={[
            ...(computed.added ?? []).map((item) => `Hinzugekommen: ${diffValue(item)}`),
            ...(computed.changed ?? []).map((item) => `Geändert: ${diffValue(item)}`),
            ...(computed.removed ?? []).map((item) => `Entfallen: ${diffValue(item)}`),
          ]}
        />
        <DiffListPanel
          title="Review-Themen"
          items={[
            ...(reviewFlags.added ?? []).map((item) => `Hinzugekommen: ${diffValue(item)}`),
            ...(reviewFlags.removed ?? []).map((item) => `Entfallen: ${diffValue(item)}`),
          ]}
        />
        <DiffListPanel
          title="Herstellerfragen"
          items={[
            ...(questions.added ?? []).map((item) => `Hinzugekommen: ${diffValue(item)}`),
            ...(questions.removed ?? []).map((item) => `Entfallen: ${diffValue(item)}`),
          ]}
        />
        <DiffListPanel
          title="Export-Metadaten"
          items={[
            exportDiff.markdown_export_changed ? "Markdown-Export geändert" : "",
            exportDiff.pdf_export_changed ? "PDF-Export geändert" : "",
            exportDiff.export_metadata_changed ? "Export-Metadaten geändert" : "",
          ].filter(Boolean)}
        />
      </div>
      <p className="mt-3 text-xs text-[#6B7280]">
        Audit-Metadaten wie Zeitstempel werden nicht als deterministische Änderung gezählt.
      </p>
    </section>
  );
}

function DiffListPanel({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-[10px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-2">
      <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">{title}</div>
      {items.length > 0 ? (
        <ul className="mt-2 grid gap-1 text-xs text-[#4B5563]">
          {items.map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : (
        <div className="mt-2 text-xs text-[#6B7280]">Keine Änderung.</div>
      )}
    </div>
  );
}

function diffChangeLabel(changeType: string | undefined): string {
  const labels: Record<string, string> = {
    confirmation_status_changed: "Bestätigungsstatus geändert",
    value_changed: "Wert geändert",
    source_span_changed: "Quellenstelle geändert",
    allowed_in_brief_changed: "Brief-Aufnahmezustand geändert",
    liability_bearing_changed: "Haftungsmarker geändert",
    added: "hinzugekommen",
    removed: "entfallen",
    changed: "geändert",
  };
  return changeType ? labels[changeType] || changeType : "geändert";
}

function MissingCriticalPanel({ brief }: { brief: TechnicalRwdrBrief | null }) {
  const missing = (brief?.sections ?? []).find((section) => section.id === "missing_critical_fields")?.items ?? [];
  const questions = (brief?.sections ?? []).find((section) => section.id === "manufacturer_questions")?.items ?? [];
  const measurements = (brief?.sections ?? []).find((section) => section.id === "recommended_measurement_and_verification_data")?.items ?? [];
  return (
    <section className="rounded-[14px] border border-[#FFF4E5] bg-[#FFF4E5] p-3">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#9A3412]">Kritisch fehlend</div>
      <div className="grid gap-2">
        {missing.map((item) => (
          <div key={valueToText(item)} className="rounded-[12px] border border-[#FDE2B8] bg-white px-3 py-2 text-sm text-[#9A3412]">
            <div className="font-semibold">{fieldLabel(valueToText(item))}</div>
            {questions[0] ? <div className="mt-1">Frage: {valueToText(questions[0])}</div> : null}
            {measurements[0] ? <div className="mt-1">Messhinweis: {valueToText(measurements[0])}</div> : null}
          </div>
        ))}
      </div>
    </section>
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

function RfqReadinessPanel({
  readiness,
  expectedCaseRevision,
}: {
  readiness: WorkspaceRfqReadinessProjection | null;
  expectedCaseRevision: number | null;
}) {
  if (!readiness) {
    return null;
  }

  // §12.6: the backend readiness_band reconciles the three states the §20 band
  // speaks. Fall back to the legacy binary derivation when an older stream omits
  // the band, so historic projections keep rendering.
  const band = readiness.readiness_band ?? null;
  const status =
    band === "rfq_ready"
      ? "Anfrageentwurf prüfbar"
      : band === "rfq_with_open_points"
        ? "RFQ mit offenen Punkten"
        : band === "blocked"
          ? "Blockiert"
          : readiness.rfq_basis_ready || readiness.manufacturer_review_ready
            ? "Anfrageentwurf prüfbar"
            : "Anfragebasis offen";
  const previewStatus =
    readiness.preview_action_available && readiness.preview_possible
      ? "Vorschau verfügbar"
      : "Vorschau noch blockiert";
  const consentStatus = readiness.preview_export_requires_consent || readiness.consent_required
    ? "Zustimmung erforderlich"
    : "Zustimmung nicht gemeldet";

  return (
    <section className="mb-4 rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
            Anfragebasis für Herstellerprüfung
          </div>
          <div className="mt-1 text-sm font-semibold text-[#111827]">{status}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge label={previewStatus} variant={readiness.preview_action_available && readiness.preview_possible ? "success" : "warning"} />
          <StatusBadge label={consentStatus} variant="info" />
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <MetaTile label="Herstellerprüfung" value={readiness.manufacturer_review_ready ? "prüfbar vorbereitet" : "noch offen"} />
        <MetaTile label="Anfrageentwurf" value={readiness.rfq_basis_ready ? "prüfbar vorbereitet" : "noch offen"} />
        <MetaTile label="Fallstand" value={expectedCaseRevision !== null ? expectedCaseRevision : "nicht geliefert"} />
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <ListPanel
          title="Fehlende Angaben"
          items={readiness.known_missing_fields}
          empty="Keine fehlenden Angaben in der Readiness-Projektion gemeldet."
          tone="warning"
        />
        <ListPanel
          title="Offene Punkte"
          items={readiness.open_points}
          empty="Keine offenen Punkte in der Readiness-Projektion gemeldet."
          tone="warning"
        />
        <ListPanel
          title="Blocker"
          items={readiness.blocking_reasons}
          empty="Keine Blocker in der Readiness-Projektion gemeldet."
          tone="neutral"
        />
      </div>

      {readiness.pending_question?.question_text ? (
        <div className="mt-3 rounded-[12px] border border-[#E5E7EB] bg-white px-3 py-2 text-sm text-[#4B5563]">
          Nächste Frage: {readiness.pending_question.question_text}
        </div>
      ) : null}

      <div className="mt-3 rounded-[12px] border border-[#E5E7EB] bg-white px-3 py-2 text-sm text-[#4B5563]">
        Vorschau bedeutet Anfragebasis für die Herstellerprüfung. Das ist keine Weitergabe, kein Herstellerkontakt und keine Auslegungsfreigabe.
      </div>
    </section>
  );
}

function TechnicalRwdrBriefPanel({
  brief,
  exportMarkdown = "",
  caseId = null,
}: {
  brief: TechnicalRwdrBrief;
  exportMarkdown?: string;
  caseId?: string | null;
}) {
  const confirmedFields = brief.confirmed_case_fields ?? [];
  const calculationFields = brief.calculation_fields ?? [];
  const openFields = brief.open_fields ?? [];
  const evaluationOpenPoints = brief.evaluation?.open_points ?? [];
  const outOfScopeReasons = brief.evaluation?.out_of_scope_reasons ?? [];

  return (
    <section className="rounded-[14px] border border-[#D7E4F5] bg-[#F8FBFF] p-3">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-seal-blue">
            Technical RWDR RFQ Brief
          </div>
          <h3 className="mt-1 text-sm font-semibold text-[#111827]">
            Herstellerprüfbasis für Radialwellendichtringe
          </h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge label={rwdrStatusLabel(brief.status)} variant={rwdrStatusVariant(brief.status)} />
          <StatusBadge label="kein Hersteller-Ranking" variant="info" />
          <button
            type="button"
            onClick={() => void copyTextToClipboard(exportMarkdown || briefToMarkdown(brief))}
            className="rounded-[10px] border border-[#D7E4F5] bg-white px-3 py-1.5 text-xs font-semibold text-seal-blue"
          >
            Brief als Text kopieren
          </button>
          {caseId ? (
            <a
              href={buildRwdrCasePdfReadPath(caseId)}
              className="rounded-[10px] border border-[#D7E4F5] bg-white px-3 py-1.5 text-xs font-semibold text-seal-blue"
            >
              Brief als PDF herunterladen
            </a>
          ) : null}
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <MetaTile label="Status" value={brief.status || "NEEDS_CLARIFICATION"} />
        <MetaTile
          label="Technische Grenze"
          value={brief.no_final_technical_release === false ? "nicht gemeldet" : "keine finale Entscheidung"}
        />
        <MetaTile
          label="Hersteller-Routing"
          value={brief.manufacturer_matching_enabled ? "nicht erwartet" : "deaktiviert"}
        />
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <BriefFieldList
          title="Bestätigte Brief-Fakten"
          fields={confirmedFields}
          empty="Noch keine bestätigten Brief-Fakten für den Brief verfügbar."
        />
        <BriefFieldList
          title="Berechnungen"
          fields={calculationFields}
          empty="Noch keine berechneten Werte für den Brief vorhanden."
        />
        <BriefFieldList
          title="Offene Brief-Punkte"
          fields={openFields}
          fallbackItems={[...evaluationOpenPoints, ...outOfScopeReasons]}
          empty="Keine offenen RWDR-MVP-Punkte gemeldet."
          tone="warning"
        />
      </div>

      <div className="mt-3 rounded-[12px] border border-[#D7E4F5] bg-white px-3 py-2 text-sm text-[#4B5563]">
        Dieser Brief ist eine eingefrorene Herstellerprüfbasis. Er enthält keine
        Produktempfehlung, keine Materialfreigabe und keinen automatischen Herstellerkontakt.
      </div>

      {brief.sections?.length ? (
        <div className="mt-3 grid gap-3">
          {brief.sections
            .filter((section) => section.id !== "header" && section.id !== "export_metadata")
            .map((section) => (
              <section key={section.id || section.title} className="rounded-[12px] border border-[#E5E7EB] bg-white p-3">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">
                  {sectionTitle(section.id, section.title)}
                </div>
                {(section.items ?? []).length > 0 ? (
                  <div className="space-y-2">
                    {(section.items ?? []).slice(0, 10).map((item, index) => (
                      <div key={`${section.id}-${index}`} className="rounded-[10px] border border-[#F0F2F5] bg-[#FAFAFB] px-3 py-2 text-sm text-[#4B5563]">
                        {valueToText(item)}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-[10px] border border-dashed border-[#D1D5DB] bg-[#FAFAFB] px-3 py-2 text-sm text-[#6B7280]">
                    Keine Angaben gemeldet.
                  </div>
                )}
              </section>
            ))}
        </div>
      ) : null}
    </section>
  );
}

function BriefFieldList({
  title,
  fields,
  fallbackItems = [],
  empty,
  tone = "neutral",
}: {
  title: string;
  fields: TechnicalRwdrBriefField[];
  fallbackItems?: string[];
  empty: string;
  tone?: "warning" | "neutral";
}) {
  const items =
    fields.length > 0
      ? fields.map((field) =>
          field.blocked_reason
            ? `${briefFieldText(field)} · ${field.blocked_reason}`
            : briefFieldText(field),
        )
      : fallbackItems;

  return <ListPanel title={title} items={items} empty={empty} tone={tone} />;
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
          Wert: {value}
          {unit ? ` ${valueToText(unit)}` : ""}
        </div>
      ) : null}
      <div className="mt-1 text-xs text-[#4B5563]">
        Herkunft: {field.provenance || "nicht geliefert"} · Sicherheit: {field.confidence || "nicht geliefert"}
      </div>
      {field.evidence_refs?.length ? (
        <div className="mt-1 text-xs text-[#4B5563]">Beleg: {field.evidence_refs.join(", ")}</div>
      ) : null}
      {field.confirmation_required ? (
        <div className="mt-1 text-xs font-medium text-[#B45309]">Bestätigung erforderlich</div>
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
