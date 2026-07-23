"""In-process Fachkarten retriever — grounds the eval's hot material-compat pairs, stays quiet
elsewhere (vorläufig), and enforces tenant scope (P0)."""

from __future__ import annotations

import asyncio

import pytest

from sealai_v2.knowledge.fachkarten import Claim, Fachkarte, FachkartenCatalog
from sealai_v2.knowledge.retrieval import (
    InProcessRetriever,
    _card_severity,
    _retrieval_concepts,
    _score,
)
from sealai_v2.tests.reviewed_catalog import independently_reviewed_test_catalog


def _r() -> InProcessRetriever:
    return InProcessRetriever(independently_reviewed_test_catalog())


def test_owner_attested_epdm_mineraloel_claim_is_grounding():
    res = asyncio.run(
        _r().retrieve(
            "EPDM-O-Ringe quellen in unserem Hydrauliköl, woran liegt das?",
            tenant_id="t",
        )
    )
    facts = [f for f in res.grounding_facts if f.card_id == "FK-EPDM-MINERALOEL"]
    assert facts
    assert all("owner domain-expert attestation" in f.sources[0] for f in facts)


def test_owner_attested_fkm_dampf_claim_is_grounding():
    res = asyncio.run(
        _r().retrieve("FKM für Heißdampf-Sterilisation bei 140 °C", tenant_id="t")
    )
    facts = [f for f in res.grounding_facts if f.card_id == "FK-FKM-DAMPF"]
    assert facts
    assert all("owner domain-expert attestation" in f.sources[0] for f in facts)


def test_broad_ptfe_overview_is_grounded_with_one_explicit_material_scope_hit():
    res = asyncio.run(_r().retrieve("Bitte gib mir Details zu PTFE.", tenant_id="t"))

    ptfe = [f for f in res.grounding_facts if f.card_id == "FK-PTFE-KALTFLUSS"]
    assert len(ptfe) >= 5
    assert any("thermoplast" in fact.text.lower() for fact in ptfe)
    assert any("füllstoff" in fact.text.lower() for fact in ptfe)


def test_bare_material_name_is_an_overview_request():
    res = asyncio.run(_r().retrieve("PTFE", tenant_id="t"))

    assert "FK-PTFE-KALTFLUSS" in {f.card_id for f in res.grounding_facts}


def test_overview_prefers_a_reviewed_material_card_over_draft_only_ties():
    reviewed = _card("FK-REVIEWED", "definition", material="ptfe", medium="unused")
    draft = Fachkarte(
        id="FK-DRAFT-SAFETY",
        scope={"material": ["ptfe"]},
        claims=(
            Claim(
                text="draft-only safety note",
                review_state="draft",
                provenance=("draft:x",),
                kind="safety_nogo",
            ),
        ),
        review_state="draft",
        provenance=("draft:x",),
    )
    res = asyncio.run(
        InProcessRetriever(FachkartenCatalog(cards=(draft, reviewed))).retrieve(
            "Details zu PTFE", tenant_id="t", k=1
        )
    )

    assert {fact.card_id for fact in res.grounding_facts} == {"FK-REVIEWED"}


def test_owner_attested_foodgrade_claims_are_grounding():
    res = asyncio.run(
        _r().retrieve(
            "lebensmittelechte Dichtung für eine Schokoladen-Anlage, EPDM food-grade?",
            tenant_id="t",
        )
    )
    facts = [f for f in res.grounding_facts if f.card_id == "FK-FOODGRADE-FETT"]
    assert facts
    assert all("owner domain-expert attestation" in f.sources[0] for f in facts)


def test_exact_medium_hit_does_not_pull_unrelated_lexical_cards():
    res = asyncio.run(
        _r().retrieve(
            "Welche möglichst günstige Dichtung für Aceton bei 180 °C?",
            tenant_id="t",
        )
    )

    assert {f.card_id for f in res.grounding_facts} == {"FK-FKM-AMIN-LAUGE-KETON"}


def test_rwdr_case_keeps_seal_profile_when_nbr_is_also_named():
    res = asyncio.run(
        _r().retrieve(
            "RWDR 40x62x8 NBR bei 6000 U/min, Temperatur noch unbekannt",
            tenant_id="t",
        )
    )

    assert "FK-RWDR-ENGINEERING-PROFILE" in {
        fact.card_id for fact in res.grounding_facts
    }


def test_focused_oring_failure_keeps_case_evidence_and_adds_profile():
    res = asyncio.run(
        _r().retrieve(
            "NBR O-Ring ist der Witterung ausgesetzt und reißt. Was tun?",
            tenant_id="t",
            k=5,
        )
    )

    card_ids = [fact.card_id for fact in res.grounding_facts]
    assert "FK-NBR-OZON" in card_ids
    assert "FK-ORING-ENGINEERING-PROFILE" in card_ids
    assert card_ids.index("FK-NBR-OZON") < card_ids.index(
        "FK-ORING-ENGINEERING-PROFILE"
    )


