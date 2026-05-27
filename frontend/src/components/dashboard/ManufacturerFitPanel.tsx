"use client";

import { AlertTriangle, Building2, Info, ShieldCheck } from "lucide-react";

import type { WorkspaceManufacturerFitMatrix, WorkspaceManufacturerFitRow, WorkspaceView } from "@/lib/contracts/workspace";
import { cn } from "@/lib/utils";

type BadgeTone = "neutral" | "info" | "warning" | "success";

const FALLBACK_DISCLOSURE =
  "Partner können später sichtbar werden. Bezahlung darf die fachliche Einordnung nicht verbessern. Der Hersteller muss die Auslegung prüfen.";

function readable(value: string | null | undefined) {
  switch (value) {
    case "verified":
      return "geprüft";
    case "documented":
      return "dokumentiert";
    case "self_declared":
      return "Selbstauskunft";
    default:
      return value ? value.replace(/_/g, " ") : "";
  }
}

function badgeClasses(tone: BadgeTone) {
  switch (tone) {
    case "success":
      return "border-[#BDECCB] bg-[#EAF7EE] text-[#166534]";
    case "info":
      return "border-seal-blue/20 bg-seal-blue/10 text-seal-blue";
    case "warning":
      return "border-[#FDE2B8] bg-[#FFF4E5] text-[#9A3412]";
    default:
      return "border-[#E5E7EB] bg-[#F0F2F5] text-[#4B5563]";
  }
}

function Badge({ label, tone = "neutral" }: { label: string; tone?: BadgeTone }) {
  return (
    <span className={cn("inline-flex rounded-full border px-2 py-1 text-[11px] font-bold uppercase tracking-[0.08em]", badgeClasses(tone))}>
      {label}
    </span>
  );
}

function Score({ value }: { value: number | null }) {
  if (value === null) {
    return <span className="text-sm font-semibold text-[#6B7280]">Score offen</span>;
  }
  return (
    <span className="text-sm font-semibold text-[#111827]">
      {Math.round(value)}
      <span className="text-[#6B7280]"> / 100</span>
    </span>
  );
}

function Row({ row }: { row: WorkspaceManufacturerFitRow }) {
  return (
    <article className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-[#111827]">{row.manufacturerId}</div>
          <div className="mt-1 text-[12px] text-[#6B7280]">Abgleich mit bekannten Fähigkeiten</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Score value={row.fitScore} />
          <Badge label={`Belegstatus: ${readable(row.verificationLevel) || "unklar"}`} tone={row.verificationLevel === "verified" ? "success" : "info"} />
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div>
          <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">Abgleichsgrundlage</div>
          {row.fitReasons.length ? (
            <ul className="mt-2 space-y-1 text-sm leading-relaxed text-[#111827]">
              {row.fitReasons.map((reason) => (
                <li key={reason}>{readable(reason)}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-[#6B7280]">Noch keine Gründe gemeldet.</p>
          )}
        </div>
        <div>
          <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">Was fehlt</div>
          {row.gaps.length || row.missingRequirements.length ? (
            <ul className="mt-2 space-y-1 text-sm leading-relaxed text-[#111827]">
              {[...row.gaps, ...row.missingRequirements].map((gap) => (
                <li key={gap}>{readable(gap)}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-[#6B7280]">Keine zusätzlichen offenen Punkte gemeldet.</p>
          )}
        </div>
      </div>
    </article>
  );
}

function hasMatrix(matrix: WorkspaceManufacturerFitMatrix | null | undefined) {
  return Boolean(matrix && (matrix.rows.length > 0 || matrix.status === "no_suitable_partner"));
}

export function ManufacturerFitPanel({ workspace }: { workspace: WorkspaceView | null }) {
  const matrix = workspace?.matching.manufacturerFitMatrix ?? null;

  if (!hasMatrix(matrix)) {
    return (
      <section className="rounded-[18px] border border-[#E5E7EB] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
        <h2 className="flex items-center gap-2 text-base font-semibold text-[#111827]">
          <Building2 size={17} />
          Partner-Abgleich
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-[#4B5563]">
          SeaLAI zeigt hier später Partnerprofile, sobald dafür genügend geprüfte Informationen vorliegen.
        </p>
        <div className="mt-3 flex items-start gap-2 rounded-[14px] border border-seal-blue/20 bg-seal-blue/10 px-3 py-2 text-sm leading-relaxed text-seal-blue">
          <Info className="mt-0.5 shrink-0" size={15} />
          <span>{FALLBACK_DISCLOSURE}</span>
        </div>
      </section>
    );
  }

  const disclosure = matrix!.disclosure || FALLBACK_DISCLOSURE;
  const noFit = matrix!.status === "no_suitable_partner" || matrix!.rows.length === 0;

  return (
    <section className="rounded-[18px] border border-[#E5E7EB] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#F0F2F5] pb-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-[#111827]">
            <Building2 size={17} />
            Partner-Abgleich
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[#4B5563]">
            Nur zur Ansicht: Abgleich mit bekannten Partnerfähigkeiten.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge label={`${matrix!.eligiblePartnerCount} Partnerprofile`} tone="info" />
          <Badge label={readable(matrix!.status) || "status offen"} tone={noFit ? "warning" : "success"} />
        </div>
      </div>

      <div className="mt-3 flex items-start gap-2 rounded-[14px] border border-seal-blue/20 bg-seal-blue/10 px-3 py-2 text-sm leading-relaxed text-seal-blue">
        <ShieldCheck className="mt-0.5 shrink-0" size={15} />
        <span>{disclosure}</span>
      </div>

      {noFit ? (
        <div className="mt-3 flex items-start gap-2 rounded-[14px] border border-[#FDE2B8] bg-[#FFF4E5] px-3 py-2 text-sm leading-relaxed text-[#9A3412]">
          <AlertTriangle className="mt-0.5 shrink-0" size={15} />
          <span>
            Aktuell wurde kein Partnerprofil gemeldet. Grund: {readable(matrix!.noSuitablePartnerReason) || "nicht angegeben"}.
          </span>
        </div>
      ) : (
        <div className="mt-3 space-y-3">
          {matrix!.rows.map((row) => (
            <Row key={row.manufacturerId} row={row} />
          ))}
        </div>
      )}
    </section>
  );
}
