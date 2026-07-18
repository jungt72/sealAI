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
import sealai_v2.pipeline.pipeline as pipeline_module
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


def test_governed_compatible_matrix_fact_is_not_a_positive_l1_claim() -> None:
    res = _run(
        _pipeline(FakeLlmClient("Antwort"), material_constraints_enabled=True),
        "Wir verwenden EPDM in Heißdampf, passt das?",
    )
    assert res.material_constraints is not None
    assert res.material_constraints.to_dict()["verdict"] == "vertraeglich"
    assert all(fact.kind != "matrix" for fact in res.grounding_facts)
    assert res.gegencheck["source"].startswith("matrix-cell:")


def test_governed_result_does_not_auto_migrate_produktspec(monkeypatch) -> None:
    candidate = {"material_candidate_set": ["NBR"]}
    monkeypatch.setattr(
        pipeline_module, "compute_kandidaten_spec", lambda *_args, **_kwargs: candidate
    )
    governed = _pipeline(FakeLlmClient("Antwort"), material_constraints_enabled=True)
    governed.produktspec_enabled = True
    assert (
        _run(governed, "Wir verwenden EPDM in Heißdampf, passt das?").kandidaten_spec
        is None
    )

    legacy = _pipeline(FakeLlmClient("Antwort"), material_constraints_enabled=False)
    legacy.produktspec_enabled = True
    assert (
        _run(legacy, "Wir verwenden EPDM in Heißdampf, passt das?").kandidaten_spec
        == candidate
    )


def test_governed_multiple_media_do_not_reach_any_matrix_path() -> None:
    class MustNotAccessMatrix:
        @property
        def catalog(self):
            raise AssertionError("blocked multi-medium case accessed matrix catalog")

        def query(self, *_args, **_kwargs):
            raise AssertionError("blocked multi-medium case queried matrix")

    pipeline = _pipeline(FakeLlmClient("Antwort"), material_constraints_enabled=True)
    pipeline.matrix = MustNotAccessMatrix()
    result = _run(
        pipeline,
        "Wir verwenden NBR in Mineralöl und Aceton, passt das?",
    )
    assert result.material_constraints is not None
    assert result.material_constraints.evaluation_state.value == "blocked"
    assert result.material_constraints.medium_cardinality.value == "multiple"
    assert result.material_constraints.blockers[0].ref == "medium-cardinality:multiple"
    assert all(fact.kind != "matrix" for fact in result.grounding_facts)
