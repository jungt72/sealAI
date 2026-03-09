"use client";

import {
  Shield,
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  FileText,
  HelpCircle,
  Layers,
  RefreshCw,
  XCircle,
  Beaker,
  Ban,
  ShieldCheck,
  FlaskConical,
  Lightbulb,
  Database,
  Microscope,
  Factory,
  Zap,
  ArrowUpCircle,
} from "lucide-react";
import type { CaseWorkspaceProjection } from "@/lib/workspaceApi";

type Props = {
  workspace: CaseWorkspaceProjection;
  isLoading?: boolean;
  onActionBridge?: (text: string) => void;
};

// -- Release status badge styles --
const RELEASE_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  inadmissible: { bg: "bg-slate-100 ring-1 ring-slate-300", text: "text-slate-600", label: "Inadmissible" },
  precheck_only: { bg: "bg-amber-50 ring-1 ring-amber-300", text: "text-amber-700", label: "Precheck Only" },
  manufacturer_validation_required: { bg: "bg-blue-50 ring-1 ring-blue-300", text: "text-blue-700", label: "Mfr. Validation" },
  rfq_ready: { bg: "bg-emerald-50 ring-1 ring-emerald-300", text: "text-emerald-700", label: "RFQ Ready" },
};

function ReleaseBadge({ status }: { status: string }) {
  const style = RELEASE_STYLES[status] || RELEASE_STYLES.inadmissible;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide ${style.bg} ${style.text}`}>
      {status === "rfq_ready" ? <CheckCircle2 className="h-3 w-3" /> : <Shield className="h-3 w-3" />}
      {style.label}
    </span>
  );
}

function ProgressBar({ value, max = 1 }: { value: number; max?: number }) {
  const pct = Math.min(100, Math.round((value / max) * 100));
  const color = pct >= 80 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-400" : "bg-slate-300";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-slate-100 overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[11px] font-mono text-slate-500 w-8 text-right">{pct}%</span>
    </div>
  );
}

function SectionHeader({ icon: Icon, title, badge }: { icon: React.ElementType; title: string; badge?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-2">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-600 uppercase tracking-wide">
        <Icon className="h-3.5 w-3.5" />
        {title}
      </div>
      {badge}
    </div>
  );
}

function CountChip({ label, count, variant = "default" }: { label: string; count: number; variant?: "default" | "warn" | "danger" | "ok" }) {
  const styles = {
    default: "bg-slate-50 text-slate-600 ring-slate-200",
    warn: "bg-amber-50 text-amber-700 ring-amber-200",
    danger: "bg-rose-50 text-rose-700 ring-rose-200",
    ok: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ${styles[variant]}`}>
      {label}
      <span className="font-bold">{count}</span>
    </span>
  );
}

// -- Severity styling for conflict items --
const SEVERITY_STYLE: Record<string, { dot: string; text: string }> = {
  CRITICAL: { dot: "bg-rose-500", text: "text-rose-700" },
  BLOCKING_UNKNOWN: { dot: "bg-rose-400", text: "text-rose-600" },
  HARD: { dot: "bg-amber-500", text: "text-amber-700" },
  SOFT: { dot: "bg-slate-400", text: "text-slate-500" },
  INFO: { dot: "bg-blue-400", text: "text-blue-600" },
  FALSE_CONFLICT: { dot: "bg-slate-300", text: "text-slate-400" },
  RESOLUTION_REQUIRES_MANUFACTURER_SCOPE: { dot: "bg-blue-500", text: "text-blue-700" },
};

// -- Cluster badge for candidates --
const CLUSTER_STYLE: Record<string, { bg: string; label: string }> = {
  viable: { bg: "bg-emerald-100 text-emerald-700 ring-emerald-300", label: "Viable" },
  mfr_validation: { bg: "bg-blue-100 text-blue-700 ring-blue-300", label: "Mfr. Val." },
  excluded: { bg: "bg-rose-100 text-rose-700 ring-rose-300", label: "Excluded" },
};

// -- Claim origin icons --
function ClaimOriginIcon({ origin }: { origin: string }) {
  switch (origin) {
    case "deterministic": return <Database className="h-3 w-3 text-blue-500" />;
    case "evidence": return <Microscope className="h-3 w-3 text-indigo-500" />;
    case "heuristic": return <Lightbulb className="h-3 w-3 text-amber-500" />;
    case "expert": return <FlaskConical className="h-3 w-3 text-purple-500" />;
    default: return <CircleDot className="h-3 w-3 text-slate-400" />;
  }
}

