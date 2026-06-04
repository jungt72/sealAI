from __future__ import annotations

import httpx
from pathlib import Path
from typing import Any

from app.agent.prompts import prompts
from app.agent.state.models import GovernedSessionState, NormalizedParameter

from app.core.config import settings

_GOTENBERG_HTML_ENDPOINT = "/forms/chromium/convert/html"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
_PDF_STYLES_PATH = _PROMPTS_DIR / "pdf" / "styles.css"
_DEFAULT_PDF_OPTIONS = {
    "marginTop": "1",
    "marginBottom": "1",
    "marginLeft": "1",
    "marginRight": "1",
    "paperWidth": "8.27",
    "paperHeight": "11.69",
}


class PdfGenerationError(RuntimeError):
    """Raised when the configured PDF backend cannot return a PDF."""


def _status_label(status: str | None) -> tuple[str, str]:
    normalized = str(status or "").strip().lower()
    mapping = {
        "observed": ("bestaetigt", "observed"),
        "assumed": ("angenommen", "assumed"),
        "derived": ("abgeleitet", "derived"),
        "stale": ("veraltet", "stale"),
        "contradicted": ("widerspruechlich", "contradicted"),
    }
    if normalized in mapping:
        return mapping[normalized]
    return ("offen", "open")


def _format_value(value: Any, unit: str | None = None) -> str:
    if value is None:
        return "offen"
    if isinstance(value, float):
        text = f"{value:.2f}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    return f"{text} {unit}".strip() if unit else text


def _fit_score_value(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    if isinstance(value, int):
        return str(value)
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if 0.0 <= numeric <= 1.0:
        return f"{numeric:.2f}"
    return f"{numeric:.0f}"


def _preselection_items(preselection: dict[str, Any] | None) -> list[dict[str, str]]:
    if not preselection:
        return []

    items: list[dict[str, str]] = []
    priority = [
        ("seal_type", "Typ"),
        ("type", "Typ"),
        ("material", "Material"),
        ("primary_material", "Material"),
        ("elastomer", "Elastomer"),
        ("secondary_material", "Sekundaerwerkstoff"),
        ("requirement_class", "Klasse"),
        ("class_id", "Klasse"),
    ]
    fit_score = _fit_score_value(preselection.get("fit_score"))
    seen: set[str] = set()
    for key, label in priority:
        raw = preselection.get(key)
        if raw in (None, "", []):
            continue
        marker = f"{label}:{raw}"
        if marker in seen:
            continue
        seen.add(marker)
        items.append({"label": label, "value": _format_value(raw), "fit_score": fit_score})

    if not items:
        for key, raw in preselection.items():
            if key == "fit_score" or raw in (None, "", [], {}):
                continue
            items.append({"label": str(key).replace("_", " ").title(), "value": _format_value(raw), "fit_score": fit_score})
    return items


def _demand_analysis(state: GovernedSessionState) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if state.sealai_norm.application_summary:
        items.append({"label": "Anwendung", "value": state.sealai_norm.application_summary})
    seal_family = state.sealai_norm.identity.seal_family
    if seal_family:
        items.append({"label": "Dichtungsart", "value": seal_family})
    if state.decision.requirement_class and state.decision.requirement_class.class_id:
        items.append({"label": "Requirement Class", "value": state.decision.requirement_class.class_id})
    if state.decision.gov_class:
        items.append({"label": "Governance-Klasse", "value": state.decision.gov_class})
    return items


def build_pdf_context(state: GovernedSessionState) -> dict[str, Any]:
    parameters: list[dict[str, str]] = []
    for field_name, parameter in state.normalized.parameters.items():
        if isinstance(parameter, NormalizedParameter):
            param = parameter
        else:
            param = NormalizedParameter.model_validate(parameter)
        status_label, status_class = _status_label(state.normalized.parameter_status.get(field_name))
        parameters.append(
            {
                "label": param.field_name.replace("_", " ").title(),
                "value": _format_value(param.value, param.unit),
                "status_label": status_label,
                "status_class": status_class,
            }
        )

    calculations: list[dict[str, str]] = []
    if state.derived.velocity is not None:
        calculations.append(
            {
                "label": "Geschwindigkeit",
                "formula": "deterministische Ableitung aus Geometrie und Drehzahl",
                "value": _format_value(state.derived.velocity, "m/s"),
            }
        )
    if state.derived.pv_value is not None:
        calculations.append(
            {
                "label": "PV-Wert",
                "formula": "deterministische Berechnung aus Last- und Bewegungsdaten",
                "value": _format_value(state.derived.pv_value, "MPa·m/s"),
            }
        )

    created_at = "n/a"
    if getattr(state, "updated_at", None):
        created_at = state.updated_at.isoformat()

    return {
        "case_id": getattr(state, "case_id", None),
        "created_at": created_at,
        "basis_hash": state.decision.decision_basis_hash,
        "demand_analysis": _demand_analysis(state),
        "parameters": parameters,
        "calculations": calculations,
        "norm_references": list(state.derived.applicable_norms),
        "preselection_items": _preselection_items(state.decision.preselection),
        "assumptions": list(state.decision.assumptions),
        "open_points": list(state.decision.open_validation_points),
        "disclaimer": (
            "Technische Vorauswahl auf Basis der angegebenen Parameter. "
            "Die finale technische Eignung und Produktfreigabe erfolgt durch den Hersteller."
        ),
        "styles_css": _PDF_STYLES_PATH.read_text(encoding="utf-8"),
    }


def _gotenberg_html_endpoint() -> str:
    base_url = (settings.gotenberg_url or "").strip()
    if not base_url:
        raise PdfGenerationError("GOTENBERG_URL is not configured")
    return f"{base_url.rstrip('/')}{_GOTENBERG_HTML_ENDPOINT}"


async def generate_pdf_from_html(
    html: str,
    *,
    idempotency_key: str | None = None,
    filename: str = "index.html",
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
) -> bytes:
    """Convert an HTML document to PDF bytes via the configured Gotenberg service."""

    headers: dict[str, str] = {}
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                _gotenberg_html_endpoint(),
                files={"files": (filename, html.encode("utf-8"), "text/html")},
                data=dict(_DEFAULT_PDF_OPTIONS),
                headers=headers or None,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip() or str(exc)
        raise PdfGenerationError(f"Gotenberg HTML->PDF request failed: {detail}") from exc
    except httpx.RequestError as exc:
        raise PdfGenerationError(f"Gotenberg HTML->PDF request failed: {exc}") from exc

    return response.content


def render_inquiry_pdf_html(state: GovernedSessionState) -> str:
    """Render the productive inquiry PDF HTML template from governed state."""

    return prompts.render("pdf/inquiry.html.j2", build_pdf_context(state))
