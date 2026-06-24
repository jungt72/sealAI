"""chat_response surfaces the Modus-E Gegencheck verdict (deterministic API field).

The structured verdict rides the response so the SPA can render a Gegencheck badge
deterministically — independent of how L1 phrased the answer. None when the turn is
not a Gegencheck situation. Offline, no LLM.
"""

from __future__ import annotations

from sealai_v2.api.serializers import chat_response
from sealai_v2.core.contracts import (
    Answer,
    Flags,
    PipelineResult,
    VerifierAction,
    VerifierVerdict,
)


def _result(gegencheck):
    return PipelineResult(
        question="Wir verwenden FKM in Heißdampf, passt das?",
        tenant_id="t1",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="…", model="fake"),
        gegencheck=gegencheck,
    )


def _verified_result(verifier, *, verified=True):
    return PipelineResult(
        question="Welche Härte für die O-Ring-Nut?",
        tenant_id="t1",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="…", model="fake"),
        verified=verified,
        verifier=verifier,
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


# --- P1.5: L3 verification status on the chat payload ------------------------------------------
# Without this block the client cannot tell a verified answer from a hedge or a
# silently-unverified one. ``verified`` is the conservative, honest signal; the nested
# ``verification`` object carries the raw action / parse_ok / hedged for a precise badge.


def test_pass_verdict_is_verified():
    out = chat_response(
        _verified_result(VerifierVerdict(action=VerifierAction.PASS, parse_ok=True))
    )
    assert out["verified"] is True
    assert out["verification"]["action"] == "pass"
    assert out["verification"]["parse_ok"] is True
    assert out["verification"]["hedged"] is False
    assert out["verification"]["ran"] is True


def test_corrected_verdict_is_verified():
    # CORRECTED = blocked then regenerated against a REVIEWED correction → clean; still confident.
    out = chat_response(
        _verified_result(
            VerifierVerdict(
                action=VerifierAction.CORRECTED, regenerated=True, parse_ok=True
            )
        )
    )
    assert out["verified"] is True
    assert out["verification"]["action"] == "corrected"
    assert out["verification"]["hedged"] is False


def test_flag_verdict_is_verified():
    out = chat_response(
        _verified_result(VerifierVerdict(action=VerifierAction.FLAG, parse_ok=True))
    )
    assert out["verified"] is True
    assert out["verification"]["action"] == "flag"
    assert out["verification"]["hedged"] is False


def test_blocked_hedge_verdict_is_not_verified_and_hedged():
    out = chat_response(
        _verified_result(
            VerifierVerdict(action=VerifierAction.BLOCKED_HEDGE, parse_ok=True)
        )
    )
    assert out["verified"] is False
    assert out["verification"]["action"] == "blocked_hedge"
    assert out["verification"]["hedged"] is True
    assert out["verification"]["ran"] is True


def test_parse_failure_is_not_verified():
    # Fail-open: L3 ran but its output did not parse → never report a confident "verified".
    out = chat_response(
        _verified_result(VerifierVerdict(action=VerifierAction.PASS, parse_ok=False))
    )
    assert out["verified"] is False
    assert out["verification"]["parse_ok"] is False
    assert out["verification"]["hedged"] is False


def test_no_verifier_is_not_verified():
    # L3 absent/disabled — the silently-unverified case the client must be able to detect.
    out = chat_response(_verified_result(None, verified=False))
    assert out["verified"] is False
    assert out["verification"]["action"] is None
    assert out["verification"]["parse_ok"] is None
    assert out["verification"]["hedged"] is False
    assert out["verification"]["ran"] is False


def test_verification_values_are_json_safe():
    # action must be the enum's .value (a plain str), not the Enum member.
    out = chat_response(
        _verified_result(VerifierVerdict(action=VerifierAction.PASS, parse_ok=True))
    )
    assert isinstance(out["verification"]["action"], str)
    assert type(out["verification"]["action"]) is str
