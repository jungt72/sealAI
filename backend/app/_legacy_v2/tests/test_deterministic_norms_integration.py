"""
Integration-Tests: deterministic_norms SQL-Pfad gegen echte DB
===============================================================

Setzt voraus:
  - Tabellen deterministic_din_norms + deterministic_material_limits existieren
  - Seed wurde ausgeführt (seed_deterministic_norms.py)
  - POSTGRES_SYNC_URL oder DATABASE_URL gesetzt (im Container automatisch)

Marker: @pytest.mark.integration
Überspringt graceful wenn keine DB-Verbindung möglich.
"""

from __future__ import annotations

import os
import pytest
from sqlalchemy import create_engine


# ---------------------------------------------------------------------------
# Real DB URL — liest direkt aus ENV, ignoriert conftest-Stub
# ---------------------------------------------------------------------------

def _real_db_url() -> str | None:
    """
    Liest Postgres-URL direkt aus ENV (nicht aus gestubtem app.core.config).
    Gibt None zurück wenn keine echte (nicht-localhost) URL vorhanden.
    """
    url = (os.environ.get("POSTGRES_SYNC_URL") or os.environ.get("DATABASE_URL") or "").strip()
    if not url or "localhost" in url:
        return None
    # asyncpg→psycopg rewrite (spiegelt knowledge_tool._resolve_sync_postgres_url)
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    elif url.startswith("postgres+asyncpg://"):
        url = url.replace("postgres+asyncpg://", "postgresql+psycopg://", 1)
    return url


_REAL_DB_URL = _real_db_url()
_skip_no_db = pytest.mark.skipif(
    _REAL_DB_URL is None,
    reason="Keine echte DB-URL gesetzt (POSTGRES_SYNC_URL zeigt auf localhost oder fehlt)",
)


@pytest.fixture(autouse=True)
def _inject_real_engine(request):
    """
    Ersetzt für Integration-Tests den gecachten lru_cache-Engine in knowledge_tool
    durch einen Engine der auf die echte DB (aus ENV) zeigt.
    Stellt nach dem Test den ursprünglichen Zustand wieder her.
    """
    if _REAL_DB_URL is None:
        yield
        return

    import app.mcp.knowledge_tool as kt

    real_engine = create_engine(_REAL_DB_URL, future=True, pool_pre_ping=True)
    original_fn = kt._get_sync_engine

    # Lru_cache leeren und durch Real-Engine ersetzen
    kt._get_sync_engine.cache_clear()
    kt._get_sync_engine = lambda: real_engine  # type: ignore[assignment]

    yield

    # Restore: Original-Funktion zurücksetzen, Cache leeren
    kt._get_sync_engine = original_fn  # type: ignore[assignment]
    try:
        original_fn.cache_clear()
    except AttributeError:
        pass


def _run_query(material: str, temp: float, pressure: float):
    from app.mcp.knowledge_tool import query_deterministic_norms
    return query_deterministic_norms(material=material, temp=temp, pressure=pressure)


# ---------------------------------------------------------------------------
# Tests: Tabellen existieren
# ---------------------------------------------------------------------------

@pytest.mark.integration
@_skip_no_db
def test_tables_exist() -> None:
    """Beide Tabellen müssen nach Migration vorhanden sein."""
    from app.mcp.knowledge_tool import _get_sync_engine
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    engine = _get_sync_engine()
    with Session(engine) as session:
        result = session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' "
                "AND table_name IN ('deterministic_din_norms', 'deterministic_material_limits') "
                "ORDER BY table_name"
            )
        )
        tables = [row[0] for row in result]

    assert "deterministic_din_norms" in tables, "Tabelle deterministic_din_norms fehlt"
    assert "deterministic_material_limits" in tables, "Tabelle deterministic_material_limits fehlt"


# ---------------------------------------------------------------------------
# Tests: Kein SQL-Error — Minimalanforderung
# ---------------------------------------------------------------------------

@pytest.mark.integration
@_skip_no_db
@pytest.mark.parametrize("material,temp,pressure", [
    ("FKM", 80.0, 3.0),
    ("NBR", 60.0, 2.0),
    ("PTFE", 100.0, 10.0),
    ("UNKNOWNMATERIAL", 25.0, 1.0),
])
def test_no_sql_error_for_any_material(material: str, temp: float, pressure: float) -> None:
    """Query darf für kein Material einen SQL-Error werfen."""
    result = _run_query(material, temp, pressure)
    assert result["status"] in ("ok", "no_match"), (
        f"Unerwarteter Status '{result['status']}' für {material}: "
        f"{result.get('retrieval_meta', {}).get('error', '')}"
    )