@pytest.mark.parametrize(
    "query,expected_card",
    [
        (
            "Der NBR-Ring draußen zeigt nach Sonne und Wetter feine Risse.",
            "FK-NBR-OZON",
        ),
        (
            "Kann ein Silikonring auf einer schnell rotierenden Welle laufen?",
            "FK-VMQ-DYNAMISCH",
        ),
        (
            "PTFE verliert nach langer Standzeit seine Vorspannung.",
            "FK-PTFE-KALTFLUSS",
        ),
    ],
)
def test_controlled_engineering_concepts_generalize_beyond_eval_wording(
    query, expected_card
):
    res = asyncio.run(_r().retrieve(query, tenant_id="t", k=5))
    assert expected_card in {fact.card_id for fact in res.grounding_facts}


def test_semantic_scope_aliases_count_as_one_card_signal():
    profile = Fachkarte(
        id="FK-PROFILE",
        scope={
            "application": [
                "Wellendichtung",
                "Radialwellendichtring",
                "RWDR",
                "Simmerring",
                "Dichtlippe",
            ]
        },
        claims=(),
        review_state="draft",
        provenance=("test",),
    )

    # One literal tag plus one inferred concept; the four aliases do not add four more points.
    assert _score(profile, "Wie funktioniert eine Wellendichtung?") == 2


def test_claims_are_interleaved_across_equally_ranked_cards():
    def card(card_id: str) -> Fachkarte:
        return Fachkarte(
            id=card_id,
            scope={"material": ["NBR"], "medium": ["Getriebeöl"]},
            claims=tuple(
                Claim(
                    text=f"{card_id} claim {index}",
                    review_state="reviewed",
                    sources=("test-source",),
                    provenance=("owner:test",),
                    reviewed_by="test-domain-reviewer",
                    reviewed_at="2026-07-11T00:00:00Z",
                    review_expires_at="2099-07-11T00:00:00Z",
                )
                for index in range(3)
            ),
            review_state="reviewed",
            provenance=("owner:test",),
        )

    res = asyncio.run(
        InProcessRetriever(FachkartenCatalog(cards=(card("FK-A"), card("FK-B")))).retrieve(
            "NBR in Getriebeöl", tenant_id="t", k=2
        )
    )

    assert [fact.card_id for fact in res.grounding_facts] == [
        "FK-A",
        "FK-B",
        "FK-A",
        "FK-B",
        "FK-A",
        "FK-B",
    ]


def test_short_uv_abbreviation_does_not_match_inside_unrelated_suv_token():
    res = asyncio.run(
        _r().retrieve("O-Ring für ein SUV-Getriebe auswählen", tenant_id="t", k=5)
    )
    assert "FK-NBR-OZON" not in {fact.card_id for fact in res.grounding_facts}


def test_hardening_stem_does_not_match_hartverchromte_shaft_surface():
    assert "hardening" not in _retrieval_concepts(
        "RWDR auf einer hartverchromten Wellenoberfläche"
    )


def test_crack_stem_still_matches_inflected_rissig_wording():
    concepts = _retrieval_concepts("Der NBR-RWDR ist rissig.")

    assert {"tear", "cracking"} <= concepts


def test_schokolade_ruehrwerk_case_retrieves_food_and_seal_profiles():
    res = asyncio.run(
        _r().retrieve(
            "Rührwerk für Schokolade, Welle läuft unrund, produktberührt, CIP bis 100 °C",
            tenant_id="t",
        )
    )

    card_ids = {fact.card_id for fact in res.grounding_facts}
    assert {"FK-FOODGRADE-FETT", "FK-GLRD-ENGINEERING-PROFILE"} <= card_ids


def test_high_pressure_gas_case_includes_reviewed_medium_method():
    res = asyncio.run(
        _r().retrieve(
            "Welche Dichtung für ein Hochdruck-Erdgasventil, 200 bar, mit schnellen Druckwechseln?",
            tenant_id="t",
        )
    )

    assert "FK-MEDIUM-ENGINEERING-METHOD" in {
        fact.card_id for fact in res.grounding_facts
    }


def test_unknown_process_medium_retrieves_only_the_reviewed_selection_method():
    res = asyncio.run(
        _r().retrieve(
            "Welcher Dichtungswerkstoff passt für ein eher exotisches Prozessmedium, "
            "zu dem es keine geprüfte Verträglichkeitsangabe gibt?",
            tenant_id="t",
        )
    )

    assert "FK-MEDIUM-ENGINEERING-METHOD" in {
        fact.card_id for fact in res.grounding_facts
    }


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
                sources=("test-source",),
                provenance=("owner:qtest",),
                reviewed_by="test-domain-reviewer",
                reviewed_at="2026-07-11T00:00:00Z",
                review_expires_at="2099-07-11T00:00:00Z",
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


