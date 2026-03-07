"""
Seed-Skript: deterministic_din_norms + deterministic_material_limits
====================================================================

Starter-Set für NBR, FKM, PTFE — erster belastbarer Datensatz für den
deterministischen SQL-Pfad (query_deterministic_norms / aquery_deterministic_norms).

Fachliche Quellen:
  DIN 3760:1996-02  — Radial-Wellendichtringe für Wellen (Wellendichtringe)
  ISO 6194-1:2007   — Rotary shaft lip-type seals (PTFE lip seals)

Designregeln:
  - Nur konservativ belegbare Werte, keine Fantasiedaten
  - tenant_id = NULL → global sichtbar (matcht jede Anfrage per SQL-Logik)
  - Idempotent: SELECT-before-INSERT Guard (NULL bricht ON CONFLICT DO NOTHING)
  - effective_date = 2020-01-01 → immer aktiv, klar nachvollziehbar
  - valid_until = NULL → kein künstliches Ablaufdatum im Starter-Set
  - is_active = TRUE

Aufruf:
  python -m app.data.seeds.seed_deterministic_norms
  oder direkt:
  python backend/app/data/seeds/seed_deterministic_norms.py

Gibt bei jeder Zeile aus ob sie neu eingefügt oder bereits vorhanden war.
"""

from __future__ import annotations

import sys
import os
from datetime import date
from typing import Any, Dict, List, Optional

