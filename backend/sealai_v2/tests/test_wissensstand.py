"""P3 Wissensstand-Referenz (audit §4.3 Versionierung, L8) — a per-pipeline knowledge-catalog
identifier, computed once at build_pipeline() time and attached to every PipelineResult/Artifact.
Pure string concatenation of already-loaded seed ``version`` strings; no I/O, no LLM."""

from __future__ import annotations

import asyncio

from sealai_v2.api.serializers import chat_response
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import Answer, Flags, PipelineResult
from sealai_v2.core.wissensstand import compute_wissensstand
from sealai_v2.pipeline.pipeline import build_pipeline
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient

_T = TenantContext("t1")


# --- compute_wissensstand() — pure ---------------------------------------------------------


def test_all_five_present_in_fixed_order():
    s = compute_wissensstand(
        fachkarten_version="fk_v1",
        matrix_version="mx_v1",
        traps_version="trap_v1",
        calc_version="calc_v1",
        versagensmodi_version="vm_v1",
    )
    assert s == "fk:fk_v1|mx:mx_v1|trap:trap_v1|calc:calc_v1|vm:vm_v1"


def test_missing_catalogs_are_omitted_not_padded():
    s = compute_wissensstand(fachkarten_version="fk_v1", versagensmodi_version="vm_v1")
    assert s == "fk:fk_v1|vm:vm_v1"


def test_all_absent_yields_empty_string():
    assert compute_wissensstand() == ""


def test_order_is_fixed_regardless_of_kwarg_order():
    a = compute_wissensstand(matrix_version="m", fachkarten_version="f")
    b = compute_wissensstand(fachkarten_version="f", matrix_version="m")
    assert a == b == "fk:f|mx:m"


# --- build_pipeline() wiring ----------------------------------------------------------------


def test_default_pipeline_omits_the_unmigrated_matrix_catalog():
    p = build_pipeline(Settings(), FakeLlmClient("x"))
    assert (
        p.wissensstand
    )  # non-empty by default (ground_enabled + verify_enabled both True)
    for label in ("fk:", "trap:", "calc:", "vm:"):
        assert label in p.wissensstand
    assert "mx:" not in p.wissensstand


def test_wissensstand_matches_the_loaded_catalog_versions():
    p = build_pipeline(Settings(), FakeLlmClient("x"))
    assert f"fk:{p.retriever.catalog.version}" in p.wissensstand
    assert p.matrix is None
    assert f"trap:{p.catalog.version}" in p.wissensstand
    assert f"calc:{p.engine.registry.version}" in p.wissensstand
    assert f"vm:{p.versagensmodi.catalog.version}" in p.wissensstand


def test_evidence_migration_flag_wires_matrix_version_explicitly():
    p = build_pipeline(Settings(compatibility_matrix_enabled=True), FakeLlmClient("x"))

    assert p.matrix is not None
    assert f"mx:{p.matrix.catalog.version}" in p.wissensstand


def test_ground_disabled_drops_fk_mx_vm_but_keeps_trap_and_calc():
    p = build_pipeline(Settings(ground_enabled=False), FakeLlmClient("x"))
    assert p.retriever is None and p.matrix is None and p.versagensmodi is None
    assert "fk:" not in p.wissensstand
    assert "mx:" not in p.wissensstand
    assert "vm:" not in p.wissensstand
    assert "trap:" in p.wissensstand  # verify_enabled still True by default
    assert "calc:" in p.wissensstand  # compute_enabled remains True


def test_verify_disabled_drops_trap_only():
    p = build_pipeline(Settings(verify_enabled=False), FakeLlmClient("x"))
    assert p.catalog is None
    assert "trap:" not in p.wissensstand
    assert "fk:" in p.wissensstand  # ground_enabled still True by default
    assert "calc:" in p.wissensstand


# --- PipelineResult attachment (every turn, not flag-gated) ---------------------------------


def test_run_attaches_the_pipeline_wissensstand_to_the_result():
    p = build_pipeline(Settings(), FakeLlmClient("FAKE-ANSWER"))
    result = asyncio.run(p.run("Frage?", tenant=_T, flags=Flags()))
    assert result.wissensstand == p.wissensstand
    assert result.wissensstand  # default settings wire all four catalogs


def test_no_catalogs_wired_yields_empty_result_field():
    p = build_pipeline(
        Settings(ground_enabled=False, verify_enabled=False, compute_enabled=False),
        FakeLlmClient("x"),
    )
    result = asyncio.run(p.run("Frage?", tenant=_T, flags=Flags()))
    assert result.wissensstand == ""


# --- chat_response() serializer --------------------------------------------------------------


def test_chat_response_passes_wissensstand_through_verbatim():
    result = PipelineResult(
        question="q",
        tenant_id="t1",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="…", model="fake"),
        wissensstand="fk:v1|mx:v2|trap:v3|calc:v4|vm:v5",
    )
    assert chat_response(result)["wissensstand"] == "fk:v1|mx:v2|trap:v3|calc:v4|vm:v5"


def test_chat_response_defaults_to_empty_string():
    result = PipelineResult(
        question="q",
        tenant_id="t1",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="…", model="fake"),
    )
    assert chat_response(result)["wissensstand"] == ""
