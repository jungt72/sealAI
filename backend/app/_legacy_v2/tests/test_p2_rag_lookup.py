"""Tests for P2 RAG Material-Lookup Node (Sprint 5)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


from app.services.rag.nodes.p2_rag_lookup import (
    _build_rag_query,
    _strip_unconfirmed_identity_fields,
    node_p2_rag_lookup,
)
from app.services.rag.state import WorkingProfile


def _make_state(**overrides):
    """Build a minimal SealAIState-like object for testing."""
    from app._legacy_v2.state import SealAIState

    defaults = {
        "conversation": {
            "messages": [],
            "user_id": "test-user",
            "thread_id": "test-thread",
        },
        "system": {
            "run_id": "test-run",
        },
    }

    for key, value in overrides.items():
        if isinstance(defaults.get(key), dict) and isinstance(value, dict):
            merged = dict(defaults[key])
            merged.update(value)
            defaults[key] = merged
        else:
            defaults[key] = value
    return SealAIState(**defaults)


class TestBuildRagQuery:
    def test_empty_profile(self):
        profile = WorkingProfile()
        query = _build_rag_query(profile)
        assert query == "Dichtungswerkstoff"

    def test_full_profile(self):
        # Semantic-only guard: deterministic fields (pressure, temperature,
        # flange_standard, emission_class) must NOT reach Qdrant.
        profile = WorkingProfile(
            medium="Dampf",
            medium_detail="gesättigter Dampf",
            pressure_max_bar=150.0,
            temperature_max_c=400.0,
            flange_standard="EN 1092-1",
            flange_dn=100,
            flange_pn=40,
            emission_class="TA-Luft",
            industry_sector="Petrochemie",
        )
        query = _build_rag_query(profile)
        # semantic fields remain
        assert "Dampf" in query
        assert "gesättigter Dampf" in query
        assert "Petrochemie" in query
        # deterministic fields must be absent → go to SQL only
        assert "150.0 bar" not in query
        assert "400.0°C" not in query
        assert "EN 1092-1" not in query
        assert "TA-Luft" not in query

    def test_partial_profile_pressure_only(self):
        # pressure_max_bar is a deterministic SQL field — must not appear in Qdrant query
        profile = WorkingProfile(pressure_max_bar=50.0)
        query = _build_rag_query(profile)
        assert "50.0 bar" not in query
        assert "°C" not in query
        assert query == "Dichtungswerkstoff"

    def test_profile_with_material_and_product(self):
        profile = WorkingProfile(material="Kyrolon", product_name="Gylon")
        query = _build_rag_query(profile)
        assert "Werkstoff Kyrolon" in query
        assert "Produkt Gylon" in query


@pytest.mark.anyio
@patch("app.services.rag.nodes.p2_rag_lookup.rag_cache.get", return_value=None)
class TestNodeP2RagLookup:
    async def test_sparse_profile_skips_rag(self, mock_cache_get):
        """Coverage < 0.2 → skip RAG, return minimal state."""
        state = _make_state(working_profile=WorkingProfile())
        result = await node_p2_rag_lookup(state)
        assert "context" not in result  # no RAG context
        assert "sources" not in result

    @patch("app.services.rag.nodes.p2_rag_lookup.search_technical_docs")
    async def test_sparse_profile_bypass_with_material(self, mock_search, mock_cache_get):
        """Profile contains 'material' → bypass sparse check."""
        mock_search.return_value = {"hits": [], "context": "found something", "retrieval_meta": {}}
        profile = WorkingProfile(material="Kyrolon")
        # Coverage is 1/17 ~ 0.058 (well below 0.2)
        state = _make_state(working_profile={"engineering_profile": profile})
        result = await node_p2_rag_lookup(state)
        mock_search.assert_called_once()
        assert result["reasoning"]["context"] == "found something"

    @patch("app.services.rag.nodes.p2_rag_lookup.search_technical_docs")
    async def test_sparse_profile_bypass_with_knowledge_intent(self, mock_search, mock_cache_get):
        """Intent is 'explanation_or_comparison' → bypass sparse check."""
        mock_search.return_value = {"hits": [], "context": "found something", "retrieval_meta": {}}
        from app._legacy_v2.state import Intent
        state = _make_state(
            working_profile={"engineering_profile": WorkingProfile()},
            conversation={"intent": Intent(goal="explanation_or_comparison")}
        )
        result = await node_p2_rag_lookup(state)
        mock_search.assert_called_once()
        assert result["reasoning"]["context"] == "found something"

    async def test_no_profile_skips_rag(self, mock_cache_get):
        state = _make_state(working_profile=None)
        result = await node_p2_rag_lookup(state)
        assert "context" not in result.get("reasoning", {})

    @patch("app.services.rag.nodes.p2_rag_lookup.search_technical_docs")
    async def test_filled_profile_calls_rag(self, mock_search, mock_cache_get):
        mock_search.return_value = {
            "hits": [
                {
                    "text": "NBR 70 Shore A — geeignet für Dampf bis 180°C",
                    "source": "material_catalog.pdf",
                    "vector_score": 0.85,
                    "metadata": {"page": 12},
                }
            ],
            "context": "NBR 70 Shore A für Dampfanwendungen",
            "retrieval_meta": {"k_returned": 1, "top_scores": [0.85]},
        }
        profile = WorkingProfile(
            medium="Dampf",
            pressure_max_bar=10.0,
            temperature_max_c=180.0,
            flange_standard="EN 1092-1",
            flange_dn=50,
        )
        state = _make_state(working_profile={"engineering_profile": profile})
        result = await node_p2_rag_lookup(state)

        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args
        assert call_kwargs.kwargs.get("tenant_id") == "test-user" or call_kwargs[1].get("tenant_id") == "test-user"

        assert len(result["system"]["sources"]) == 1
        assert result["system"]["sources"][0].source == "material_catalog.pdf"
        assert "NBR 70" in result["reasoning"]["context"]
        assert result["reasoning"]["working_memory"].panel_material["source"] == "p2_rag_lookup"

    @patch("app.services.rag.nodes.p2_rag_lookup.search_technical_docs")
    async def test_rag_failure_graceful(self, mock_search, mock_cache_get):
        mock_search.side_effect = RuntimeError("Qdrant timeout")
        profile = WorkingProfile(
            medium="Dampf",
            pressure_max_bar=10.0,
            temperature_max_c=180.0,
            flange_standard="EN 1092-1",
            flange_dn=50,
        )
        state = _make_state(working_profile={"engineering_profile": profile})
        result = await node_p2_rag_lookup(state)

        retrieval_meta = result.get("reasoning", {}).get("retrieval_meta", {})
        assert "error" in str(retrieval_meta).lower() or "RuntimeError" in str(retrieval_meta)


# ---------------------------------------------------------------------------
# Pre-RAG identity gate — _strip_unconfirmed_identity_fields
# ---------------------------------------------------------------------------


class TestStripUnconfirmedIdentityFields:
    """Identity-guarded fields with non-confirmed identity_class must be blanked."""

    def test_confirmed_medium_passes_through(self):
        profile = WorkingProfile(medium="Dampf", pressure_max_bar=10.0)
        identity_map = {"medium": {"identity_class": "identity_confirmed", "lookup_allowed": True}}
        safe = _strip_unconfirmed_identity_fields(profile, identity_map)
        assert safe.medium == "Dampf"
        assert safe.pressure_max_bar == 10.0

    def test_family_only_material_stripped(self):
        profile = WorkingProfile(material="PTFE", medium="Wasser")
        identity_map = {
            "material": {"identity_class": "identity_family_only", "lookup_allowed": False},
            "medium": {"identity_class": "identity_confirmed", "lookup_allowed": True},
        }
        safe = _strip_unconfirmed_identity_fields(profile, identity_map)
        assert safe.material is None, "family_only material must be stripped"
        assert safe.medium == "Wasser", "confirmed medium must survive"

    def test_probable_product_name_stripped(self):
        profile = WorkingProfile(product_name="Kyrolon")
        identity_map = {"product_name": {"identity_class": "identity_probable"}}
        safe = _strip_unconfirmed_identity_fields(profile, identity_map)
        assert safe.product_name is None

    def test_unresolved_trade_name_stripped(self):
        profile = WorkingProfile(material="FKM")
        identity_map = {"material": {"identity_class": "identity_unresolved"}}
        safe = _strip_unconfirmed_identity_fields(profile, identity_map)
        assert safe.material is None

    def test_numeric_fields_unaffected(self):
        """Non-identity fields (pressure, temperature) must never be stripped."""
        profile = WorkingProfile(pressure_max_bar=250.0, temperature_max_c=400.0, material="NBR")
        identity_map = {"material": {"identity_class": "identity_family_only"}}
        safe = _strip_unconfirmed_identity_fields(profile, identity_map)
        assert safe.pressure_max_bar == 250.0
        assert safe.temperature_max_c == 400.0
        assert safe.material is None

    def test_no_identity_map_passes_all(self):
        """When no identity map exists (legacy path), all fields pass through."""
        profile = WorkingProfile(medium="Dampf", material="FKM")
        safe = _strip_unconfirmed_identity_fields(profile, None)
        assert safe.medium == "Dampf"
        assert safe.material == "FKM"

    def test_missing_identity_record_passes_field(self):
        """Field present in profile but absent from identity_map → passes through (legacy safe)."""
        profile = WorkingProfile(medium="Dampf", material="NBR")
        identity_map = {"medium": {"identity_class": "identity_confirmed"}}
        safe = _strip_unconfirmed_identity_fields(profile, identity_map)
        assert safe.medium == "Dampf"
        assert safe.material == "NBR", "no identity record → field must pass"


class TestIdentityGateInQueryBuilder:
    """Verify stripped fields don't leak into _build_rag_query output."""

    def test_family_only_material_absent_from_query(self):
        profile = WorkingProfile(material="PTFE", medium="Wasser")
        identity_map = {
            "material": {"identity_class": "identity_family_only"},
            "medium": {"identity_class": "identity_confirmed"},
        }
        safe = _strip_unconfirmed_identity_fields(profile, identity_map)
        query = _build_rag_query(safe)
        assert "PTFE" not in query, "family_only material must not reach query"
        assert "Wasser" in query, "confirmed medium must be in query"

    def test_probable_product_absent_from_query(self):
        profile = WorkingProfile(product_name="Kyrolon", medium="Dampf")
        identity_map = {
            "product_name": {"identity_class": "identity_probable"},
            "medium": {"identity_class": "identity_confirmed"},
        }
        safe = _strip_unconfirmed_identity_fields(profile, identity_map)
        query = _build_rag_query(safe)
        assert "Kyrolon" not in query
        assert "Dampf" in query


