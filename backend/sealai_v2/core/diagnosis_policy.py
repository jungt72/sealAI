"""Serve-boundary policy for deterministic failure-mode diagnoses."""

from __future__ import annotations


DIAGNOSIS_REVIEW_BOUNDARY = (
    "Für dieses Fehlerbild liegt noch kein fachlich geprüfter Diagnoseeintrag vor. "
    "Ursache und Maßnahme werden deshalb nicht ausgegeben."
)


def public_diagnose_payload(payload: dict | None) -> dict | None:
    """Strip cause/fix content unless the matched failure mode is reviewed.

    Draft catalog entries may exist for authoring and review, but are never evidence for a user-facing
    diagnosis. The defensive projection also quarantines legacy payloads that carry only the old
    ``provisional`` flag.
    """
    if payload is None:
        return None
    if (
        bool(payload.get("provisional", True))
        or payload.get("review_state") != "reviewed"
    ):
        return {
            "provisional": True,
            "quarantined": True,
            "review_state": "draft",
            "hinweis": str(payload.get("hinweis") or DIAGNOSIS_REVIEW_BOUNDARY),
        }
    return dict(payload)
