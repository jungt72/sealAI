from __future__ import annotations

import pytest

from sealai_v2.core.case_state import CaseFieldStatus, CaseStateV2
from sealai_v2.core.contracts import RememberedFact


def test_case_state_preserves_field_provenance_and_document_coordinates():
    state = CaseStateV2.from_remembered_facts(
        case_id="RWDR-42",
        revision=7,
        facts=(
            RememberedFact(
                feld="medium",
                wert="synthetic_oil",
                provenance="document-extracted",
                status="document_extracted",
                unit="",
                source_ref="DOC-221#p17",
                observed_at="2026-07-10T10:00:00Z",
                document_id="DOC-221",
                document_version="2026-04",
                page=17,
                bbox=(120.0, 210.0, 880.0, 360.0),
                confidence=0.97,
            ),
        ),
    )
    field = state.field("medium")
    assert field is not None
    assert field.status is CaseFieldStatus.DOCUMENT_EXTRACTED
    assert field.source.document_id == "DOC-221"
    assert field.source.page == 17
    assert state.to_prompt_context() == [{"feld": "medium", "wert": "synthetic_oil"}]
    assert len(state.fingerprint) == 64


def test_case_state_legacy_round_trip_keeps_metadata():
    fact = RememberedFact(
        feld="temperature",
        wert="120",
        provenance="user-confirmed",
        status="confirmed",
        unit="degC",
        source_ref="message-12",
        as_of_turn=3,
        confidence=1.0,
    )
    state = CaseStateV2.from_remembered_facts(
        case_id="case-a", revision=2, facts=(fact,)
    )
    roundtrip = state.to_remembered_facts()[0]
    assert roundtrip.feld == fact.feld
    assert roundtrip.wert == fact.wert
    assert roundtrip.unit == fact.unit
    assert roundtrip.status == fact.status
    assert roundtrip.source_ref == fact.source_ref
    assert roundtrip.confidence == fact.confidence


def test_case_state_rejects_duplicate_keys_and_negative_revision():
    facts = (RememberedFact("medium", "oil"), RememberedFact("medium", "water"))
    with pytest.raises(ValueError, match="unique"):
        CaseStateV2.from_remembered_facts(case_id="c", revision=0, facts=facts)
    with pytest.raises(ValueError, match="negative"):
        CaseStateV2(case_id="c", revision=-1)
