# backend/app/api/v1/renderers/rfq_html.py
"""Render an HTML RFQ document from a CaseWorkspaceProjection.

Pure function — no I/O, no LLM, no DB calls.
Generates a self-contained HTML string suitable for browser display or print-to-PDF.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from app.api.v1.schemas.case_workspace import CaseWorkspaceProjection


def render_rfq_html(projection: CaseWorkspaceProjection) -> str:
    """Build a clean, self-contained HTML RFQ document from workspace projection."""
    pkg = projection.rfq_package
    rfq = projection.rfq_status
    gov = projection.governance_status
    cc = projection.candidate_clusters
    mq = projection.manufacturer_questions
    spec = projection.specificity
    case = projection.case_summary
    comp = projection.completeness
    cycle = projection.cycle_info

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rfq_id = escape(pkg.rfq_id or "—")
    basis_status = escape(pkg.rfq_basis_status)
    release_status = escape(gov.release_status)

    # --- Operating context rows ---
    context_rows = ""
    for key, value in pkg.operating_context_redacted.items():
        k = escape(_format_key(key))
        v = escape(str(value) if value is not None else "—")
        context_rows += f"<tr><td>{k}</td><td>{v}</td></tr>\n"

    # --- Candidate materials ---
    viable_rows = ""
    for c in cc.plausibly_viable:
        if isinstance(c, dict):
            mat = escape(str(c.get("value", "")))
            spc = escape(str(c.get("specificity", "family_only")))
            viable_rows += f"<tr><td>{mat}</td><td>{spc}</td><td>Viable</td></tr>\n"

    for c in cc.manufacturer_validation_required:
        if isinstance(c, dict):
            mat = escape(str(c.get("value", "")))
            spc = escape(str(c.get("specificity", "family_only")))
            viable_rows += f"<tr><td>{mat}</td><td>{spc}</td><td>Mfr. Validation Required</td></tr>\n"

    # --- Mandatory questions ---
    questions_html = ""
    all_mandatory = list(pkg.manufacturer_questions_mandatory)
    for q in mq.mandatory:
        if q not in all_mandatory:
            all_mandatory.append(q)
    for q in all_mandatory:
        questions_html += f"<li>{escape(q)}</li>\n"

    # --- Assumptions ---
    assumptions_html = ""
    all_assumptions = list(pkg.buyer_assumptions_acknowledged)
    for a in gov.assumptions_active:
        if a not in all_assumptions:
            all_assumptions.append(a)
    for a in all_assumptions:
        assumptions_html += f"<li>{escape(a)}</li>\n"

    # --- Disclaimers ---
    disclaimers_html = ""
    for d in gov.required_disclaimers:
        disclaimers_html += f"<li>{escape(d)}</li>\n"

    # --- Blockers ---
    blockers_html = ""
    for b in rfq.blockers:
        blockers_html += f"<li>{escape(b)}</li>\n"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SEALAI RFQ Document — {rfq_id}</title>
  <style>
    body {{ font-family: Arial, Helvetica, sans-serif; color: #111827; margin: 0; padding: 24px; line-height: 1.5; background: #fff; }}
    .header {{ margin-bottom: 20px; }}
    .header h1 {{ margin: 0 0 4px; font-size: 20px; color: #0f172a; }}
    .header .meta {{ color: #64748b; font-size: 12px; }}
    .badge {{ display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; border: 1px solid #cbd5e1; }}
    .badge-ready {{ background: #ecfdf5; color: #065f46; border-color: #6ee7b7; }}
    .badge-precheck {{ background: #fffbeb; color: #92400e; border-color: #fcd34d; }}
    .badge-validation {{ background: #eff6ff; color: #1e40af; border-color: #93c5fd; }}
    .badge-inadmissible {{ background: #f1f5f9; color: #475569; border-color: #cbd5e1; }}
    .card {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px; margin-bottom: 14px; }}
    .card h2 {{ margin: 0 0 8px; font-size: 14px; color: #1e293b; text-transform: uppercase; letter-spacing: 0.05em; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border: 1px solid #e5e7eb; padding: 6px 10px; text-align: left; }}
    th {{ background: #f8fafc; color: #0f172a; font-weight: 600; }}
    ul {{ margin: 0; padding-left: 18px; font-size: 13px; }}
    li {{ margin-bottom: 4px; }}
    .footer {{ margin-top: 20px; padding-top: 12px; border-top: 1px solid #e5e7eb; color: #94a3b8; font-size: 11px; }}
    .disclaimer {{ background: #fffbeb; border-left: 3px solid #f59e0b; padding: 10px; border-radius: 4px; font-size: 12px; color: #92400e; }}
    @media print {{ body {{ padding: 12px; }} .card {{ break-inside: avoid; }} }}
  </style>
</head>
<body>
  <div class="header">
    <h1>SEALAI — Technical RFQ Document</h1>
    <div class="meta">
      RFQ ID: {rfq_id} &middot;
      Generated: {generated_at} &middot;
      <span class="badge {_badge_class(basis_status)}">{escape(basis_status.replace("_", " ").title())}</span>
    </div>
  </div>

  <div class="card">
    <h2>Case Summary</h2>
    <table>
      <tr><td>Application</td><td>{escape(case.application_category or "—")}</td></tr>
      <tr><td>Seal Family</td><td>{escape(case.seal_family or "—")}</td></tr>
      <tr><td>Motion Type</td><td>{escape(case.motion_type or "—")}</td></tr>
      <tr><td>Coverage</td><td>{int(comp.coverage_score * 100)}%</td></tr>
      <tr><td>Specificity</td><td>{escape(spec.material_specificity_required.replace("_", " ").title())}</td></tr>
      <tr><td>Release Status</td><td>{escape(release_status.replace("_", " ").title())}</td></tr>
    </table>
  </div>

  {"" if not context_rows else f'''<div class="card">
    <h2>Operating Context (Redacted)</h2>
    <table>
      <thead><tr><th>Parameter</th><th>Value</th></tr></thead>
      <tbody>{context_rows}</tbody>
    </table>
  </div>'''}

  {"" if not viable_rows else f'''<div class="card">
    <h2>Candidate Materials</h2>
    <table>
      <thead><tr><th>Material</th><th>Specificity</th><th>Status</th></tr></thead>
      <tbody>{viable_rows}</tbody>
    </table>
  </div>'''}

  {"" if not questions_html else f'''<div class="card">
    <h2>Mandatory Manufacturer Questions</h2>
    <ul>{questions_html}</ul>
  </div>'''}

  {"" if not blockers_html else f'''<div class="card">
    <h2>Blockers / Open Points</h2>
    <ul>{blockers_html}</ul>
  </div>'''}

  {"" if not assumptions_html else f'''<div class="card">
    <h2>Active Assumptions</h2>
    <ul>{assumptions_html}</ul>
  </div>'''}

  {"" if not disclaimers_html else f'''<div class="disclaimer">
    <strong>Disclaimers</strong>
    <ul>{disclaimers_html}</ul>
  </div>'''}

  <div class="footer">
    Generated by SEALAI Engineering Platform &middot;
    Assertion Cycle {cycle.current_assertion_cycle_id} &middot;
    State Revision {cycle.state_revision} &middot;
    This document is auto-generated from validated engineering state.
    {"<strong>Artifacts were stale at generation time.</strong>" if cycle.derived_artifacts_stale else ""}
  </div>
</body>
</html>"""


def _format_key(key: str) -> str:
    """Convert snake_case keys to human-readable labels."""
    labels = {
        "medium": "Medium",
        "pressure_bar": "Pressure (bar)",
        "temperature_C": "Temperature (°C)",
        "shaft_diameter": "Shaft Diameter (mm)",
        "speed_rpm": "Speed (rpm)",
        "dynamic_type": "Motion Type",
        "shaft_runout": "Shaft Runout",
        "shaft_hardness": "Shaft Hardness",
        "seal_material": "Seal Material",
    }
    return labels.get(key, key.replace("_", " ").title())


def _badge_class(status: str) -> str:
    """Map basis status to CSS badge class."""
    return {
        "rfq_ready": "badge-ready",
        "precheck_only": "badge-precheck",
        "manufacturer_validation_required": "badge-validation",
    }.get(status, "badge-inadmissible")
