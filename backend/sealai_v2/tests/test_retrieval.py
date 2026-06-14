"""In-process Fachkarten retriever — grounds the eval's hot material-compat pairs, stays quiet
elsewhere (vorläufig), and enforces tenant scope (P0)."""

from __future__ import annotations

import asyncio

import pytest

from sealai_v2.knowledge.retrieval import InProcessRetriever


def _r() -> InProcessRetriever:
    return InProcessRetriever()


def test_grounds_epdm_mineraloel():
    res = asyncio.run(
        _r().retrieve(
            "EPDM-O-Ringe quellen in unserem Hydrauliköl, woran liegt das?",
            tenant_id="t",
        )
    )
    assert res.grounded
    assert "FK-EPDM-MINERALOEL" in {f.card_id for f in res.grounding_facts}
    assert all(f.text and f.card_id for f in res.grounding_facts)


def test_grounds_fkm_dampf():
    res = asyncio.run(
        _r().retrieve("FKM für Heißdampf-Sterilisation bei 140 °C", tenant_id="t")
    )
    assert "FK-FKM-DAMPF" in {f.card_id for f in res.grounding_facts}


def test_grounds_foodgrade_over_plain_epdm():
    res = asyncio.run(
        _r().retrieve(
            "lebensmittelechte Dichtung für eine Schokoladen-Anlage, EPDM food-grade?",
            tenant_id="t",
        )
    )
    assert "FK-FOODGRADE-FETT" in {f.card_id for f in res.grounding_facts}


def test_offtopic_is_vorlaeufig():
    res = asyncio.run(
        _r().retrieve(
            "Welchen Elektromotor nehme ich für mein Rührwerk?", tenant_id="t"
        )
    )
    assert not res.grounded
    assert res.grounding_facts == ()


def test_tenant_is_mandatory_p0():
    for bad in ("", "   "):
        with pytest.raises(ValueError):
            asyncio.run(_r().retrieve("EPDM Hydrauliköl", tenant_id=bad))
