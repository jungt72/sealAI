"""M6c — API serializers: present the pure core's results to the client. The citation serializer
surfaces the OWNER-VERIFIED PRIMARY SOURCE (GroundingFact.sources, e.g. Parker / ISO 3601-2) instead
of the internal card_id (which stays internal for provenance/audit). Presentation only — no domain logic.
"""

from __future__ import annotations

from sealai_v2.core.contracts import GroundingFact, PipelineResult


def citation(fact: GroundingFact) -> dict:
    """User-facing citation: the claim text + its primary source(s). Never exposes the internal
    card_id; falls back to a neutral 'reviewed' label when a (path-i owner-grounded) claim has no
    external primary source."""
    return {
        "text": fact.text,
        "sources": list(fact.sources)
        if fact.sources
        else ["geprüfte Fachkarte (intern)"],
    }


def chat_response(result: PipelineResult) -> dict:
    return {
        "answer": result.answer.text,
        "model": result.answer.model,
        "grounded": result.grounded,
        "intent": (result.understanding.intent.value if result.understanding else None),
        "citations": [citation(f) for f in result.grounding_facts],
    }
