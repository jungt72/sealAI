"""P6 Digital Twin RFQ document generation node.

Renders a strict Jinja2 HTML report from state.rfq_payload and attempts PDF generation.
Falls back to storing rendered HTML if no PDF engine is available.
"""

from __future__ import annotations

import base64
import io
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import structlog
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound, UndefinedError

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState

logger = structlog.get_logger("rag.nodes.p6_generate_pdf")

_TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "templates"
_TEMPLATE_NAME = "rfq_template.html"
_REQUIRED_RFQ_KEYS = (
    "validated_parameters",
    "kinematics_and_physics",
    "sealai_poc_rationale",
    "matched_partners",
)


@lru_cache(maxsize=1)
def _template_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _coerce_payload(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dumped
    return {}


def _validate_rfq_payload(payload: Dict[str, Any]) -> Optional[str]:
    if not payload:
        return "P6: rfq_payload missing or empty."
    missing = [key for key in _REQUIRED_RFQ_KEYS if key not in payload]
    if missing:
        return f"P6: rfq_payload missing required keys: {', '.join(missing)}"
    return None


def _render_html(payload: Dict[str, Any]) -> str:
    template = _template_env().get_template(_TEMPLATE_NAME)
    return template.render(rfq_payload=payload)


def _try_weasyprint(html: str) -> Tuple[Optional[bytes], Optional[str]]:
    try:
        from weasyprint import HTML  # type: ignore

        pdf_bytes = HTML(string=html).write_pdf()
        return pdf_bytes, None
    except Exception as exc:  # pragma: no cover - optional dependency
        return None, str(exc)


def _try_xhtml2pdf(html: str) -> Tuple[Optional[bytes], Optional[str]]:
    try:
        from xhtml2pdf import pisa  # type: ignore

        out = io.BytesIO()
        status = pisa.CreatePDF(src=html, dest=out, encoding="utf-8")
        if getattr(status, "err", 1) == 0:
            return out.getvalue(), None
        return None, "xhtml2pdf reported render errors"
    except Exception as exc:  # pragma: no cover - optional dependency
        return None, str(exc)


def _html_to_pdf_bytes(html: str) -> Tuple[Optional[bytes], str]:
    pdf_bytes, error = _try_weasyprint(html)
    if pdf_bytes is not None:
        return pdf_bytes, "weasyprint"

    pdf_bytes, error2 = _try_xhtml2pdf(html)
    if pdf_bytes is not None:
        return pdf_bytes, "xhtml2pdf"

    reason = error2 or error or "no_pdf_engine_available"
    logger.warning("p6_pdf_engine_unavailable", reason=reason)
    return None, "html_fallback"


def node_p6_generate_pdf(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Generate strict RFQ document output from state.rfq_payload."""
    # FIX 3: Turn limit and knowledge coverage guard
    turn_count = int(getattr(state, "turn_count", 0) or 0)
    coverage_ready = getattr(state, "coverage_disclosure_ready", False)
    if not coverage_ready and turn_count >= 12:
        logger.warning("p6_pdf_blocked_by_turn_limit", turn_count=turn_count)
        return {
            "rfq_ready": False,
            "rfq_blocked": True,
            "error": "Turn limit reached without full knowledge coverage. PDF generation blocked.",
            "phase": PHASE.PROCUREMENT,
            "last_node": "node_p6_generate_pdf",
        }

    payload = _coerce_payload(getattr(state, "rfq_payload", {}) or {})

    logger.info(
        "p6_generate_pdf_start",
        has_rfq_payload=bool(payload),
        payload_keys=sorted(payload.keys()) if payload else [],
        run_id=state.run_id,
        thread_id=state.thread_id,
    )

    update: Dict[str, Any] = {
        "phase": PHASE.PROCUREMENT,
        "last_node": "node_p6_generate_pdf",
    }

    payload_error = _validate_rfq_payload(payload)
    if payload_error:
        update["rfq_ready"] = False
        update["error"] = payload_error
        return update

    try:
        html = _render_html(payload)
    except (TemplateNotFound, UndefinedError) as exc:
        update["rfq_ready"] = False
        update["error"] = f"P6 template rendering error: {exc}"
        logger.error("p6_generate_pdf_render_error", error=str(exc), template=_TEMPLATE_NAME)
        return update

    pdf_bytes, engine = _html_to_pdf_bytes(html)

    update["rfq_html_report"] = html
    update["rfq_ready"] = True

    if pdf_bytes is not None:
        update["rfq_pdf_base64"] = base64.b64encode(pdf_bytes).decode("ascii")
        logger.info(
            "p6_generate_pdf_done",
            mode="pdf",
            engine=engine,
            pdf_size_bytes=len(pdf_bytes),
            run_id=state.run_id,
        )
    else:
        logger.info(
            "p6_generate_pdf_done",
            mode="html_fallback",
            engine=engine,
            html_size_chars=len(html),
            run_id=state.run_id,
        )

    return update


__all__ = ["node_p6_generate_pdf"]