# ---------------------------------------------------------------------------
# Tests: Seeded Materialien liefern 'ok'
# ---------------------------------------------------------------------------

@pytest.mark.integration
@_skip_no_db
def test_fkm_typical_conditions_ok() -> None:
    """FKM bei 80°C / 3 bar → muss 'ok' liefern (temp + pressure + velocity match)."""
    result = _run_query("FKM", 80.0, 3.0)
    assert result["status"] == "ok", (
        f"FKM typisch: erwartet 'ok', bekam '{result['status']}'. "
        f"Seed möglicherweise nicht ausgeführt."
    )
    # velocity-Zeile immer present (limit_kind NOT IN temperature/pressure)
    limits = result["matches"]["material_limits"]
    velocity_rows = [r for r in limits if r["limit_kind"] == "velocity"]
    assert len(velocity_rows) >= 1, "velocity-Zeile für FKM fehlt in material_limits"


@pytest.mark.integration
@_skip_no_db
def test_nbr_typical_conditions_ok() -> None:
    """NBR bei 60°C / 2 bar → muss 'ok' liefern."""
    result = _run_query("NBR", 60.0, 2.0)
    assert result["status"] == "ok", (
        f"NBR typisch: erwartet 'ok', bekam '{result['status']}'."
    )


@pytest.mark.integration
@_skip_no_db
def test_ptfe_typical_conditions_ok() -> None:
    """PTFE bei 100°C / 10 bar → muss 'ok' liefern."""
    result = _run_query("PTFE", 100.0, 10.0)
    assert result["status"] == "ok", (
        f"PTFE typisch: erwartet 'ok', bekam '{result['status']}'."
    )


@pytest.mark.integration
@_skip_no_db
def test_material_case_insensitive() -> None:
    """Query normalisiert material auf lower() — 'fkm' muss identisch zu 'FKM' liefern."""
    result_upper = _run_query("FKM", 80.0, 3.0)
    result_lower = _run_query("fkm", 80.0, 3.0)
    assert result_upper["status"] == result_lower["status"], (
        "Case-Sensitivity-Problem: 'FKM' und 'fkm' liefern unterschiedliche Status"
    )


# ---------------------------------------------------------------------------
# Tests: Nicht-seeded Material bleibt 'no_match'
# ---------------------------------------------------------------------------

@pytest.mark.integration
@_skip_no_db
def test_unknown_material_no_match() -> None:
    """Nicht-geseedetes Material muss 'no_match' liefern, keinen Error."""
    result = _run_query("SILIKON_UNBEKANNT_XYZ", 25.0, 1.0)
    assert result["status"] == "no_match", (
        f"Erwartet 'no_match' für unbekanntes Material, bekam '{result['status']}'"
    )


# ---------------------------------------------------------------------------
# Tests: Grenzwerte der temperature-Limits
# ---------------------------------------------------------------------------

@pytest.mark.integration
@_skip_no_db
def test_fkm_temperature_within_limit_ok() -> None:
    """FKM bei 200°C (Obergrenze) → temperature-Limit sollte noch matchen."""
    result = _run_query("FKM", 200.0, 3.0)
    assert result["status"] == "ok"
    limits = result["matches"]["material_limits"]
    temp_rows = [r for r in limits if r["limit_kind"] == "temperature"]
    assert len(temp_rows) >= 1, "temperature-Zeile für FKM bei 200°C erwartet"


@pytest.mark.integration
@_skip_no_db
def test_fkm_temperature_exceeds_limit_velocity_still_matches() -> None:
    """
    FKM bei 250°C (über 200°C Limit) → temperature-Limit matcht nicht,
    aber velocity-Limit (limit_kind='velocity') matcht immer → Status 'ok'.
    """
    result = _run_query("FKM", 250.0, 3.0)
    assert result["status"] == "ok", (
        "Erwartet 'ok' weil velocity-Limit unabhängig von Temp/Pressure matcht"
    )
    limits = result["matches"]["material_limits"]
    temp_rows = [r for r in limits if r["limit_kind"] == "temperature"]
    velocity_rows = [r for r in limits if r["limit_kind"] == "velocity"]
    # temperature-Zeile darf bei 250°C NICHT present sein (200°C Obergrenze)
    assert len(temp_rows) == 0, (
        f"temperature-Zeile für FKM bei 250°C sollte nicht matchen, "
        f"aber {len(temp_rows)} Treffer: {temp_rows}"
    )
    assert len(velocity_rows) >= 1, "velocity-Zeile für FKM muss always vorhanden sein"