@pytest.mark.anyio
@patch("app.services.rag.nodes.p2_rag_lookup.rag_cache.get", return_value=None)
class TestIdentityGateIntegration:
    """End-to-end: unconfirmed fields must not trigger has_high_signal bypass."""

    async def test_family_only_material_no_bypass(self, mock_cache_get):
        """Profile with only family_only material should NOT bypass sparse check."""
        profile = WorkingProfile(material="PTFE")
        state = _make_state(
            working_profile={"engineering_profile": profile},
            reasoning={"extracted_parameter_identity": {
                "material": {"identity_class": "identity_family_only", "lookup_allowed": False},
            }},
        )
        result = await node_p2_rag_lookup(state)
        # With only a family_only material and nothing else, coverage < 0.2
        # and has_high_signal_fields is False → should skip RAG
        assert "context" not in result.get("reasoning", {})

    @patch("app.services.rag.nodes.p2_rag_lookup.search_technical_docs")
    async def test_confirmed_medium_triggers_bypass(self, mock_search, mock_cache_get):
        """Profile with confirmed medium should bypass sparse check and call RAG."""
        mock_search.return_value = {"hits": [], "context": "result", "retrieval_meta": {}}
        profile = WorkingProfile(medium="Dampf")
        state = _make_state(
            working_profile={"engineering_profile": profile},
            reasoning={"extracted_parameter_identity": {
                "medium": {"identity_class": "identity_confirmed", "lookup_allowed": True},
            }},
        )
        result = await node_p2_rag_lookup(state)
        mock_search.assert_called_once()
        assert result["reasoning"]["context"] == "result"