// -- Specificity label --
function specificityLabel(s: string | undefined): string {
  if (!s) return "";
  const map: Record<string, string> = {
    compound_required: "Compound",
    product_family_required: "Product Family",
    subfamily: "Subfamily",
    family_only: "Family",
  };
  return map[s] || s.replace(/_/g, " ");
}

export default function CaseStatusPanel({ workspace: ws, isLoading, onActionBridge }: Props) {
  const { governance_status: gov, completeness: comp, candidate_clusters: cc, conflicts, claims_summary: claims, manufacturer_questions: mq, rfq_status: rfq, artifact_status: art, cycle_info: cycle, specificity: spec, case_summary: summary } = ws;

  const handleHintClick = (hint: any) => {
    if (!onActionBridge) return;
    const text = hint.action_type === "specify_material" 
      ? `Ich möchte das Material genauer spezifizieren (z.B. genaue Compound-Bezeichnung).`
      : `Lass uns über ${hint.label.replace('Define ', '')} sprechen, um die Spezifität zu erhöhen.`;
    onActionBridge(text);
  };

  return (
    <div className="rounded-2xl border border-slate-200/70 bg-white/60 backdrop-blur-sm p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Case Governance</p>
        {isLoading && <RefreshCw className="h-3.5 w-3.5 text-slate-400 animate-spin" />}
      </div>

      {/* Release Status */}
      <div className="flex items-center justify-between gap-2">
        <ReleaseBadge status={gov.release_status} />
        {cycle.derived_artifacts_stale && (
          <span className="flex items-center gap-1 text-[10px] font-bold text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full ring-1 ring-amber-200">
            <AlertTriangle className="h-3 w-3" />
            Stale
          </span>
        )}
      </div>

      {/* Completeness */}
      <section>
        <SectionHeader
          icon={Layers}
          title="Completeness"
          badge={<span className="text-[10px] font-medium text-slate-400 capitalize">{comp.completeness_depth}</span>}
        />
        <ProgressBar value={comp.coverage_score} />
        {comp.missing_critical_parameters.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {comp.missing_critical_parameters.slice(0, 4).map((p) => (
              <span key={p} className="text-[10px] bg-rose-50 text-rose-600 px-1.5 py-0.5 rounded ring-1 ring-rose-200 font-medium">
                {p}
              </span>
            ))}
            {comp.missing_critical_parameters.length > 4 && (
              <span className="text-[10px] text-slate-400">+{comp.missing_critical_parameters.length - 4}</span>
            )}
          </div>
        )}
        {comp.coverage_gaps.length > 0 && comp.missing_critical_parameters.length === 0 && (
          <p className="mt-1 text-[10px] text-slate-400">{comp.coverage_gaps.length} gap{comp.coverage_gaps.length !== 1 ? "s" : ""} remaining</p>
        )}
      </section>

      {/* Specificity Elevation */}
      {spec.elevation_possible && (
        <section className="bg-blue-50/50 rounded-xl p-3 border border-blue-100 ring-1 ring-blue-200/50">
          <SectionHeader
            icon={Zap}
            title="Increase Specificity"
            badge={spec.elevation_target && <span className="text-[9px] font-bold text-blue-600 bg-blue-100 px-1.5 py-0.5 rounded-full uppercase tracking-wider text-center">Target: {spec.elevation_target.replace(/_/g, ' ')}</span>}
          />
          <ul className="space-y-1.5">
            {spec.elevation_hints.map((hint, i) => (
              <li key={i}>
                <button
                  onClick={() => handleHintClick(hint)}
                  className="w-full flex items-start gap-2 text-[10px] text-slate-600 leading-snug hover:bg-white/60 p-1.5 rounded-lg transition-colors border border-transparent hover:border-blue-200 hover:shadow-sm text-left group"
                >
                  <ArrowUpCircle className="h-3 w-3 text-blue-500 shrink-0 mt-0.5 group-hover:scale-110 transition-transform" />
                  <div className="flex flex-col">
                    <span className="font-semibold text-slate-700">{hint.label}</span>
                    <span className="text-[9px] text-slate-400">{hint.reason}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ================================================================ */}
      {/* ENGINEERING MATERIALS — detailed view */}
      {/* ================================================================ */}
      {cc.total_candidates > 0 && (
        <section>
          <SectionHeader
            icon={CircleDot}
            title="Engineering Materials"
            badge={<CountChip label="Total" count={cc.total_candidates} />}
          />
          <div className="space-y-1.5">
            {/* Viable */}
            {cc.plausibly_viable.map((c, i) => (
              <CandidateRow key={`v-${i}`} candidate={c} cluster="viable" />
            ))}
            {/* Mfr. validation */}
            {cc.manufacturer_validation_required.map((c, i) => (
              <CandidateRow key={`m-${i}`} candidate={c} cluster="mfr_validation" />
            ))}
            {/* Excluded */}
            {cc.inadmissible_or_excluded.map((c, i) => (
              <CandidateRow key={`x-${i}`} candidate={c} cluster="excluded" />
            ))}
          </div>
        </section>
      )}

      {/* ================================================================ */}
      {/* CONFLICTS — detailed view */}
      {/* ================================================================ */}
      {conflicts.total > 0 && (
        <section>
          <SectionHeader
            icon={AlertTriangle}
            title="Conflicts"
            badge={
              <div className="flex gap-1">
                {conflicts.open > 0 && <CountChip label="Open" count={conflicts.open} variant="danger" />}
                {conflicts.resolved > 0 && <CountChip label="Resolved" count={conflicts.resolved} variant="ok" />}
              </div>
            }
          />
          <div className="space-y-1.5">
            {/* Open conflicts first, then resolved */}
            {[...conflicts.items]
              .sort((a, b) => (a.resolution_status === "OPEN" ? -1 : 1) - (b.resolution_status === "OPEN" ? -1 : 1))
              .map((c, i) => (
                <ConflictRow key={i} conflict={c} />
              ))}
          </div>
        </section>
      )}

      {/* ================================================================ */}
      {/* CLAIMS — detailed view */}
      {/* ================================================================ */}
      {claims.total > 0 && (
        <section>
          <SectionHeader
            icon={ShieldCheck}
            title="Claims"
            badge={<CountChip label="Total" count={claims.total} />}
          />
          {/* Origin breakdown chips */}
          <div className="flex flex-wrap gap-1 mb-2">
            {Object.entries(claims.by_origin).map(([origin, n]) => (
              <span key={origin} className="inline-flex items-center gap-1 text-[10px] font-medium text-slate-500 bg-slate-50 px-1.5 py-0.5 rounded ring-1 ring-slate-200">
                <ClaimOriginIcon origin={origin} />
                {origin} {n}
              </span>
            ))}
          </div>
          {/* Individual claim items */}
          {(claims.items || []).length > 0 && (
            <div className="space-y-1">
              {claims.items.slice(0, 6).map((claim, i) => (
                <div key={i} className="flex items-start gap-1.5 text-[11px] leading-tight">
                  <ClaimOriginIcon origin={claim.claim_origin} />
                  <span className="text-slate-600 flex-1 truncate">{claim.value || claim.claim_type.replace(/_/g, " ")}</span>
                  <span className="text-[9px] text-slate-400 shrink-0 capitalize">{claim.claim_type.replace(/_/g, " ")}</span>
                </div>
              ))}
              {claims.total > 6 && (
                <p className="text-[10px] text-slate-400 pl-5">+{claims.total - 6} more</p>
              )}
            </div>
          )}
        </section>
      )}

      {/* RFQ Status */}
      <section>
        <SectionHeader icon={FileText} title="RFQ" />
        <div className="flex flex-wrap gap-1.5">
          <CountChip
            label={rfq.admissibility_status === "ready" ? "Ready" : rfq.admissibility_status === "provisional" ? "Provisional" : "Inadmissible"}
            count={rfq.blockers.length}
            variant={rfq.admissibility_status === "ready" ? "ok" : rfq.blockers.length > 0 ? "danger" : "default"}
          />
          {rfq.rfq_confirmed && (
            <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-600">
              <CheckCircle2 className="h-3 w-3" /> Confirmed
            </span>
          )}
          {art.has_rfq_draft && (
            <span className="text-[10px] text-slate-400 font-medium">Draft available</span>
          )}
        </div>
        {rfq.blockers.length > 0 && (
          <ul className="mt-1 space-y-0.5">
            {rfq.blockers.slice(0, 2).map((b, i) => (
              <li key={i} className="text-[10px] text-rose-600 truncate flex items-center gap-1">
                <XCircle className="h-2.5 w-2.5 shrink-0" />{b}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Governance assumptions & disclaimers */}
      {(gov.assumptions_active.length > 0 || gov.required_disclaimers.length > 0) && (
        <section className="border-t border-slate-100 pt-3">
          {gov.assumptions_active.length > 0 && (
            <p className="text-[10px] text-slate-400 leading-snug mb-1">
              <span className="font-semibold text-slate-500">Assumptions:</span>{" "}
              {gov.assumptions_active.slice(0, 3).join(", ")}
              {gov.assumptions_active.length > 3 && ` +${gov.assumptions_active.length - 3}`}
            </p>
          )}
          {gov.required_disclaimers.length > 0 && (
            <p className="text-[10px] text-amber-600 leading-snug">
              <span className="font-semibold">Disclaimer:</span>{" "}
              {gov.required_disclaimers[0]}
            </p>
          )}
        </section>
      )}

      {/* Cycle / Revision footer */}
      <div className="flex items-center justify-between text-[10px] text-slate-400 border-t border-slate-100 pt-2">
        <span>Cycle {cycle.current_assertion_cycle_id} / Rev {cycle.asserted_profile_revision}</span>
        <span>Turn {summary.turn_count}/{summary.max_turns}</span>
        {spec.material_specificity_required !== "family_only" && (
          <span className="capitalize">{spec.material_specificity_required.replace(/_/g, " ")}</span>
        )}
      </div>
    </div>
  );
}

// ========================================================================
// Sub-components for detailed engineering objects
// ========================================================================

function CandidateRow({ candidate, cluster }: { candidate: Record<string, unknown>; cluster: "viable" | "mfr_validation" | "excluded" }) {
  const cs = CLUSTER_STYLE[cluster];
  const name = String(candidate.value || candidate.kind || "—");
  const kind = String(candidate.kind || "");
  const specificity = specificityLabel(candidate.specificity as string | undefined);
  const excludedBy = candidate.excluded_by_gate as string | undefined;

  return (
    <div className={`flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[11px] ring-1 ${cs.bg}`}>
      {cluster === "excluded" ? <Ban className="h-3 w-3 shrink-0" /> : cluster === "mfr_validation" ? <Factory className="h-3 w-3 shrink-0" /> : <CheckCircle2 className="h-3 w-3 shrink-0" />}
      <span className="font-semibold truncate flex-1">{name}</span>
      {specificity && <span className="text-[9px] opacity-70 shrink-0">{specificity}</span>}
      {excludedBy && <span className="text-[9px] opacity-60 shrink-0 italic">({excludedBy})</span>}
    </div>
  );
}

function ConflictRow({ conflict }: { conflict: { conflict_type: string; severity: string; summary: string; resolution_status: string } }) {
  const sev = SEVERITY_STYLE[conflict.severity] || SEVERITY_STYLE.HARD;
  const isOpen = conflict.resolution_status === "OPEN";
  const typeLabel = conflict.conflict_type.replace(/_/g, " ").replace(/CONFLICT/g, "").trim();

  return (
    <div className={`rounded-lg px-2.5 py-1.5 text-[11px] ring-1 ${isOpen ? "ring-slate-200 bg-white" : "ring-slate-100 bg-slate-50/50 opacity-70"}`}>
      <div className="flex items-center gap-1.5 mb-0.5">
        <span className={`h-2 w-2 rounded-full shrink-0 ${sev.dot}`} />
        <span className={`font-semibold uppercase text-[10px] tracking-wide ${sev.text}`}>{conflict.severity}</span>
        <span className="text-[9px] text-slate-400 capitalize">{typeLabel}</span>
        {!isOpen && <span className="ml-auto text-[9px] text-emerald-500 font-bold">Resolved</span>}
      </div>
      {conflict.summary && (
        <p className="text-slate-600 leading-snug pl-3.5 truncate">{conflict.summary}</p>
      )}
    </div>
  );
}