@pytest.mark.integration
@_skip_no_db
def test_nbr_temperature_exceeds_limit() -> None:
    """NBR bei 120°C (über 100°C Grenzwert) → temperature-Zeile matcht nicht."""
    result = _run_query("NBR", 120.0, 2.0)
    # Status kann 'ok' sein wegen velocity-Rows
    limits = result["matches"]["material_limits"]
    temp_rows = [r for r in limits if r["limit_kind"] == "temperature"]
    assert len(temp_rows) == 0, (
        f"NBR temperature-Limit bei 120°C sollte nicht matchen (max=100°C), "
        f"aber {len(temp_rows)} Treffer"
    )


# ---------------------------------------------------------------------------
# Tests: DIN Norm Matches
# ---------------------------------------------------------------------------

@pytest.mark.integration
@_skip_no_db
def test_fkm_din_norm_match() -> None:
    """FKM Wellendichtring-Betriebspunkt → DIN 3760 Norm-Treffer erwartet."""
    result = _run_query("FKM", 80.0, 3.0)
    assert result["status"] == "ok"
    din_norms = result["matches"]["din_norms"]
    din3760 = [r for r in din_norms if r["norm_code"] == "DIN 3760"]
    assert len(din3760) >= 1, (
        f"DIN 3760 Treffer für FKM erwartet, bekam: {din_norms}"
    )
    assert din3760[0]["source_ref"] == "DIN 3760:1996-02"


@pytest.mark.integration
@_skip_no_db
def test_nbr_din_norm_match() -> None:
    """NBR Wellendichtring-Betriebspunkt → DIN 3760 Norm-Treffer erwartet."""
    result = _run_query("NBR", 60.0, 2.0)
    assert result["status"] == "ok"
    din_norms = result["matches"]["din_norms"]
    din3760 = [r for r in din_norms if r["norm_code"] == "DIN 3760"]
    assert len(din3760) >= 1, f"DIN 3760 für NBR erwartet, bekam: {din_norms}"


@pytest.mark.integration
@_skip_no_db
def test_fkm_pressure_exceeds_din_norm() -> None:
    """FKM bei 50 bar (weit über 5 bar DIN 3760 Grenzwert) → kein DIN-Norm-Treffer."""
    result = _run_query("FKM", 80.0, 50.0)
    # Status kann trotzdem 'ok' sein (material_limits velocity-Row matcht)
    din_norms = result["matches"]["din_norms"]
    # pressure_max_bar=5 → 50 > 5 → DIN 3760 matcht nicht
    din3760 = [r for r in din_norms if r["norm_code"] == "DIN 3760"]
    assert len(din3760) == 0, (
        f"DIN 3760 sollte bei 50 bar nicht matchen (max=5 bar), "
        f"aber {len(din3760)} Treffer: {din3760}"
    )


# ---------------------------------------------------------------------------
# Tests: Payload-Inhalt
# ---------------------------------------------------------------------------

@pytest.mark.integration
@_skip_no_db
def test_result_structure_complete() -> None:
    """Ergebnis-Struktur muss alle erwarteten Schlüssel enthalten."""
    result = _run_query("FKM", 80.0, 3.0)
    assert "tool" in result
    assert "status" in result
    assert "matches" in result
    assert "din_norms" in result["matches"]
    assert "material_limits" in result["matches"]
    assert "retrieval_meta" in result
    assert result["retrieval_meta"]["mode"] == "exact_range_sql"
    assert result["retrieval_meta"]["source"] == "postgresql"


@pytest.mark.integration
@_skip_no_db
def test_material_limit_row_fields_present() -> None:
    """Jede material_limits-Zeile muss alle Felder haben."""
    result = _run_query("FKM", 80.0, 3.0)
    for row in result["matches"]["material_limits"]:
        assert "material" in row
        assert "limit_kind" in row
        assert "source_ref" in row
        assert "version" in row
        assert row["version"] >= 1


@pytest.mark.integration
@_skip_no_db
def test_din_norm_row_fields_present() -> None:
    """Jede din_norms-Zeile muss alle Felder haben."""
    result = _run_query("FKM", 80.0, 3.0)
    for row in result["matches"]["din_norms"]:
        assert "norm_code" in row
        assert "material" in row
        assert "source_ref" in row
        assert row["norm_code"] == "DIN 3760"
