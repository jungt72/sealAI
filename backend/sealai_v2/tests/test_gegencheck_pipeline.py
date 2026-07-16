"""Gegencheck verdict threaded through ``pipeline.run`` (Modus E end-to-end, offline).

A "wir verwenden X, passt das?" turn attaches the deterministic verdict to
``PipelineResult.gegencheck``; a knowledge turn or a matrix-off pipeline attaches
None (byte-identical no-Gegencheck path). Generate-only fake client (no understand,
no L3) — the verdict is pure/deterministic, independent of the narration.
"""

from __future__ import annotations

import asyncio

from sealai_v2.core.contracts import ModelConfig
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.knowledge.matrix import InProcessCompatibilityMatrix
from sealai_v2.pipeline import stages
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient


def _pipeline(
    client, *, with_matrix: bool = True, material_constraints_enabled: bool = False
) -> Pipeline:
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=None,
        matrix=InProcessCompatibilityMatrix() if with_matrix else None,
        material_constraints_enabled=material_constraints_enabled,
    )


def _run(p, q):
    return asyncio.run(p.run(q, tenant=TenantContext("t1")))


def test_verdict_flows_for_incompatible_gegencheck():
    res = _run(
        _pipeline(FakeLlmClient("Antwort")),
        "Wir verwenden FKM in Heißdampf, passt das?",
    )
    assert res.gegencheck is not None
    assert res.gegencheck["disqualified"] is True
    assert res.gegencheck["reason"] and res.gegencheck["source"]


def test_no_verdict_on_knowledge_turn():
    res = _run(_pipeline(FakeLlmClient("Antwort")), "Was kann FKM?")
    assert res.gegencheck is None


def test_no_verdict_when_matrix_off():
    res = _run(
        _pipeline(FakeLlmClient("Antwort"), with_matrix=False),
        "Wir verwenden FKM in Heißdampf, passt das?",
    )
    assert res.gegencheck is None


def test_material_constraint_result_is_absent_by_default() -> None:
    res = _run(
        _pipeline(FakeLlmClient("Antwort")),
        "Wir verwenden NBR in Synthetiköl, passt das?",
    )
    assert res.material_constraints is None


def test_flag_off_does_not_call_new_material_constraint_stage(monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("flag-off path called the MAT-GOV-01 stage")

    monkeypatch.setattr(stages, "material_constraints", forbidden)
    res = _run(
        _pipeline(FakeLlmClient("Antwort")),
        "Wir verwenden FKM in Heißdampf, passt das?",
    )
    assert res.gegencheck is not None
    assert res.gegencheck["disqualified"] is True
    assert res.material_constraints is None


def test_enabled_contract_is_additive_and_legacy_verdict_stays_compatible() -> None:
    res = _run(
        _pipeline(FakeLlmClient("Antwort"), material_constraints_enabled=True),
        "Wir verwenden NBR in Synthetiköl, passt das?",
    )
    assert res.gegencheck is not None
    assert res.gegencheck["basis"] == "matrix_conditional"
    assert res.material_constraints is not None
    assert res.material_constraints.to_dict()["verdict"] == "bedingt"
    assert res.material_constraints.to_dict()["medium_cardinality"] == "single"
    assert res.material_constraints.to_dict()["relation_state"] == "not_applicable"


def test_enabled_contract_never_returns_none_without_matrix() -> None:
    res = _run(
        _pipeline(
            FakeLlmClient("Antwort"),
            with_matrix=False,
            material_constraints_enabled=True,
        ),
        "Wir verwenden FKM in Heißdampf, passt das?",
    )
    assert res.material_constraints is not None
    assert res.material_constraints.to_dict()["evaluation_state"] == "no_rule_data"
    assert res.material_constraints.to_dict()["medium_cardinality"] == "single"


def test_enabled_contract_returns_blocked_result_without_inputs() -> None:
    res = _run(
        _pipeline(FakeLlmClient("Antwort"), material_constraints_enabled=True),
        "Was ist eine Radialwellendichtung?",
    )
    assert res.material_constraints is not None
    assert res.material_constraints.to_dict()["evaluation_state"] == "blocked"
    assert res.material_constraints.to_dict()["medium_cardinality"] == "none"
    assert res.material_constraints.to_dict()["relation_state"] == "undetermined"
