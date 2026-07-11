"""Release-stage contract for the V2 deployment wrapper.

Candidate deployments may defer the paid replay while final releases remain
fail-closed. These tests are intentionally network- and Docker-free.
"""

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


def test_ci_uses_candidate_for_iteration_and_requires_explicit_final():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "default: candidate" in workflow
    assert "- final" in workflow
    assert '"--$RELEASE_STAGE"' in workflow
