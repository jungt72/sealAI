"""Release invariants for the ratified SSoT v2.0 owner review."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sealai_v2.knowledge.fachkarten import load_fachkarten
from sealai_v2.knowledge.ledger import (
    _authority_fingerprint,
    _digest,
    _normalise_text,
)


ROOT = Path(__file__).resolve().parents[3]
RECORD = ROOT / "docs/ssot/reviews/2026-07-12-owner-claim-approval.json"
OWNER_SUBJECT = "7748ba15-bef4-43b4-b95a-cf80fcc476d8"


def test_owner_review_activates_exactly_79_claims_without_promoting_drafts():
    catalog = load_fachkarten()
    claims = [claim for card in catalog.cards for claim in card.claims]

    assert sum(claim.reviewed for claim in claims) == 79
    assert sum(claim.review_state == "draft" for claim in claims) == 522
    assert sum(claim.quarantined for claim in claims) == 0


def test_owner_review_contract_is_complete_current_and_human_bound():
    catalog = load_fachkarten()
    reviewed = [claim for card in catalog.cards for claim in card.reviewed_claims()]
    now = datetime.now(timezone.utc)

    assert reviewed
    for claim in reviewed:
        assert claim.reviewed_by == OWNER_SUBJECT
        assert claim.sources
        assert claim.evidence
        assert claim.applicability
        assert claim.uncertainty
        assert claim.transferability
        assert (
            datetime.fromisoformat(claim.review_expires_at.replace("Z", "+00:00")) > now
        )


def test_owner_review_record_matches_every_live_authority_fingerprint():
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    catalog = load_fachkarten()
    decisions = {item["claim_id"]: item for item in record["claims"]}

    assert record["independent_review_attested"] is True
    assert record["reviewer"]["subject"] == OWNER_SUBJECT
    assert record["counts"] == {
        "approved": 79,
        "external_technical_sources": 51,
        "internal_domain_expert_attestation": 28,
        "technical_text_changes": 0,
    }

    observed = 0
    for card in catalog.cards:
        for claim in card.reviewed_claims():
            content_hash = _digest(_normalise_text(claim.text))
            matching = [
                item
                for item in decisions.values()
                if item["card_id"] == card.id and item["text_sha256"] == content_hash
            ]
            assert len(matching) == 1
            assert matching[0]["authority_fingerprint"] == _authority_fingerprint(
                card, claim, content_sha256=content_hash
            )
            observed += 1
    assert observed == 79


def test_internal_attestations_are_not_misrepresented_as_external_evidence():
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    internal = [item for item in record["claims"] if item["external_evidence"] is False]

    assert len(internal) == 28
    for item in internal:
        assert item["evidence_class"] == "internal_domain_expert_attestation"
        assert item["uncertainty"] == "not_sufficiently_supported"
        assert item["transferability"] == "not_assessed"
        assert item["evidence"][0]["source_type"] == (
            "internal_domain_expert_attestation"
        )
        assert item["evidence"][0]["external_evidence"] is False
        assert (
            "no external technical evidence asserted" in item["evidence"][0]["citation"]
        )
        assert item["review_expires_at"] == "2026-10-12T10:29:44Z"
