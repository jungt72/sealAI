from __future__ import annotations
from typing import Dict, Any

def _ensure_reportlab():
    # Lazy import to avoid startup crashes if reportlab not yet installed
    global canvas, A4, mm, simpleSplit
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        from reportlab.lib.utils import simpleSplit
    except Exception as e:
        raise RuntimeError("reportlab missing: pip install reportlab>=4.2.0") from e

def _draw_multiline(c, text: str, x: float, y: float, max_width: float, leading: float = 14):
    lines = simpleSplit(text, "Helvetica", 10, max_width)
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y

def generate_rfq_pdf(data: Dict[str, Any], out_path: str) -> None:
    _ensure_reportlab()
    c = canvas.Canvas(out_path, pagesize=A4)
    width, height = A4
    x0, y = 20*mm, height - 25*mm

    c.setFont("Helvetica-Bold", 14)
    c.drawString(x0, y, "RFQ – Request for Quotation")
    c.setFont("Helvetica", 9)
    c.drawString(x0, y-14, "SealAI – Dichtungstechnik Beratung")
    y -= 30

    # Eingabedaten
    c.setFont("Helvetica-Bold", 11); c.drawString(x0, y, "Eingabedaten"); y -= 12
    c.setFont("Helvetica", 10)
    for k, v in (data.get("params") or {}).items():
        c.drawString(x0, y, f"- {k}: {v}"); y -= 12

    # Abgeleitete Kennwerte
    y -= 8; c.setFont("Helvetica-Bold", 11); c.drawString(x0, y, "Abgeleitete Kennwerte"); y -= 12
    c.setFont("Helvetica", 10)
    for k, v in (data.get("derived") or {}).items():
        c.drawString(x0, y, f"- {k}: {v}"); y -= 12

    # Kandidaten
    y -= 8; c.setFont("Helvetica-Bold", 11); c.drawString(x0, y, "Top-Partnerprodukte"); y -= 12
    c.setFont("Helvetica", 10); c.drawString(x0, y, "(Preise/LZ/MOQ durch Hersteller)"); y -= 14
    for cand in (data.get("candidates") or [])[:10]:
        line = f"- {cand.get('title')} | {cand.get('vendor_id')} | Material {cand.get('material')} | Profil {cand.get('profile')}"
        y = _draw_multiline(c, line, x0, y, width - 40*mm)
        if y < 40*mm:
            c.showPage(); y = height - 25*mm; c.setFont("Helvetica", 10)

    # Quellen
    y -= 8; c.setFont("Helvetica-Bold", 11); c.drawString(x0, y, "Quellen"); y -= 12
    c.setFont("Helvetica", 9)
    for src in (data.get("sources") or [])[:12]:
        y = _draw_multiline(c, f"- {src}", x0, y, width - 40*mm, leading=12)
        if y < 40*mm:
            c.showPage(); y = height - 25*mm; c.setFont("Helvetica", 9)

    # Rechtshinweis
    y -= 8; c.setFont("Helvetica", 9)
    leg = data.get("legal_notice") or "Verbindliche Eignungszusage obliegt dem Hersteller."
    _draw_multiline(c, f"Rechtshinweis: {leg}", x0, y, width - 40*mm, leading=12)

    c.showPage()
    c.save()
