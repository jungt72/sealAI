"""Model-swap eval matrix — Part 2 (offline, no network, no token spend).

Proves: token-usage capture is additive; the per-cell GATE computes correctly (PASS + every FAIL
mode); the JUDGE is metered-excluded AND uses its own client (decoupled from the helper); the matrix
runner wires per-role provider routing + latency/cost/answer-quality aggregation end-to-end against
a fake factory. No cell hits an API — the live run is owner-token-gated (--execute)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sealai_v2.core.contracts import Flags, LlmResult, ModelConfig, TokenUsage
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.eval import matrix
from sealai_v2.eval.cases import Case
from sealai_v2.eval.harness import _run_unit
from sealai_v2.eval.metering import MeteringLlmClient, TokenMeter
from sealai_v2.llm.client import _parse_usage
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler


# --- additive usage capture ---------------------------------------------------------------


def test_parse_usage_present_and_absent():
    resp = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=120, completion_tokens=30, total_tokens=150)
    )
    assert _parse_usage(resp) == TokenUsage(120, 30, 150)
    assert _parse_usage(SimpleNamespace()) is None  # no usage attr → None (byte-identical default)


def test_metering_keys_by_model_and_ignores_none_usage():
    meter = TokenMeter()
    meter.add("m-a", TokenUsage(10, 5, 15))
    meter.add("m-a", TokenUsage(10, 5, 15))
    meter.add("m-b", None)  # fake → counted as a call, no tokens
    assert meter.by_model["m-a"]["total_tokens"] == 30
    assert meter.by_model["m-b"]["total_tokens"] == 0
    assert meter.total_tokens == 30 and meter.n_calls == 3 and meter.n_calls_with_usage == 2


# --- judge is metered-EXCLUDED and uses its own client ------------------------------------


class _RecordingFake:
    def __init__(self, text: str, usage: TokenUsage | None = None):
        self.text, self.usage, self.calls = text, usage, []

    async def generate(self, *, system, user, model_config):
        self.calls.append({"system": system, "model": model_config.model})
        return LlmResult(text=self.text, model=model_config.model, finish_reason="stop", usage=self.usage)


_JUDGE_JSON = (
    '{"must_contain":[{"point":"x","status":"met"}],"must_catch":{"named":true},'
    '"must_avoid":[],"axes":{"2":"pass","3":"pass","4":"pass","5":"pass","6":"pass","7":"pass"},'
    '"notes":"ok"}'
)


def _case() -> Case:
    return Case(
        id="t1",
        klass="wissensfrage",
        input="Was ist NBR?",
        must_contain=("definition",),
        must_catch="kein",
        must_avoid=(),
        primary_axes=(2, 4, 6),
        hard_gates=(),
    )


def test_judge_uses_own_client_and_is_not_metered():
    meter = TokenMeter()
    subject = MeteringLlmClient(
        _RecordingFake("eine Antwort", TokenUsage(100, 50, 150)), meter
    )
    judge_fake = _RecordingFake(_JUDGE_JSON, TokenUsage(999, 999, 1998))
    pipeline = Pipeline(
        generator=L1Generator(subject, PromptAssembler(), ModelConfig("subject-l1")),
        client=subject,
        helper_model=ModelConfig("subject-helper"),
        understand_enabled=False,
    )
    rec = asyncio.run(
        _run_unit(
            pipeline,
            ModelConfig("JUDGE-MODEL"),
            _case(),
            "flags_on",
            Flags(),
            judge_client=judge_fake,
        )
    )
    # judge ran on its OWN client (not the subject), and its (large) tokens never reached the meter.
    assert judge_fake.calls and judge_fake.calls[0]["model"] == "JUDGE-MODEL"
    assert "JUDGE-MODEL" not in meter.by_model
    assert meter.total_tokens == 150  # only the single subject L1 call
    assert rec.score.axis_status.get(2) == "pass"  # judge JSON was actually consumed


# --- gate pure functions ------------------------------------------------------------------


def _out(*, cred=1.0, mc=1.0, kt=1.0, parametric=1.0, memory=1.0, exfil=1.0, corrected=2):
    return {
        "summaries": {
            "flags_off": {"overall_credibility": cred},
            "flags_on": {"overall_credibility": cred},
        },
        "answer_quality": {
            "overall": {"must_contain_coverage": mc, "must_catch_named_rate": kt}
        },
        "parametric": {"schranken_quota": parametric},
        "multiturn": {"summary": {"memory_schranken_quota": memory}},
        "injection": {"exfiltration": {"schranken_quota": exfil}},
        "catches": {"pass": 5, "flag": 0, "corrected": corrected, "blocked_hedge": 0},
        "latency": {"p50_ms": 100.0, "p95_ms": 200.0},
        "token_usage": {"by_model": {}, "n_turns": 10, "tokens_per_turn": 0.0},
    }


def _gate(cell, base=None, tol_cred=0.0, tol_aq=0.0):
    return matrix.evaluate_gate(
        base or _out(), cell, tol_cred=tol_cred, tol_aq=tol_aq
    )


def test_gate_passes_when_no_regression():
    passed, reasons, _ = _gate(_out())
    assert passed and reasons == []


def test_gate_fails_on_schranke_trip():
    passed, reasons, _ = _gate(_out(parametric=0.9))
    assert not passed and any("schranke" in r for r in reasons)


def test_gate_fails_on_credibility_regression():
    passed, reasons, _ = _gate(_out(cred=0.8))
    assert not passed and any("credibility" in r for r in reasons)


def test_gate_fails_on_answer_quality_regression_even_if_credibility_holds():
    # The owner's #1 protection: a thinned answer (must_contain coverage drops) fails the gate
    # though credibility (axes 2-7) is unchanged.
    passed, reasons, views = _gate(_out(mc=0.6))
    assert not passed and any("answer-quality" in r for r in reasons)
    assert views["answer_quality"]["metrics"]["must_contain_coverage"]["delta"] < 0


def test_gate_fails_when_l3_catches_go_silent():
    passed, reasons, _ = _gate(_out(corrected=0))  # baseline had corrected=2, cell has 0
    assert not passed and any("catches" in r for r in reasons)


def test_gate_tolerance_absorbs_small_dip():
    passed, _, _ = _gate(_out(cred=0.99, mc=0.99), tol_cred=0.02, tol_aq=0.02)
    assert passed


# --- cost ---------------------------------------------------------------------------------


def test_est_cost_applies_per_model_rates():
    tu = {
        "by_model": {
            "m-a": {"prompt_tokens": 1_000_000, "completion_tokens": 0, "total_tokens": 1_000_000},
            "m-b": {"prompt_tokens": 0, "completion_tokens": 2_000_000, "total_tokens": 2_000_000},
        },
        "n_turns": 10,
        "tokens_per_turn": 300000.0,
    }
    rates = {"m-a": {"in": 1.0, "out": 2.0}, "m-b": {"in": 0.5, "out": 4.0}}
    cost = matrix.est_cost(tu, rates)
    assert cost["est_total_usd"] == 9.0  # 1*1.0 + 2*4.0
    assert cost["est_cost_per_turn_usd"] == 0.9 and cost["rates_missing"] == []


def test_est_cost_null_when_a_rate_is_missing():
    tu = {"by_model": {"m-a": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}, "n_turns": 1}
    cost = matrix.est_cost(tu, rates={})  # no rate for m-a → honest null, no invented price
    assert cost["est_cost_per_turn_usd"] is None and cost["rates_missing"] == ["m-a"]


# --- manifest + plan ----------------------------------------------------------------------


def test_manifest_loads_baseline_first_and_judge_fixed():
    manifest = matrix.load_manifest()
    cells = matrix.cells_from_manifest(manifest)
    assert cells[0].name == "baseline"
    assert all("judge_model" not in c.overrides and "judge_provider" not in c.overrides for c in cells)


def test_cells_reject_judge_override_and_typos():
    import pytest

    with pytest.raises(ValueError, match="judge"):
        matrix.cells_from_manifest({"cells": [{"name": "x", "overrides": {"judge_model": "y"}}]})
    with pytest.raises(ValueError):
        matrix.cells_from_manifest({"cells": [{"name": "x", "overrides": {"bogus_model": "y"}}]})


def test_settings_for_cell_applies_overrides():
    s = matrix.settings_for_cell(
        matrix.Cell("L1=mistral", {"l1_provider": "mistral", "l1_model": "mistral-small-4"})
    )
    assert s.l1_provider == "mistral" and s.l1_model == "mistral-small-4"
    assert s.verifier_model == "gpt-5.1" and s.judge_model == "gpt-4.1-mini"  # untouched


def test_render_plan_lists_roles_and_no_call_note():
    plan = matrix.render_plan(matrix.load_manifest())
    assert "baseline" in plan and "no models called" in plan
    assert "L1=mistral-small-4" in plan and "judge" in plan


# --- end-to-end offline run (injected fake factory; NO network) ---------------------------


class _MatrixFake:
    """Routes by system-prompt marker so ONE fake drives the full eval offline. Returns valid JSON
    for judge/understand/distill/reask; a plain answer for L1/verifier. Records calls + returns usage
    so the meter accumulates."""

    def __init__(self):
        self.calls = []

    async def generate(self, *, system, user, model_config):
        self.calls.append({"model": model_config.model, "system": system})
        if "Rubrik-Prüfer" in system:
            text = _JUDGE_JSON
        elif "RE-ASK-Disziplin" in system:
            text = '{"reasked":[]}'
        elif "klassifizierst" in system:
            text = '{"intent":"wissensfrage","rationale":"r"}'
        elif "extrahierst strukturierte Fakten" in system:
            text = '{"facts":[]}'
        else:
            text = "Eine sachliche, vorläufige Orientierung ohne Freigabe."
        return LlmResult(
            text=text, model=model_config.model, finish_reason="stop",
            usage=TokenUsage(80, 40, 120),
        )


def test_run_matrix_offline_routes_meters_and_gates(tmp_path):
    fakes: dict[str, _MatrixFake] = {}

    def fake_factory(provider: str):
        return fakes.setdefault(provider, _MatrixFake())

    manifest = {
        "tolerance": {"credibility": 0.0, "answer_quality": 0.0},
        "rates_usd_per_mtok": {
            "gpt-5.1": {"in": 1.0, "out": 2.0},
            "gpt-4.1-mini": {"in": 0.1, "out": 0.2},
            "mistral-small-4": {"in": 0.05, "out": 0.1},
        },
        "cells": [
            {"name": "baseline", "overrides": {}},
            {"name": "L1=mistral-small-4", "overrides": {"l1_provider": "mistral", "l1_model": "mistral-small-4"}},
        ],
    }
    out = asyncio.run(
        matrix.run_matrix(
            manifest,
            run_root=tmp_path,
            git_sha="test",
            timestamp="2026-06-13T00:00:00Z",
            client_factory=fake_factory,
            smoke_limit=1,
        )
    )
    results = {r.name: r for r in out["results"]}
    # Per-role provider ROUTING: the candidate's L1 ran on the mistral client with the cell's model.
    assert "mistral" in fakes
    assert any(c["model"] == "mistral-small-4" for c in fakes["mistral"].calls)
    # Baseline never touched mistral.
    base = results["baseline"]
    assert base.roles["l1"]["provider"] == "openai"
    cand = results["L1=mistral-small-4"]
    assert cand.roles["l1"] == {"provider": "mistral", "model": "mistral-small-4"}
    # Cost computed with rates; latency present.
    assert base.latency["p50_ms"] is not None
    assert base.cost["est_cost_per_turn_usd"] is not None  # rates present → real number
    # Same fake → no regression → candidate PASSES the full gate.
    assert cand.passed is True and cand.reasons == []
    # Report renders without error and marks the verdict.
    report = matrix.render_report(out)
    assert "L1=mistral-small-4 — PASS" in report and "Ranking among PASS cells" in report
