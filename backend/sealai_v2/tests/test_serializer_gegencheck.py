"""chat_response surfaces the Modus-E Gegencheck verdict (deterministic API field).

The structured verdict rides the response so the SPA can render a Gegencheck badge
deterministically — independent of how L1 phrased the answer. None when the turn is
not a Gegencheck situation. Offline, no LLM.
"""

from __future__ import annotations

from sealai_v2.api.serializers import chat_response
from sealai_v2.core.contracts import Answer, Flags, PipelineResult


def _result(gegencheck):
    return PipelineResult(
        question="Wir verwenden FKM in Heißdampf, passt das?",
        tenant_id="t1",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="…", model="fake"),
        gegencheck=gegencheck,
    )


def test_disqualifying_verdict_is_serialised():
    verdict = {
        "disqualified": True,
        "reason": "FKM hydrolysiert in Heißdampf",
        "source": "Verträglichkeitsmatrix · MX-FKM-DAMPF (reviewed; …)",
    }
    out = chat_response(_result(verdict))
    assert out["gegencheck"] == verdict
    assert out["gegencheck"]["disqualified"] is True


def test_no_gegencheck_situation_serialises_none():
    out = chat_response(_result(None))
    assert out["gegencheck"] is None
