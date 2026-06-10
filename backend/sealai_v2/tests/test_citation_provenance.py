"""M6c — provenance: the user-facing citation surfaces the OWNER-VERIFIED PRIMARY SOURCE
(GroundingFact.sources), never the internal card_id. The sources field is L1-NEUTRAL (the assembler
ignores it → byte-identical prompt → no behavior change, no eval perturbation)."""

from __future__ import annotations

import asyncio

from sealai_v2.api.serializers import citation
from sealai_v2.core.contracts import Flags, GroundingFact
from sealai_v2.knowledge.retrieval import InProcessRetriever
from sealai_v2.prompts.assembler import PromptAssembler


def test_citation_surfaces_primary_source_not_card_id():
    f = GroundingFact(
        text="Statische O-Ring-Verpressung ~15–25 %.",
        quelle="Fachkarte FK-ORING-VERPRESSUNG (reviewed)",
        card_id="FK-ORING-VERPRESSUNG",
        sources=("Parker O-Ring Handbook", "ISO 3601-2 (Nutauslegung)"),
    )
    c = citation(f)
    assert c["sources"] == ["Parker O-Ring Handbook", "ISO 3601-2 (Nutauslegung)"]
    assert "FK-ORING-VERPRESSUNG" not in str(c)  # internal card_id never exposed to the user


def test_citation_fallback_when_no_primary_source_hides_card_id():
    f = GroundingFact(text="x", quelle="Fachkarte FK-EPDM (reviewed)", card_id="FK-EPDM", sources=())
    c = citation(f)
    assert c["sources"] == ["geprüfte Fachkarte (intern)"] and "FK-EPDM" not in str(c)


def test_retrieval_propagates_claim_primary_sources_to_grounding_fact():
    r = asyncio.run(
        InProcessRetriever().retrieve("O-Ring Verpressung statische Nut Auslegung", tenant_id="t")
    )
    assert any("Parker O-Ring Handbook" in f.sources for f in r.grounding_facts)


def test_sources_field_is_L1_neutral_byte_identical_prompt():
    # the assembler renders only text + quelle → adding `sources` must not change the prompt
    a = PromptAssembler()
    gf_with = [GroundingFact(text="t", quelle="q", card_id="c", sources=("Parker", "ISO 3601-2"))]
    gf_without = [GroundingFact(text="t", quelle="q", card_id="c")]
    assert a.system_prompt(flags=Flags(), grounding_facts=gf_with) == a.system_prompt(
        flags=Flags(), grounding_facts=gf_without
    )
