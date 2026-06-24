"""In-process Fachkarten retriever — grounds the eval's hot material-compat pairs, stays quiet
elsewhere (vorläufig), and enforces tenant scope (P0)."""

from __future__ import annotations

import asyncio

import pytest

from sealai_v2.knowledge.fachkarten import Claim, Fachkarte, FachkartenCatalog
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


def _mixed_catalog() -> FachkartenCatalog:
    # one card carrying BOTH a reviewed and a draft claim → exercises both _quelle branches
    card = Fachkarte(
        id="FK-QTEST",
        scope={"material": ["epdm"], "medium": ["mineraloel"]},  # ≥2 tags → retrieves
        claims=(
            Claim(
                text="EPDM is reviewed-grounded here.",
                review_state="reviewed",
                provenance=("owner:qtest",),
            ),
            Claim(
                text="EPDM draft note, unverified.",
                review_state="draft",
                provenance=("cc-draft:qtest",),
            ),
        ),
        review_state="reviewed",
        provenance=("owner:qtest",),
    )
    return FachkartenCatalog(cards=(card,))


def test_quelle_labels_reviewed_vs_draft_distinctly():
    # P3a — a draft claim must NOT be cited as "(reviewed; …)". Reviewed → "reviewed";
    # draft → "draft — vorläufig, gegen Hersteller verifizieren" (mirrors versagensmodi.quelle()).
    # query tokens must contain the scope tags verbatim — the in-process retriever is plain
    # substring match (_score), so use the tag spellings "epdm" + "mineraloel".
    res = asyncio.run(
        InProcessRetriever(_mixed_catalog()).retrieve("epdm mineraloel", tenant_id="t")
    )
    assert len(res.grounding_facts) == 1 and len(res.provisional) == 1
    reviewed_q = res.grounding_facts[0].quelle
    draft_q = res.provisional[0].quelle
    # reviewed citation says "reviewed" and is NOT mislabelled draft/vorläufig
    assert "reviewed" in reviewed_q
    assert "vorläufig" not in reviewed_q and "draft" not in reviewed_q
    # draft citation says draft/vorläufig and is NOT the old hardcoded "reviewed"
    assert "draft" in draft_q and "vorläufig" in draft_q
    assert "reviewed" not in draft_q