# --- P2-D: claim-severity tie-break (Quellenhierarchie/Konfliktlogik §4.3) -----------------------


def _card(cid, kind, *, material="fkm", medium="testmedium"):
    return Fachkarte(
        id=cid,
        scope={"material": [material], "medium": [medium]},
        claims=(
            Claim(
                text=f"{material} claim of kind {kind}.",
                review_state="reviewed",
                sources=("test-source",),
                provenance=("owner:x",),
                kind=kind,
                reviewed_by="test-domain-reviewer",
                reviewed_at="2026-07-11T00:00:00Z",
                review_expires_at="2099-07-11T00:00:00Z",
            ),
        ),
        review_state="reviewed",
        provenance=("owner:x",),
    )


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("safety_nogo", 4),
        ("safety_caution", 3),
        ("qualification_required", 3),
        ("regulatory_status", 2),
        ("system_dependent", 1),
        ("definition", 1),
        ("example_value", 1),
        ("family_tendency", 0),
    ],
)
def test_card_severity_ranks_each_kind(kind, expected):
    assert _card_severity(_card("FK-T", kind)) == expected


def test_card_severity_takes_the_max_across_multiple_claims():
    card = Fachkarte(
        id="FK-T",
        scope={"material": ["fkm"]},
        claims=(
            Claim(
                text="a",
                review_state="reviewed",
                sources=("test-source",),
                provenance=("owner:x",),
                kind="family_tendency",
                reviewed_by="test-domain-reviewer",
                reviewed_at="2026-07-11T00:00:00Z",
                review_expires_at="2099-07-11T00:00:00Z",
            ),
            Claim(
                text="b",
                review_state="draft",
                provenance=("cc:x",),
                kind="safety_nogo",
            ),
        ),
        review_state="reviewed",
        provenance=("owner:x",),
    )
    assert (
        _card_severity(card) == 4
    )  # the draft safety_nogo still counts (see docstring)


def test_tie_break_prefers_higher_claim_severity_at_equal_relevance():
    # FK-A ("family_tendency") would win the OLD alphabetical tie-break, but FK-Z (safety_nogo) must
    # win under the new severity tie-break — a safety-critical card must not lose a coin-flip-by-name.
    low = _card("FK-A", "family_tendency")
    high = _card("FK-Z", "safety_nogo")
    catalog = FachkartenCatalog(cards=(low, high))
    res = asyncio.run(
        InProcessRetriever(catalog).retrieve("fkm testmedium", tenant_id="t", k=1)
    )
    # k=1 makes the tie decisive: only ONE card can make the cut, and it must be the safety-relevant one
    assert {f.card_id for f in res.grounding_facts} == {"FK-Z"}


def test_relevance_still_beats_claim_severity():
    # a card with MORE scope hits always wins, regardless of claim severity — the tie-break only
    # decides between EQUALLY relevant cards, it never overrides the primary relevance ranking.
    weaker_but_severe = _card("FK-A", "safety_nogo")
    stronger_but_mild = Fachkarte(
        id="FK-Z",
        scope={
            "material": ["fkm"],
            "medium": ["testmedium"],
            "property": ["hitzebestaendig"],
        },
        claims=(
            Claim(
                text="fkm claim",
                review_state="reviewed",
                sources=("test-source",),
                provenance=("owner:x",),
                kind="family_tendency",
                reviewed_by="test-domain-reviewer",
                reviewed_at="2026-07-11T00:00:00Z",
                review_expires_at="2099-07-11T00:00:00Z",
            ),
        ),
        review_state="reviewed",
        provenance=("owner:x",),
    )
    catalog = FachkartenCatalog(cards=(weaker_but_severe, stronger_but_mild))
    res = asyncio.run(
        InProcessRetriever(catalog).retrieve(
            "fkm testmedium hitzebestaendig", tenant_id="t", k=1
        )
    )
    assert {f.card_id for f in res.grounding_facts} == {"FK-Z"}  # 3 hits beats 2


# --- P3: catalog accessor (Wissensstand-Referenz) ------------------------------------------------


def test_catalog_property_exposes_the_backing_catalog():
    # mirrors the accessor already on InProcessCompatibilityMatrix/InProcessVersagensmodiStore
    catalog = FachkartenCatalog(
        cards=(_card("FK-T", "family_tendency"),), version="test_v1"
    )
    assert InProcessRetriever(catalog).catalog is catalog
    assert InProcessRetriever(catalog).catalog.version == "test_v1"
