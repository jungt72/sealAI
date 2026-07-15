#!/usr/bin/env python3
"""Validate the signed in-toto payload emitted by ``cosign verify-attestation``.

Cosign establishes certificate, transparency-log, and signature validity. This
module then binds the verified statement to sealingAI's expected image subject,
source revision, workflow, repository, and predicate contract.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
from pathlib import Path


class AttestationPayloadError(ValueError):
    pass


SCAN_PREDICATE_TYPE = "https://sealingai.com/attestations/trivy-scan/v1"


def _json_objects(raw: str) -> list[dict]:
    raw = raw.strip()
    if not raw:
        raise AttestationPayloadError("empty cosign output")
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        decoded = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if isinstance(decoded, dict):
        decoded = [decoded]
    if not isinstance(decoded, list) or not all(
        isinstance(item, dict) for item in decoded
    ):
        raise AttestationPayloadError(
            "cosign output must contain JSON envelope objects"
        )
    return decoded


def _statement(envelope: dict) -> dict:
    encoded = envelope.get("payload")
    if not isinstance(encoded, str) or not encoded:
        raise AttestationPayloadError("DSSE envelope has no payload")
    try:
        payload = base64.b64decode(encoded, validate=True)
        statement = json.loads(payload)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AttestationPayloadError("DSSE payload is not valid base64 JSON") from exc
    if not isinstance(statement, dict):
        raise AttestationPayloadError("in-toto statement must be an object")
    return statement


def _subject_matches(statement: dict, image_name: str, image_digest: str) -> bool:
    algorithm, separator, value = image_digest.partition(":")
    if separator != ":" or not algorithm or not value:
        raise AttestationPayloadError("image digest must be algorithm:hex")
    return any(
        isinstance(subject, dict)
        and subject.get("name") == image_name
        and (subject.get("digest") or {}).get(algorithm) == value
        for subject in statement.get("subject") or []
    )


def _validate_provenance(
    statement: dict,
    *,
    expected_revision: str,
    repository: str,
    workflow_path: str,
) -> None:
    predicate = statement.get("predicate") or {}
    definition = predicate.get("buildDefinition") or {}
    external = definition.get("externalParameters") or {}
    workflow = external.get("workflow") or {}
    expected_repository = f"https://github.com/{repository}"
    expected = {
        "path": workflow_path,
        "ref": "refs/heads/main",
        "repository": expected_repository,
    }
    if any(workflow.get(key) != value for key, value in expected.items()):
        raise AttestationPayloadError(
            "provenance workflow identity does not match main"
        )

    dependencies = definition.get("resolvedDependencies") or []
    if not any(
        isinstance(item, dict)
        and item.get("uri") == f"git+{expected_repository}@refs/heads/main"
        and (item.get("digest") or {}).get("gitCommit") == expected_revision
        for item in dependencies
    ):
        raise AttestationPayloadError(
            "provenance does not bind the expected source revision"
        )


def _validate_spdx(statement: dict) -> None:
    predicate = statement.get("predicate") or {}
    if predicate.get("spdxVersion") != "SPDX-2.3":
        raise AttestationPayloadError("SBOM is not SPDX-2.3")
    if not predicate.get("documentNamespace"):
        raise AttestationPayloadError("SPDX SBOM has no document namespace")
    if not isinstance(predicate.get("packages"), list) or not predicate["packages"]:
        raise AttestationPayloadError("SPDX SBOM contains no packages")


def _validate_scan(
    statement: dict,
    *,
    image_name: str,
    image_digest: str,
    expected_revision: str,
    expected_tree_hash: str,
    policy_sha256: str | None,
    exceptions_sha256: str | None,
) -> None:
    predicate = statement.get("predicate") or {}
    expected_keys = {
        "schema_version",
        "artifact",
        "scanner",
        "source",
        "scope",
        "result",
        "report_sha256",
        "policy_sha256",
        "exceptions_sha256",
    }
    if set(predicate) != expected_keys or predicate.get("schema_version") != 2:
        raise AttestationPayloadError("scan predicate schema is invalid")
    scanner = predicate.get("scanner") or {}
    if scanner != {
        "license_confidence_level": 0.9,
        "license_full_scan": True,
        "name": "trivy",
        "version": "0.69.3",
    }:
        raise AttestationPayloadError("scan predicate uses an unapproved scanner")
    if predicate.get("artifact") != {
        "digest": image_digest,
        "name": image_name,
        "type": "container_image",
    }:
        raise AttestationPayloadError("scan predicate does not bind the image")
    if predicate.get("source") != {
        "git_sha": expected_revision,
        "tree_hash": expected_tree_hash,
    }:
        raise AttestationPayloadError("scan predicate does not bind the source tree")
    if (
        predicate.get("scope") != "backend-v2-image"
        or predicate.get("result") != "pass"
    ):
        raise AttestationPayloadError("image scan did not record a policy pass")
    for key in ("report_sha256", "policy_sha256", "exceptions_sha256"):
        value = predicate.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise AttestationPayloadError("scan predicate contains an invalid digest")
    if not policy_sha256 or predicate.get("policy_sha256") != policy_sha256:
        raise AttestationPayloadError("scan predicate policy digest does not match")
    if not exceptions_sha256 or predicate.get("exceptions_sha256") != exceptions_sha256:
        raise AttestationPayloadError("scan predicate exception digest does not match")


def validate_attestations(
    raw: str,
    *,
    image_name: str,
    image_digest: str,
    predicate_type: str,
    expected_revision: str,
    repository: str,
    workflow_path: str,
    expected_tree_hash: str,
    policy_sha256: str | None = None,
    exceptions_sha256: str | None = None,
) -> dict:
    errors: list[str] = []
    for envelope in _json_objects(raw):
        try:
            statement = _statement(envelope)
            if statement.get("_type") != "https://in-toto.io/Statement/v1":
                raise AttestationPayloadError("unexpected in-toto statement version")
            if statement.get("predicateType") != predicate_type:
                raise AttestationPayloadError("unexpected predicate type")
            if not _subject_matches(statement, image_name, image_digest):
                raise AttestationPayloadError(
                    "attestation subject does not match image digest"
                )
            if predicate_type == "https://slsa.dev/provenance/v1":
                _validate_provenance(
                    statement,
                    expected_revision=expected_revision,
                    repository=repository,
                    workflow_path=workflow_path,
                )
            elif predicate_type == "https://spdx.dev/Document/v2.3":
                _validate_spdx(statement)
            elif predicate_type == SCAN_PREDICATE_TYPE:
                _validate_scan(
                    statement,
                    image_name=image_name,
                    image_digest=image_digest,
                    expected_revision=expected_revision,
                    expected_tree_hash=expected_tree_hash,
                    policy_sha256=policy_sha256,
                    exceptions_sha256=exceptions_sha256,
                )
            else:
                raise AttestationPayloadError("predicate type is not approved")
            return {
                "image_name": image_name,
                "image_digest": image_digest,
                "predicate_type": predicate_type,
                "revision": expected_revision,
                "workflow_path": workflow_path,
            }
        except AttestationPayloadError as exc:
            errors.append(str(exc))
    raise AttestationPayloadError("no matching attestation: " + "; ".join(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("envelope_file", type=Path)
    parser.add_argument("--image-name", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--predicate-type", required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--expected-tree-hash", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--policy-sha256")
    parser.add_argument("--exceptions-sha256")
    args = parser.parse_args()
    try:
        result = validate_attestations(
            args.envelope_file.read_text(encoding="utf-8"),
            image_name=args.image_name,
            image_digest=args.image_digest,
            predicate_type=args.predicate_type,
            expected_revision=args.expected_revision,
            expected_tree_hash=args.expected_tree_hash,
            repository=args.repository,
            workflow_path=args.workflow_path,
            policy_sha256=args.policy_sha256,
            exceptions_sha256=args.exceptions_sha256,
        )
    except (OSError, json.JSONDecodeError, AttestationPayloadError) as exc:
        parser.exit(2, f"attestation payload verification failed: {exc}\n")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