# Damit der Import aus /app/ heraus funktioniert (Container: WORKDIR=/app)
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.normpath(os.path.join(_HERE, "..", "..", "..", ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Verbindung
# ---------------------------------------------------------------------------

def _get_seed_url() -> str:
    """Liest POSTGRES_SYNC_URL oder DATABASE_URL aus ENV, rewritet asyncpg→psycopg."""
    raw = (
        os.environ.get("POSTGRES_SYNC_URL", "")
        or os.environ.get("DATABASE_URL", "")
    ).strip()
    if not raw:
        # Fallback: Settings laden (funktioniert nur wenn APP im Python-Path)
        try:
            from app.core.config import settings
            raw = (
                str(getattr(settings, "POSTGRES_SYNC_URL", "") or "").strip()
                or str(getattr(settings, "database_url", "") or "").strip()
            )
        except Exception:
            pass
    if not raw:
        raise RuntimeError(
            "Keine Postgres-URL gefunden. Setze POSTGRES_SYNC_URL oder DATABASE_URL."
        )
    if raw.startswith("postgresql+asyncpg://"):
        raw = raw.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    elif raw.startswith("postgres+asyncpg://"):
        raw = raw.replace("postgres+asyncpg://", "postgresql+psycopg://", 1)
    return raw


# ---------------------------------------------------------------------------
# Seed-Daten: deterministic_material_limits
# ---------------------------------------------------------------------------
# Fachliche Basis:
#   - Wellendichtring-Betriebsgrenzen nach DIN 3760:1996-02
#   - PTFE-Lippendichtung nach ISO 6194-1:2007
#   - Werte sind konservativ (kontinuierlicher Betrieb, Standardkompound)
#   - Abweichungen möglich je nach Hersteller/Compound — daher conditions_json-Hinweis
#
# limit_kind-Semantik im Query-Pfad:
#   'temperature'  → wird gefiltert: nur wenn min_value ≤ :temp ≤ max_value
#   'pressure'     → wird gefiltert: nur wenn min_value ≤ :pressure ≤ max_value
#   alles andere   → immer returned (kein numerischer Range-Filter im Query)

_SEED_DATE = date(2020, 1, 1)
_REVISION_DIN3760 = "DIN 3760:1996-02"
_REVISION_ISO6194 = "ISO 6194-1:2007"

MATERIAL_LIMITS_SEED: List[Dict[str, Any]] = [
    # -----------------------------------------------------------------------
    # FKM (Fluorelastomer / Viton) — Wellendichtring
    # Konservative Kontinuumsgrenzwerte für Standardkompound
    # -----------------------------------------------------------------------
    {
        "material": "FKM",
        "medium": None,
        "limit_kind": "temperature",
        "min_value": -20.0,
        "max_value": 200.0,
        "unit": "°C",
        "conditions_json": {
            "application": "Wellendichtring, kontinuierlicher Betrieb",
            "grade": "Standard-FKM",
            "note": "Kurzzeitspitzen bis +230°C je nach Compound möglich",
        },
        "source_ref": _REVISION_DIN3760,
        "revision": "1996-02",
        "version": 1,
        "effective_date": _SEED_DATE,
        "valid_until": None,
        "tenant_id": None,
    },
    {
        "material": "FKM",
        "medium": None,
        "limit_kind": "pressure",
        "min_value": 0.0,
        "max_value": 5.0,
        "unit": "bar",
        "conditions_json": {
            "application": "Wellendichtring, dynamisch",
            "note": "Statisch oder mit Druckentlastung höher möglich",
        },
        "source_ref": _REVISION_DIN3760,
        "revision": "1996-02",
        "version": 1,
        "effective_date": _SEED_DATE,
        "valid_until": None,
        "tenant_id": None,
    },
    {
        "material": "FKM",
        "medium": None,
        "limit_kind": "velocity",
        "min_value": 0.0,
        "max_value": 8.0,
        "unit": "m/s",
        "conditions_json": {
            "application": "Schleifgeschwindigkeit Wellendichtring, Standard-Lip",
            "note": "Hydrodynamische Ausführung bis 14 m/s je nach Hersteller",
        },
        "source_ref": _REVISION_DIN3760,
        "revision": "1996-02",
        "version": 1,
        "effective_date": _SEED_DATE,
        "valid_until": None,
        "tenant_id": None,
    },
    # -----------------------------------------------------------------------
    # NBR (Acrylnitril-Butadien-Kautschuk) — Wellendichtring
    # -----------------------------------------------------------------------
    {
        "material": "NBR",
        "medium": None,
        "limit_kind": "temperature",
        "min_value": -40.0,
        "max_value": 100.0,
        "unit": "°C",
        "conditions_json": {
            "application": "Wellendichtring, kontinuierlicher Betrieb",
            "grade": "Standard-NBR",
            "note": "Kurzzeitspitzen bis +120°C je nach ACN-Gehalt",
        },
        "source_ref": _REVISION_DIN3760,
        "revision": "1996-02",
        "version": 1,
        "effective_date": _SEED_DATE,
        "valid_until": None,
        "tenant_id": None,
    },
    {
        "material": "NBR",
        "medium": None,
        "limit_kind": "pressure",
        "min_value": 0.0,
        "max_value": 5.0,
        "unit": "bar",
        "conditions_json": {
            "application": "Wellendichtring, dynamisch",
        },
        "source_ref": _REVISION_DIN3760,
        "revision": "1996-02",
        "version": 1,
        "effective_date": _SEED_DATE,
        "valid_until": None,
        "tenant_id": None,
    },
    {
        "material": "NBR",
        "medium": None,
        "limit_kind": "velocity",
        "min_value": 0.0,
        "max_value": 4.0,
        "unit": "m/s",
        "conditions_json": {
            "application": "Schleifgeschwindigkeit Wellendichtring",
            "note": "Höherer Reibwert als FKM; mit Schmierung bis 7 m/s möglich",
        },
        "source_ref": _REVISION_DIN3760,
        "revision": "1996-02",
        "version": 1,
        "effective_date": _SEED_DATE,
        "valid_until": None,
        "tenant_id": None,
    },
    # -----------------------------------------------------------------------
    # PTFE (Polytetrafluorethylen) — Lippendichtung
    # ISO 6194-1 deckt PTFE-Lippendichtringe ab
    # -----------------------------------------------------------------------
    {
        "material": "PTFE",
        "medium": None,
        "limit_kind": "temperature",
        "min_value": -60.0,
        "max_value": 200.0,
        "unit": "°C",
        "conditions_json": {
            "application": "PTFE-Lippendichtung",
            "note": "Reines PTFE bis +260°C; für Lippendichtungsanwendung konservativ +200°C",
        },
        "source_ref": _REVISION_ISO6194,
        "revision": "2007",
        "version": 1,
        "effective_date": _SEED_DATE,
        "valid_until": None,
        "tenant_id": None,
    },
    {
        "material": "PTFE",
        "medium": None,
        "limit_kind": "pressure",
        "min_value": 0.0,
        "max_value": 70.0,
        "unit": "bar",
        "conditions_json": {
            "application": "PTFE-Lippendichtung, dynamisch",
        },
        "source_ref": _REVISION_ISO6194,
        "revision": "2007",
        "version": 1,
        "effective_date": _SEED_DATE,
        "valid_until": None,
        "tenant_id": None,
    },
    {
        "material": "PTFE",
        "medium": None,
        "limit_kind": "velocity",
        "min_value": 0.0,
        "max_value": 15.0,
        "unit": "m/s",
        "conditions_json": {
            "application": "PTFE-Lippendichtung, niedrige Reibung",
        },
        "source_ref": _REVISION_ISO6194,
        "revision": "2007",
        "version": 1,
        "effective_date": _SEED_DATE,
        "valid_until": None,
        "tenant_id": None,
    },
]

# ---------------------------------------------------------------------------
# Seed-Daten: deterministic_din_norms
# ---------------------------------------------------------------------------
# Nur DIN 3760 für FKM und NBR (Wellendichtringe).
# PTFE: DIN 3760 ist primär für Elastomere — PTFE-Lippendichtungen
# fallen unter ISO 6194-1. Im ersten Seed-Schnitt wird PTFE hier
# bewusst NICHT eingetragen (fachliche Lücke, kein Risiko).

DIN_NORMS_SEED: List[Dict[str, Any]] = [
    {
        "tenant_id": None,
        "norm_code": "DIN 3760",
        "material": "FKM",
        "medium": None,
        "pressure_min_bar": 0.0,
        "pressure_max_bar": 5.0,
        "temperature_min_c": -20.0,
        "temperature_max_c": 200.0,
        "payload_json": {
            "application": "Radial-Wellendichtringe",
            "shaft_speed_max_m_s": 8.0,
            "notes": "Standardauslegung, dynamisch, kontinuierlicher Betrieb",
        },
        "source_ref": _REVISION_DIN3760,
        "revision": "1996-02",
        "version": 1,
        "effective_date": _SEED_DATE,
        "valid_until": None,
    },
    {
        "tenant_id": None,
        "norm_code": "DIN 3760",
        "material": "NBR",
        "medium": None,
        "pressure_min_bar": 0.0,
        "pressure_max_bar": 5.0,
        "temperature_min_c": -40.0,
        "temperature_max_c": 100.0,
        "payload_json": {
            "application": "Radial-Wellendichtringe",
            "shaft_speed_max_m_s": 4.0,
            "notes": "Standardauslegung, dynamisch, kontinuierlicher Betrieb",
        },
        "source_ref": _REVISION_DIN3760,
        "revision": "1996-02",
        "version": 1,
        "effective_date": _SEED_DATE,
        "valid_until": None,
    },
]


# ---------------------------------------------------------------------------
# Idempotenz-Guards (SELECT-before-INSERT wegen NULL-Unique-Constraint)
# ---------------------------------------------------------------------------

_EXISTS_MATERIAL_LIMIT = text("""
    SELECT 1 FROM deterministic_material_limits
    WHERE tenant_id IS NULL
      AND lower(material) = lower(:material)
      AND limit_kind = :limit_kind
      AND version = :version
      AND effective_date = :effective_date
    LIMIT 1
""")

_INSERT_MATERIAL_LIMIT = text("""
    INSERT INTO deterministic_material_limits
        (tenant_id, material, medium, limit_kind,
         min_value, max_value, unit, conditions_json,
         source_ref, revision, version,
         effective_date, valid_until, is_active)
    VALUES
        (NULL, :material, :medium, :limit_kind,
         :min_value, :max_value, :unit, :conditions_json,
         :source_ref, :revision, :version,
         :effective_date, :valid_until, TRUE)
""")

_EXISTS_DIN_NORM = text("""
    SELECT 1 FROM deterministic_din_norms
    WHERE tenant_id IS NULL
      AND norm_code = :norm_code
      AND lower(material) = lower(:material)
      AND version = :version
      AND effective_date = :effective_date
    LIMIT 1
""")

_INSERT_DIN_NORM = text("""
    INSERT INTO deterministic_din_norms
        (tenant_id, norm_code, material, medium,
         pressure_min_bar, pressure_max_bar,
         temperature_min_c, temperature_max_c,
         payload_json, source_ref, revision, version,
         effective_date, valid_until, is_active)
    VALUES
        (NULL, :norm_code, :material, :medium,
         :pressure_min_bar, :pressure_max_bar,
         :temperature_min_c, :temperature_max_c,
         :payload_json, :source_ref, :revision, :version,
         :effective_date, :valid_until, TRUE)
""")


# ---------------------------------------------------------------------------
# Seed-Ausführung
# ---------------------------------------------------------------------------

def _seed_material_limits(session: Session) -> Dict[str, int]:
    inserted = 0
    skipped = 0
    import json

    for row in MATERIAL_LIMITS_SEED:
        exists = session.execute(
            _EXISTS_MATERIAL_LIMIT,
            {
                "material": row["material"],
                "limit_kind": row["limit_kind"],
                "version": row["version"],
                "effective_date": row["effective_date"],
            },
        ).fetchone()

        if exists:
            print(
                f"  SKIP  material_limits: {row['material']:6s} / {row['limit_kind']:15s} "
                f"(bereits vorhanden)"
            )
            skipped += 1
        else:
            session.execute(
                _INSERT_MATERIAL_LIMIT,
                {
                    "material": row["material"],
                    "medium": row.get("medium"),
                    "limit_kind": row["limit_kind"],
                    "min_value": row.get("min_value"),
                    "max_value": row.get("max_value"),
                    "unit": row.get("unit", ""),
                    "conditions_json": json.dumps(row.get("conditions_json") or {}),
                    "source_ref": row["source_ref"],
                    "revision": row.get("revision"),
                    "version": row["version"],
                    "effective_date": row["effective_date"],
                    "valid_until": row.get("valid_until"),
                },
            )
            print(
                f"  INSERT material_limits: {row['material']:6s} / {row['limit_kind']:15s} "
                f"[{row['source_ref']}]"
            )
            inserted += 1

    return {"inserted": inserted, "skipped": skipped}


def _seed_din_norms(session: Session) -> Dict[str, int]:
    inserted = 0
    skipped = 0
    import json

    for row in DIN_NORMS_SEED:
        exists = session.execute(
            _EXISTS_DIN_NORM,
            {
                "norm_code": row["norm_code"],
                "material": row["material"],
                "version": row["version"],
                "effective_date": row["effective_date"],
            },
        ).fetchone()

        if exists:
            print(
                f"  SKIP  din_norms:       {row['material']:6s} / {row['norm_code']:12s} "
                f"(bereits vorhanden)"
            )
            skipped += 1
        else:
            session.execute(
                _INSERT_DIN_NORM,
                {
                    "norm_code": row["norm_code"],
                    "material": row["material"],
                    "medium": row.get("medium"),
                    "pressure_min_bar": row.get("pressure_min_bar"),
                    "pressure_max_bar": row.get("pressure_max_bar"),
                    "temperature_min_c": row.get("temperature_min_c"),
                    "temperature_max_c": row.get("temperature_max_c"),
                    "payload_json": json.dumps(row.get("payload_json") or {}),
                    "source_ref": row["source_ref"],
                    "revision": row.get("revision"),
                    "version": row["version"],
                    "effective_date": row["effective_date"],
                    "valid_until": row.get("valid_until"),
                },
            )
            print(
                f"  INSERT din_norms:       {row['material']:6s} / {row['norm_code']:12s} "
                f"[{row['source_ref']}]"
            )
            inserted += 1

    return {"inserted": inserted, "skipped": skipped}


def run_seed(db_url: Optional[str] = None) -> None:
    url = db_url or _get_seed_url()
    print(f"\n=== Seed deterministic norms — DB: {url.split('@')[-1]} ===\n")

    engine = create_engine(url, future=True, pool_pre_ping=True)

    with Session(engine) as session:
        print("--- deterministic_material_limits ---")
        ml_stats = _seed_material_limits(session)

        print("\n--- deterministic_din_norms ---")
        dn_stats = _seed_din_norms(session)

        session.commit()

    print(
        f"\n=== Fertig ==="
        f"\n  material_limits : {ml_stats['inserted']} neu, {ml_stats['skipped']} übersprungen"
        f"\n  din_norms       : {dn_stats['inserted']} neu, {dn_stats['skipped']} übersprungen"
        f"\n"
    )


if __name__ == "__main__":
    run_seed()
