from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
PROVENANCE = "https://slsa.dev/provenance/v1"
SPDX = "https://spdx.dev/Document/v2.3"
IMAGE_NAME = "ghcr.io/jungt72/sealai-backend-v2"
DIGEST = "sha256:" + "a" * 64
REVISION = "b" * 40
WORKFLOW = ".github/workflows/build-and-push.yml"
VERIFY_SCRIPT = REPO / "ops" / "verify-image-attestations.sh"


def _module():
    spec = importlib.util.spec_from_file_location(
        "verify_attestation_payload", REPO / "ops" / "verify_attestation_payload.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _module()


def _envelope(
    predicate_type: str, *, revision: str = REVISION, digest: str = "a" * 64
) -> str:
    predicate: dict
    if predicate_type == PROVENANCE:
        predicate = {
            "buildDefinition": {
                "externalParameters": {
                    "workflow": {
                        "path": WORKFLOW,
                        "ref": "refs/heads/main",
                        "repository": "https://github.com/jungt72/sealAI",
                    }
                },
                "resolvedDependencies": [
                    {
                        "uri": "git+https://github.com/jungt72/sealAI@refs/heads/main",
                        "digest": {"gitCommit": revision},
                    }
                ],
            }
        }
    else:
        predicate = {
            "spdxVersion": "SPDX-2.3",
            "documentNamespace": "https://example.invalid/sbom",
            "packages": [{"name": "sealai"}],
        }
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": IMAGE_NAME, "digest": {"sha256": digest}}],
        "predicateType": predicate_type,
        "predicate": predicate,
    }
    encoded = base64.b64encode(json.dumps(statement).encode()).decode()
    return json.dumps(
        {"payload": encoded, "payloadType": "application/vnd.in-toto+json"}
    )


def _validate(raw: str, predicate_type: str):
    return MODULE.validate_attestations(
        raw,
        image_name=IMAGE_NAME,
        image_digest=DIGEST,
        predicate_type=predicate_type,
        expected_revision=REVISION,
        repository="jungt72/sealAI",
        workflow_path=WORKFLOW,
    )


def test_accepts_revision_bound_provenance():
    result = _validate(_envelope(PROVENANCE), PROVENANCE)
    assert result["revision"] == REVISION


def test_shell_gate_is_token_free_digest_pinned_and_checks_both_predicates():
    script = VERIFY_SCRIPT.read_text(encoding="utf-8")
    assert "cosign/cosign:v3.1.1@sha256:" in script
    assert "GH_TOKEN" not in script
    assert "GITHUB_TOKEN" not in script
    assert "--certificate-identity" in script
    assert PROVENANCE in script
    assert SPDX in script


def test_accepts_nonempty_spdx_23_sbom():
    result = _validate(_envelope(SPDX), SPDX)
    assert result["predicate_type"] == SPDX


@pytest.mark.parametrize(
    ("raw", "predicate_type"),
    [
        (_envelope(PROVENANCE, revision="c" * 40), PROVENANCE),
        (_envelope(PROVENANCE, digest="d" * 64), PROVENANCE),
        (_envelope(SPDX, digest="d" * 64), SPDX),
    ],
)
def test_rejects_mismatched_revision_or_subject(raw: str, predicate_type: str):
    with pytest.raises(MODULE.AttestationPayloadError):
        _validate(raw, predicate_type)


def test_rejects_empty_spdx_package_inventory():
    raw = _envelope(SPDX)
    envelope = json.loads(raw)
    statement = json.loads(base64.b64decode(envelope["payload"]))
    statement["predicate"]["packages"] = []
    envelope["payload"] = base64.b64encode(json.dumps(statement).encode()).decode()
    with pytest.raises(MODULE.AttestationPayloadError):
        _validate(json.dumps(envelope), SPDX)
