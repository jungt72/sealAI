"""Deterministic PDF renderer for governed RFQ preview exports.

The renderer is intentionally dependency-free and only consumes the already
allowlisted RFQ export contract. It does not read files, call an LLM, or contact
external systems.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
LEFT_MARGIN = 48
TOP_MARGIN = 790
LINE_HEIGHT = 14
MAX_CHARS = 92


def render_rfq_export_pdf(export_payload: Mapping[str, Any]) -> bytes:
    """Render an allowlisted RFQ export payload as a simple PDF document."""

    content = _mapping(export_payload.get("content"))
    lines = _build_rfq_lines(export_payload=export_payload, content=content)
    pages = _paginate(lines)
    return _build_pdf(pages)


def _build_rfq_lines(
    *, export_payload: Mapping[str, Any], content: Mapping[str, Any]
) -> list[str]:
    generated_at = _generated_at(export_payload)
    case_id = _nested_text(content, "safe_case_reference", "case_id") or _text(
        export_payload.get("case_id")
    )
    preview_id = _nested_text(content, "preview_reference", "preview_id") or _text(
        export_payload.get("preview_id")
    )
    revision = _mapping(content.get("revision"))

    lines = [
        "sealing | Intelligence - Anfragebasis fuer Herstellerpruefung",
        "",
        "Sehr geehrte Damen und Herren,",
        "bitte pruefen Sie auf Basis der folgenden, vom Anwender bestaetigten "
        "Anfragebasis den Technical RWDR RFQ Brief. Die Angaben stammen aus "
        "dem backend-eigenen Fallstand und sind als strukturierte "
        "Anfragebasis fuer Ihre Herstellerpruefung zu verstehen.",
        "",
        "Wichtiger Hinweis: Dieser Technical RWDR RFQ Brief strukturiert die "
        "Anfrage. Er enthaelt keine finale technische Eignungsfreigabe, keine "
        "Materialfreigabe, keine Produktempfehlung und keine Herstellerfreigabe. "
        "Die finale technische Bewertung erfolgt durch Hersteller, Haendler "
        "oder eine verantwortliche technische Stelle.",
        "",
        f"Case-ID: {case_id or '-'}",
        f"Preview-ID: {preview_id or '-'}",
        f"Fallstand: {_text(revision.get('case_revision')) or '-'}",
        f"Export erzeugt: {generated_at}",
        "",
    ]

    technical_fields = _sequence(content.get("technical_fields"))
    if technical_fields:
        lines.extend(["Technische Angaben", ""])
        for field in technical_fields:
            if not isinstance(field, Mapping):
                continue
            name = _text(field.get("field") or field.get("field_name")) or "Feld"
            value = _text(field.get("value")) or "Noch offen"
            engineering = _mapping(field.get("engineering_value"))
            unit = _text(engineering.get("unit"))
            status = _text(field.get("status")) or "unbewertet"
            provenance = _text(field.get("provenance")) or "nicht geliefert"
            confidence = _text(field.get("confidence")) or "nicht geliefert"
            suffix = f" {unit}" if unit and unit not in value else ""
            lines.append(
                f"- {name}: {value}{suffix} | Status: {status} | Herkunft: "
                f"{provenance} | Sicherheit: {confidence}"
            )
        lines.append("")

    rwdr_brief = _mapping(content.get("technical_rwdr_rfq_brief"))
    if rwdr_brief:
        evaluation = _mapping(rwdr_brief.get("evaluation"))
        lines.extend(
            [
                "Technical RWDR RFQ Brief",
                "",
                f"Status: {_text(rwdr_brief.get('status')) or '-'}",
                "Grenze: Herstellerpruefbasis; keine Produktauswahl, kein "
                "Hersteller-Ranking und keine automatische Weitergabe.",
            ]
        )
        open_points = _sequence(evaluation.get("open_points"))
        if open_points:
            lines.append("Offene RWDR-MVP Punkte:")
            for item in open_points:
                lines.append(f"- {_text(item)}")
        for title, key in (
            ("Bestaetigte Brief-Fakten", "confirmed_case_fields"),
            ("Deterministische Berechnungen", "calculation_fields"),
        ):
            fields = _sequence(rwdr_brief.get(key))
            if not fields:
                continue
            lines.extend([title, ""])
            for field in fields:
                if not isinstance(field, Mapping):
                    continue
                name = _text(field.get("field")) or "Feld"
                value = _text(field.get("value")) or "Noch offen"
                unit = _text(field.get("unit"))
                suffix = f" {unit}" if unit and unit not in value else ""
                lines.append(f"- {name}: {value}{suffix}")
        lines.append("")

    rwdr_sections = _sequence(content.get("rwdr_sections"))
    if rwdr_sections:
        lines.extend(["RWDR Brief-Abschnitte", ""])
        for section in rwdr_sections:
            if not isinstance(section, Mapping):
                continue
            title = _text(section.get("title")) or "Section"
            lines.append(title)
            items = _sequence(section.get("items"))
            if not items:
                lines.append("- Keine Angaben gemeldet.")
            for item in items[:12]:
                lines.append(f"- {_text(item)}")
            lines.append("")

    _append_section(lines, "Offene Punkte", content.get("open_points"))
    _append_section(lines, "Risiken", content.get("risks"))
    _append_section(
        lines,
        "Vom Hersteller zu pruefen",
        content.get("manufacturer_review_notes"),
    )

    evidence_refs = _sequence(content.get("evidence_references"))
    if evidence_refs:
        lines.extend(["Belegreferenzen", ""])
        for ref in evidence_refs:
            lines.append(f"- {_text(ref)}")
        lines.append("")

    source_summary = _mapping(content.get("source_validation_summary"))
    if source_summary:
        lines.extend(["Quellen-/Validierungsstatus", ""])
        for key, value in source_summary.items():
            lines.append(f"- {_human_key(key)}: {_text(value)}")
        lines.append("")

    lines.extend(
        [
            "Rueckfragen / Herstellerantwort",
            "",
            "Bitte geben Sie zu Ihrer Bewertung mindestens Werkstoff/Compound, "
            "Dichtungsbauart, zulaessige Betriebsgrenzen, Medienbestaendigkeit, "
            "PV-/Geschwindigkeitsgrenzen, Gegenlaufflaechenanforderungen, "
            "Nachweise, offene Annahmen und Liefer-/Herstellerdaten an.",
            "",
            "Mit freundlichen Gruessen",
            "SealAI Anfragebasis",
        ]
    )
    return _wrap_lines(lines)


def _append_section(lines: list[str], title: str, value: Any) -> None:
    items = [_text(item) for item in _sequence(value)]
    items = [item for item in items if item]
    if not items:
        return
    lines.extend([title, ""])
    for item in items:
        lines.append(f"- {item}")
    lines.append("")


def _generated_at(export_payload: Mapping[str, Any]) -> str:
    value = export_payload.get("created_at")
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = _text(value)
    if not text:
        return "nicht geliefert"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _build_pdf(pages: Sequence[Sequence[str]]) -> bytes:
    objects: list[bytes] = []
    total_pages = max(1, len(pages))
    pages_object_id = 2
    font_object_id = 3
    first_page_object_id = 4

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    page_refs = " ".join(
        f"{first_page_object_id + index * 2} 0 R" for index in range(total_pages)
    )
    objects.append(
        f"<< /Type /Pages /Kids [{page_refs}] /Count {total_pages} >>".encode()
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for index, page_lines in enumerate(pages or [[]]):
        page_object_id = first_page_object_id + index * 2
        content_object_id = page_object_id + 1
        stream = _page_stream(page_lines)
        objects.append(
            (
                "<< /Type /Page /Parent "
                f"{pages_object_id} 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources << /Font << /F1 {font_object_id} 0 R >> >> "
                f"/Contents {content_object_id} 0 R >>"
            ).encode()
        )
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_number, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_number} 0 obj\n".encode())
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(
        (
            "trailer\n"
            f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            "startxref\n"
            f"{xref_offset}\n"
            "%%EOF\n"
        ).encode()
    )
    return bytes(pdf)


def _page_stream(lines: Sequence[str]) -> bytes:
    commands = ["BT", "/F1 10 Tf", "12 TL", f"{LEFT_MARGIN} {TOP_MARGIN} Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("T*")
        commands.append(f"({_pdf_text(line)}) Tj")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1", "replace")


def _paginate(lines: Sequence[str]) -> list[list[str]]:
    max_lines = int((TOP_MARGIN - 48) / LINE_HEIGHT)
    pages: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if len(current) >= max_lines:
            pages.append(current)
            current = []
        current.append(line)
    if current or not pages:
        pages.append(current)
    return pages


def _wrap_lines(lines: Sequence[str]) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        text = _text(line)
        if not text:
            wrapped.append("")
            continue
        while len(text) > MAX_CHARS:
            split_at = text.rfind(" ", 0, MAX_CHARS)
            if split_at <= 0:
                split_at = MAX_CHARS
            wrapped.append(text[:split_at].strip())
            text = text[split_at:].strip()
        wrapped.append(text)
    return wrapped


def _pdf_text(value: str) -> str:
    return (
        _pdf_ascii_text(value)
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def _pdf_ascii_text(value: str) -> str:
    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "Ä": "Ae",
        "Ö": "Oe",
        "Ü": "Ue",
        "ß": "ss",
        "–": "-",
        "—": "-",
        "“": '"',
        "”": '"',
        "„": '"',
        "’": "'",
        "…": "...",
    }
    return "".join(replacements.get(char, char) for char in value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return (value,)


def _nested_text(mapping: Mapping[str, Any], key: str, nested_key: str) -> str:
    return _text(_mapping(mapping.get(key)).get(nested_key))


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Mapping):
        return "; ".join(f"{_human_key(k)}: {_text(v)}" for k, v in value.items())
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return ", ".join(_text(item) for item in value)
    return str(value).replace("\n", " ").strip()


def _human_key(value: Any) -> str:
    return str(value).replace("_", " ").strip().capitalize()
