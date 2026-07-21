"""GATE-10 P1 phase 2: backend_image_digest provenance verification.

Unlike the phase 1 source-derived hashes (test_gate10_artifact_binding.py), this
cannot be verified by local recomputation -- it genuinely needs Docker + network to
reach Sigstore/Rekor. These tests therefore monkeypatch subprocess.run (same pattern
as test_gate08_root_bootstrap.py uses for its own unavailable-in-CI system
dependency) instead of hitting the real transparency log.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
OPS = REPO / "ops"
sys.path.insert(0, str(OPS))

import production_release_gate as gate  # noqa: E402


VALID_DIGEST = "sha256:" + "a" * 64
SOURCE_SHA = "b" * 40


def test_rejects_malformed_digest_before_shelling_out(monkeypatch):
    calls: list[object] = []
    monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: calls.append(a))

    with pytest.raises(gate.GateConfigurationError, match="backend_image_digest"):
        gate._verify_backend_image_attestation("not-a-digest", SOURCE_SHA)

    assert (
        calls == []
    ), "must fail closed on bad input without ever invoking the verifier"


def test_calls_verify_script_with_exact_expected_arguments(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(gate.subprocess, "run", fake_run)

    gate._verify_backend_image_attestation(VALID_DIGEST, SOURCE_SHA)

    cmd = captured["cmd"]
    assert cmd[0] == "/bin/bash"
    assert cmd[1] == "-p"
    assert cmd[2].endswith("verify-image-attestations.sh")
    assert cmd[3] == f"ghcr.io/jungt72/sealai-backend-v2@{VALID_DIGEST}"
    assert cmd[4] == SOURCE_SHA
    assert cmd[5] == ".github/workflows/build-and-push.yml"
    assert captured["kwargs"]["check"] is False


def test_fails_closed_when_attestation_script_exits_nonzero(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 1, stdout="", stderr="Error: no matching attestations"
        )

    monkeypatch.setattr(gate.subprocess, "run", fake_run)

    with pytest.raises(
        gate.GateConfigurationError,
        match="backend_image_digest failed provenance/SBOM attestation verification",
    ):
        gate._verify_backend_image_attestation(VALID_DIGEST, SOURCE_SHA)


def test_passes_through_when_attestation_script_exits_zero(monkeypatch):
    monkeypatch.setattr(
        gate.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
    )
    gate._verify_backend_image_attestation(VALID_DIGEST, SOURCE_SHA)  # must not raise


def test_registry_only_covers_backend_for_now():
    """frontend_image_digest has no attested build workflow yet (build-and-push.yml
    only builds backend-v2) -- documents that boundary so it doesn't silently expand
    or silently stay missing without anyone noticing."""

    assert set(gate._IMAGE_ATTESTATION_HASH_VERIFIERS) == {"backend_image_digest"}


def test_verify_image_attestation_hashes_passes_claimed_digest_and_source_sha(
    monkeypatch,
):
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(
        gate,
        "_IMAGE_ATTESTATION_HASH_VERIFIERS",
        {
            "backend_image_digest": lambda digest, source_git_sha: seen.append(
                (digest, source_git_sha)
            )
        },
    )

    gate._verify_image_attestation_hashes(
        {"backend_image_digest": VALID_DIGEST}, SOURCE_SHA
    )

    assert seen == [(VALID_DIGEST, SOURCE_SHA)]
