"""Phase 0 (LangGraph-suitability audit) — end-to-end check that pipeline.py's ACTUAL
``_trace_inputs``/``_trace_outputs`` (the functions LangSmith's ``@traceable`` calls on every real
turn) never leak raw question/answer/case content, not just the underlying ``obs.safe_trace``
helpers in isolation."""

from __future__ import annotations

from sealai_v2.core.contracts import Answer, Flags, VerifierAction, VerifierVerdict
from sealai_v2.pipeline.pipeline import _trace_inputs, _trace_outputs

_SYNTHETIC_CUSTOMER = "Musterfirma Dichtungstechnik GmbH"
_SYNTHETIC_FILE = "zeichnung_kunde_XYZ_2026.pdf"
_SYNTHETIC_TECH_VALUE = "genau 847.3 bar bei 212.5 U/min"
_RAW_QUESTION = f"Wir sind {_SYNTHETIC_CUSTOMER}, Zeichnung {_SYNTHETIC_FILE}, {_SYNTHETIC_TECH_VALUE}"
_RAW_ANSWER_TEXT = f"Für {_SYNTHETIC_CUSTOMER} laut {_SYNTHETIC_FILE}: {_SYNTHETIC_TECH_VALUE} empfohlen"


class _FakeResult:
    """Minimal stand-in for PipelineResult — only the attributes _trace_outputs reads."""

    def __init__(
        self, answer: Answer, grounded: bool, verifier: VerifierVerdict | None
    ) -> None:
        self.answer = answer
        self.grounded = grounded
        self.verifier = verifier


def test_trace_inputs_never_contains_raw_question() -> None:
    proj = _trace_inputs(
        {"question": _RAW_QUESTION, "flags": Flags(True, True), "untrusted": ()}
    )
    dumped = repr(proj)
    assert _RAW_QUESTION not in dumped
    assert _SYNTHETIC_CUSTOMER not in dumped
    assert _SYNTHETIC_FILE not in dumped
    assert _SYNTHETIC_TECH_VALUE not in dumped
    assert "question" not in proj  # no raw-content key at all under this or any alias
    assert proj["has_question"] is True
    assert proj["question_length"] == len(_RAW_QUESTION)


def test_trace_inputs_flags_repr_is_safe_dataclass_repr_not_raw_text() -> None:
    proj = _trace_inputs(
        {"question": "x", "flags": Flags(True, False), "untrusted": ()}
    )
    # Flags() only ever reprs its two booleans — never user content — but assert the raw
    # question specifically never leaks through the flags channel either.
    assert _RAW_QUESTION not in proj["flags"]


def test_trace_outputs_never_contains_raw_answer() -> None:
    answer = Answer(text=_RAW_ANSWER_TEXT, model="gpt-5.1")
    verdict = VerifierVerdict(action=VerifierAction.PASS)
    result = _FakeResult(answer=answer, grounded=True, verifier=verdict)

    proj = _trace_outputs(result)
    dumped = repr(proj)
    assert _RAW_ANSWER_TEXT not in dumped
    assert _SYNTHETIC_CUSTOMER not in dumped
    assert _SYNTHETIC_FILE not in dumped
    assert _SYNTHETIC_TECH_VALUE not in dumped
    assert "answer" not in proj
    assert "text" not in proj
    assert proj["answer_length"] == len(_RAW_ANSWER_TEXT)
    assert proj["answer_model"] == "gpt-5.1"
    assert proj["grounded"] is True
    assert proj["verifier_status"] == "pass"


def test_trace_outputs_handles_missing_verifier_safely() -> None:
    answer = Answer(text="ok", model="gpt-5.1")
    result = _FakeResult(answer=answer, grounded=False, verifier=None)
    proj = _trace_outputs(result)
    assert proj["verifier_status"] is None
    assert proj["grounded"] is False


def test_trace_outputs_handles_missing_answer_safely() -> None:
    result = _FakeResult(answer=None, grounded=False, verifier=None)  # type: ignore[arg-type]
    proj = _trace_outputs(result)
    assert proj["answer_length"] == 0
    assert proj["answer_model"] is None
