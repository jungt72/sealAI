"""Release-stage contract for the V2 deployment wrapper and production CI."""

from __future__ import annotations

import pathlib
import subprocess


REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "ops" / "release-backend-v2.sh"
WORKFLOW = REPO / ".github" / "workflows" / "deploy.yml"


def test_release_wrapper_documents_explicit_stages():
    result = subprocess.run(
        ["bash", str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--candidate" in result.stdout
    assert "--final" in result.stdout
    assert "default" in result.stdout.lower()


def test_final_is_fail_closed_and_candidate_is_auditable():
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'RELEASE_STAGE="final"' in script
    assert 'if [[ "${RELEASE_STAGE}" == "final" ]]' in script
    assert "python ops/v2_deploy_gate.py" in script
    assert 'EVAL_STATUS="pending"' in script
    assert '"release_stage": release_stage' in script
    assert '"eval_status": eval_status' in script


def test_candidate_is_forbidden_for_production_configuration():
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'DEPLOY_ENV="${DEPLOY_ENV:-production}"' in script
    assert "development|test|staging" in script
    assert "candidate releases are forbidden" in script


def test_running_rollback_artifact_is_preserved_before_local_build():
    script = SCRIPT.read_text(encoding="utf-8")

    preserve = script.index('ROLLBACK_HOLD_TAG="sealai-backend-v2:rollback-hold-')
    build = script.index('build --build-arg "GATE_TREE_HASH=${TREE_HASH}"')
    assert preserve < build
    assert 'docker tag "${ROLLBACK_SOURCE}" "${ROLLBACK_HOLD_TAG}"' in script
    assert "Never `docker commit`" in script
    assert "\ndocker commit " not in script


def test_missing_running_image_requires_identity_matched_override():
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'ROLLBACK_IMAGE_OVERRIDE="${SEALAI_V2_ROLLBACK_IMAGE:-}"' in script
    assert '"${OVERRIDE_REVISION}" == "${RUNNING_REVISION}"' in script
    assert '"${OVERRIDE_TREE_HASH}" == "${RUNNING_TREE_HASH}"' in script
    assert "build_identity verify" in script
    assert (
        "docker image inspect --format '{{.Id}}' \"${LOCAL_BACKEND_IMAGE}\"" in script
    )


def test_production_ci_is_manual_and_final_only():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "workflow_run:" not in workflow
    assert "release_stage:" not in workflow
    assert "--final" in workflow
    assert "--candidate" not in workflow
