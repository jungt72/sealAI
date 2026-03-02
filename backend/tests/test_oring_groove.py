from __future__ import annotations

import os

os.environ.setdefault("postgres_user", "test")
os.environ.setdefault("postgres_password", "test")
os.environ.setdefault("postgres_host", "localhost")
os.environ.setdefault("postgres_port", "5432")
os.environ.setdefault("postgres_db", "testdb")
os.environ.setdefault("database_url", "postgresql+asyncpg://test:test@localhost:5432/testdb")
os.environ.setdefault("POSTGRES_SYNC_URL", "postgresql://test:test@localhost:5432/testdb")
os.environ.setdefault("openai_api_key", "sk-test")
os.environ.setdefault("qdrant_url", "http://localhost:6333")
os.environ.setdefault("qdrant_collection", "test")
os.environ.setdefault("redis_url", "redis://localhost:6379/0")
os.environ.setdefault("nextauth_url", "http://localhost")
os.environ.setdefault("nextauth_secret", "test")
os.environ.setdefault("keycloak_issuer", "http://localhost")
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_client_id", "test")
os.environ.setdefault("keycloak_client_secret", "test")
os.environ.setdefault("keycloak_expected_azp", "test")

from app.mcp.calculations.oring_groove import lookup_nut


def test_statisch_3_53():
    r = lookup_nut(3.53, "statisch", 50.0)
    assert r.schnurdurchmesser_mm == 3.53
    assert r.nuttiefe_mm == 2.70
    assert r.nutbreite_mm == 4.8
    assert r.empfohlene_shore == "70–80 Shore A"
    assert not r.backup_ring_empfohlen


def test_dynamisch_hoch_druck():
    r = lookup_nut(3.53, "dynamisch", 120.0)
    assert r.backup_ring_empfohlen  # > 100 bar
    assert r.empfohlene_shore == "80 Shore A"


def test_naechster_normwert():
    r = lookup_nut(3.0, "statisch", 10.0)
    assert r.schnurdurchmesser_mm == 2.62  # nächster
    assert "Eingabe 3.0" in r.hinweis


def test_druck_null_erlaubt():
    r = lookup_nut(2.62, "statisch", 0.0)
    assert r.empfohlene_shore == "70 Shore A"
    assert not r.backup_ring_empfohlen
