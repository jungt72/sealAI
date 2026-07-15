from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_staging_build_wrapper_gates_and_leases_before_compose_up() -> None:
    wrapper = ROOT / "ops" / "staging" / "up-staging-v2.sh"
    content = wrapper.read_text(encoding="utf-8")

    rc_helper = content.index('source "${REPO_ROOT}/ops/staging/rc-contract.sh"')
    rc_load = content.index('rc_contract_load "${REPO_ROOT}" staging')
    checkout_guard = content.index("rc_contract_assert_nonproduction_checkout")
    tls_validation = content.index("rc_contract_assert_tls_fixtures")
    helper = content.index("production-release-gate-check.sh")
    gate = content.index("production_release_gate_check", helper)
    approved_source_binding = content.index("rc_contract_bind_approved_source", gate)
    served_tree_binding = content.index("rc_contract_assert_served_tree_binding", gate)
    installed_lease = content.index(
        "STORAGE_LEASE=/usr/local/libexec/sealai/production-storage-lease.sh"
    )
    lease_validation = content.index("installed_storage_lease_unsafe")
    lease_source = content.index('source "${STORAGE_LEASE}"')
    lease_acquisition = content.index("\nacquire_production_storage_lease\n")
    snapshot_validation = content.index("rc_contract_assert_snapshot_volumes")
    compose_build = content.index('"${COMPOSE[@]}" build backend-v2-staging')
    post_build_tree_validation = content.index("POST_BUILD_TREE_HASH")
    immutable_image = content.index('readonly IMAGE_ID="$(', post_build_tree_validation)
    immutable_up_binding = content.index('"RC_BACKEND_IMAGE=${IMAGE_ID}"')
    compose_up = content.index("up -d --no-build")

    assert content.startswith("#!/bin/bash -p\n")
    assert wrapper.stat().st_mode & 0o111
    assert "readonly PATH=" in content
    assert "/usr/bin/docker compose" in content
    assert "eval " not in content
    assert ".env.prod" not in content
    assert "sealai_default" not in content
    assert "/usr/bin/env -i" in content
    assert "COMPOSE_DISABLE_ENV_FILE=1" in content
    assert '--env-file "${RC_ENV_FILE}"' in content
    assert 'SOURCE_PARENT_GIT_SHA="$(/usr/bin/git rev-parse HEAD^)"' in content
    assert 'readonly RC_GIT_SHA="${RC_APPROVED_SOURCE_SHA}"' in content
    assert '"RC_GIT_SHA=${RC_GIT_SHA}"' in content
    assert 'build "${GATE_CONTROL_GIT_SHA}"' not in content
    assert (
        installed_lease
        < rc_helper
        < rc_load
        < checkout_guard
        < tls_validation
        < helper
        < gate
        < approved_source_binding
        < served_tree_binding
        < lease_validation
        < lease_source
        < lease_acquisition
        < snapshot_validation
        < compose_build
        < post_build_tree_validation
        < immutable_image
        < immutable_up_binding
        < compose_up
    )


def test_staging_and_cutover_docs_do_not_recommend_raw_compose_build_up() -> None:
    staging_compose = (
        ROOT / "ops" / "staging" / "docker-compose.staging.yml"
    ).read_text(encoding="utf-8")
    runbook = (ROOT / "docs" / "ops" / "RUNBOOK_V2_CUTOVER.md").read_text(
        encoding="utf-8"
    )

    assert "./ops/staging/up-staging-v2.sh" in staging_compose
    assert "./ops/staging/up-staging-v2.sh" in runbook
    assert "up -d --build" not in staging_compose
    assert "up -d --build" not in runbook
    assert "./ops/release-backend-v2.sh --final" in runbook
    assert "this step stays deliberately blocked" in runbook

    production_phase = runbook.split("## Phase 3", 1)[1]
    assert "$COMPOSE up" not in production_phase
    assert "docker stop backend-v2" not in production_phase
    assert "frontend-v2/dist" not in production_phase
    assert "There is currently no sanctioned production entrypoint" in production_phase
    assert "do not recreate Nginx manually" in production_phase
