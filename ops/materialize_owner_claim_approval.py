#!/usr/bin/env python3
"""Materialize one explicit owner decision into the governed knowledge seed.

This command does not decide whether a claim is correct. It records an already
made human decision, verifies that it targets the exact review queue, and emits
the immutable review contract consumed by the repository bootstrap.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from sealai_v2.knowledge.fachkarten import load_fachkarten
from sealai_v2.knowledge.ledger import (
    GLOBAL_KNOWLEDGE_TENANT,
    _authority_fingerprint,
    _claim_id,
    _digest,
    _normalise_text,
)


INTERNAL_ATTESTATION_PATH = (
    "repo://docs/ssot/reviews/2026-07-12-owner-claim-approval.json"
)
UNCERTAINTY_BY_KIND = {
    "definition": "bounded",
    "example_value": "bounded",
    "family_tendency": "conditional",
    "qualification_required": "conditional",
    "regulatory_status": "conditional",
    "safety_caution": "conditional",
    "safety_nogo": "conditional",
    "system_dependent": "conditional",
}
TRANSFERABILITY_BY_KIND = {
    "definition": "family_level_orientation",
    "example_value": "source_specific",
    "family_tendency": "family_level_orientation",
    "qualification_required": "application_dependent",
    "regulatory_status": "source_specific",
    "safety_caution": "application_dependent",
    "safety_nogo": "application_dependent",
    "system_dependent": "application_dependent",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--reviewer-subject", required=True)
    parser.add_argument("--reviewer-username", required=True)
    parser.add_argument("--reviewer-email", required=True)
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--source-backed-expires-at", required=True)
    parser.add_argument("--internal-attestation-expires-at", required=True)
    parser.add_argument("--decision-reference", required=True)
    parser.add_argument("--expected-claims", type=int, default=79)
    parser.add_argument("--independent-review-attested", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.independent_review_attested:
        raise SystemExit(
            "refusing to materialize without independent human attestation"
        )

    seed = json.loads(args.seed.read_text(encoding="utf-8"))
    queue = json.loads(args.queue.read_text(encoding="utf-8"))
    queued = queue.get("claims", [])
    if len(queued) != args.expected_claims:
        raise SystemExit(
            f"expected {args.expected_claims} queued claims, received {len(queued)}"
        )
    initial_seed_hash_matches = queue.get("seed_sha256") == _sha256(args.seed)

    queue_by_location = {
        (item["card_id"], int(item["claim_order"])): item for item in queued
    }
    if len(queue_by_location) != args.expected_claims:
        raise SystemExit("review queue contains duplicate claim locations")

    changed = 0
    internal_count = 0
    for card in seed["cards"]:
        card_changed = False
        for order, claim in enumerate(card["claims"]):
            queued_claim = queue_by_location.get((card["id"], order))
            if queued_claim is None:
                continue
            already_materialized = (
                claim.get("review_state") == "reviewed"
                and claim.get("reviewed_by") == args.reviewer_subject
                and claim.get("reviewed_at") == args.reviewed_at
            )
            if claim.get("review_state") != "quarantined" and not already_materialized:
                raise SystemExit(
                    f"{card['id']}[{order}] is neither queued nor this exact review"
                )
            if claim["text"] != queued_claim["text"]:
                raise SystemExit(
                    f"{card['id']}[{order}] text differs from review queue"
                )

            source_backed = bool(queued_claim["source_backed"])
            if not source_backed:
                internal_count += 1
                internal_citation = (
                    "sealingAI owner domain-expert attestation; no external technical "
                    f"evidence asserted; claim {queued_claim['claim_id']} "
                    f"({INTERNAL_ATTESTATION_PATH}#{queued_claim['claim_id']})"
                )
                claim["sources"] = [internal_citation]
                claim["evidence"] = [
                    {
                        "citation": internal_citation,
                        "source_type": "internal_domain_expert_attestation",
                        "external_evidence": False,
                        "reviewer_subject": args.reviewer_subject,
                        "decision_record": INTERNAL_ATTESTATION_PATH,
                    }
                ]
            else:
                claim["evidence"] = [
                    {
                        "citation": citation,
                        "source_type": "external_technical_reference",
                        "external_evidence": True,
                    }
                    for citation in claim["sources"]
                ]

            claim["review_state"] = "reviewed"
            claim["reviewed_by"] = args.reviewer_subject
            claim["reviewed_at"] = args.reviewed_at
            claim["review_expires_at"] = (
                args.source_backed_expires_at
                if source_backed
                else args.internal_attestation_expires_at
            )
            claim["applicability"] = {
                key: list(card.get("scope", {}).get(key, []))
                for key in ("material", "medium", "property", "application")
            }
            claim["uncertainty"] = (
                UNCERTAINTY_BY_KIND[claim.get("kind", "family_tendency")]
                if source_backed
                else "not_sufficiently_supported"
            )
            claim["transferability"] = (
                TRANSFERABILITY_BY_KIND[claim.get("kind", "family_tendency")]
                if source_backed
                else "not_assessed"
            )
            previous_reason = str(claim.get("change_reason", "")).strip()
            approval_reason = "owner_domain_approval_ssot_v2_20260712"
            if approval_reason not in previous_reason:
                claim["change_reason"] = (
                    f"{previous_reason}; {approval_reason}"
                    if previous_reason
                    else approval_reason
                )
            card_changed = True
            changed += 1
        if card_changed:
            card["review_state"] = "reviewed"

    if changed != args.expected_claims:
        raise SystemExit(f"materialized {changed}, expected {args.expected_claims}")
    if internal_count != queue["counts"]["without_external_evidence"]:
        raise SystemExit("internal-attestation count differs from review queue")

    if not initial_seed_hash_matches and not seed["version"].endswith(
        "+owner-approval-20260712"
    ):
        raise SystemExit("review queue does not bind the current seed")
    if not seed["version"].endswith("+owner-approval-20260712"):
        seed["version"] = f"{seed['version']}+owner-approval-20260712"
    seed["source"] = (
        "Governed SSoT v2.0 seed. The sealingAI owner independently approved the "
        "79 previously quarantined claims on 2026-07-12. Fifty-one retain their "
        "external technical citations; 28 are explicitly identified as internal "
        "domain-expert attestations without external evidence and therefore carry "
        "not_sufficiently_supported/not_assessed metadata plus a shorter review "
        "window. The remaining 522 claims remain draft and non-authoritative."
    )
    _write_json(args.seed, seed)

    catalog = load_fachkarten(args.seed)
    cards = {card.id: card for card in catalog.cards}
    decisions = []
    for queued_claim in queued:
        card = cards[queued_claim["card_id"]]
        claim = card.claims[int(queued_claim["claim_order"])]
        content_hash = _digest(_normalise_text(claim.text))
        claim_id = _claim_id(
            tenant_id=GLOBAL_KNOWLEDGE_TENANT,
            source_type="git_seed",
            source_id="fachkarten_seed",
            card_id=card.id,
            content_sha256=content_hash,
        )
        if claim_id != queued_claim["claim_id"]:
            raise SystemExit(f"logical claim identity changed for {card.id}")
        decisions.append(
            {
                "claim_id": claim_id,
                "authority_fingerprint": _authority_fingerprint(
                    card, claim, content_sha256=content_hash
                ),
                "card_id": card.id,
                "claim_order": int(queued_claim["claim_order"]),
                "text_sha256": content_hash,
                "technical_text_changed": False,
                "review_status": "approved",
                "evidence_class": (
                    "external_technical_sources"
                    if queued_claim["source_backed"]
                    else "internal_domain_expert_attestation"
                ),
                "external_evidence": bool(queued_claim["source_backed"]),
                "evidence": list(claim.evidence),
                "applicability": claim.applicability,
                "uncertainty": claim.uncertainty,
                "transferability": claim.transferability,
                "conflicts": list(claim.conflicts),
                "reviewed_at": claim.reviewed_at,
                "review_expires_at": claim.review_expires_at,
                "change_reason": claim.change_reason,
            }
        )

    record = {
        "schema_version": "sealingai.owner-knowledge-review.v1",
        "ssot_version": "2.0",
        "decision": "approve_all_queued_claims",
        "independent_review_attested": True,
        "decision_reference": args.decision_reference,
        "reviewer": {
            "identity_provider": "keycloak",
            "realm": "sealAI",
            "subject": args.reviewer_subject,
            "username": args.reviewer_username,
            "email": args.reviewer_email,
        },
        "reviewed_at": args.reviewed_at,
        "source_queue": {
            "source_commit": queue["source_commit"],
            "served_tree_hash": queue["served_tree_hash"],
            "seed_sha256_before_review": queue["seed_sha256"],
        },
        "seed_sha256_after_review": _sha256(args.seed),
        "counts": {
            "approved": len(decisions),
            "external_technical_sources": sum(
                1 for item in decisions if item["external_evidence"]
            ),
            "internal_domain_expert_attestation": sum(
                1 for item in decisions if not item["external_evidence"]
            ),
            "technical_text_changes": 0,
        },
        "authority_notice": (
            "Approval is bound to each authority_fingerprint. Any change to text, "
            "card version, scope, sources, applicability, uncertainty, "
            "transferability, or conflicts invalidates preservation of this review."
        ),
        "internal_evidence_notice": (
            "Internal domain-expert attestations are deliberately not represented "
            "as external research. Their shorter expiry and conservative epistemic "
            "metadata remain part of the serving contract."
        ),
        "claims": decisions,
    }
    _write_json(args.record, record)
    print(json.dumps(record["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
