from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_staging_build_wrapper_gates_and_leases_before_compose_up() -> None:
    wrapper = ROOT / "ops" / "staging" / "up-staging-v2.sh"
    content = wrapper.read_text(encoding="utf-8")

    helper = content.index("production-release-gate-check.sh")
    gate = content.index("production_release_gate_check", helper)
    installed_lease = content.index(
        "STORAGE_LEASE=/usr/local/libexec/sealai/production-storage-lease.sh"
    )
    lease_validation = content.index("installed_storage_lease_unsafe")
    lease_source = content.index('source "${STORAGE_LEASE}"')
    lease_acquisition = content.index("\nacquire_production_storage_lease\n")
    tree_hash = content.index('TREE_HASH="$(/bin/bash -p ops/tree-hash.sh)"')
    compose_build = content.index('"${COMPOSE[@]}" build')
    build_arg_tree_hash = content.index('--build-arg "GATE_TREE_HASH=${TREE_HASH}"')
    build_arg_git_sha = content.index('--build-arg "SOURCE_GIT_SHA=${GIT_SHA}"')
    compose_up = content.index('exec "${COMPOSE[@]}" up -d')

    assert content.startswith("#!/bin/bash -p\n")
    assert wrapper.stat().st_mode & 0o111
    assert "readonly PATH=" in content
    assert "/usr/bin/docker compose" in content
    assert "eval " not in content
    assert "up -d --build" not in content
    assert (
        installed_lease
        < helper
        < gate
        < lease_validation
        < lease_source
        < lease_acquisition
        < tree_hash
        < compose_build
        < build_arg_tree_hash
        < compose_up
    )
    assert build_arg_git_sha < compose_up
    assert compose_build < build_arg_git_sha


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
