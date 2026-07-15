from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "ops" / "staging" / "rc-contract.sh"
COMPOSE = ROOT / "ops" / "staging" / "docker-compose.staging.yml"
RUN_EVAL = ROOT / "ops" / "run_eval.sh"
WRAPPER = ROOT / "ops" / "staging" / "up-staging-v2.sh"

_A = "1" * 64
_B = "2" * 64
_C = "3" * 64


def _valid_contract(*, staging: bool = False) -> str:
    values = [
        "SEALAI_RC_MODE=isolated-nonprod",
        "RC_DATA_SEED_STATUS=READY",
        "RC_POSTGRES_PASSWORD=rcOnlyCredentialValue12345",
        f"RC_POSTGRES_SNAPSHOT_SHA256={_A}",
        f"RC_QDRANT_SNAPSHOT_SHA256={_B}",
        f"RC_AUTHORITY_EPOCH=sha256:{_C}",
        "RC_QDRANT_COLLECTION=sealai_rc_knowledge_fixture",
        "RC_QDRANT_MEMORY_COLLECTION=sealai_rc_memory_fixture",
        f"RC_POSTGRES_IMAGE=docker.io/library/postgres:16.11@sha256:{_A}",
        f"RC_QDRANT_IMAGE=docker.io/qdrant/qdrant:v1.16.0@sha256:{_B}",
        "RC_STUB_PROVIDER_STATUS=READY",
        f"RC_LLM_STUB_IMAGE=localhost/sealai-rc-llm-stub:v1@sha256:{_C}",
    ]
    if staging:
        values.extend(
            [
                "RC_WEB_STUB_STATUS=READY",
                "RC_TLS_FIXTURE_STATUS=READY",
                f"RC_NGINX_IMAGE=docker.io/library/nginx:1.29.4@sha256:{_A}",
                f"RC_AUTH_STUB_IMAGE=localhost/sealai-rc-auth-stub:v1@sha256:{_B}",
                f"RC_FRONTEND_STUB_IMAGE=localhost/sealai-rc-frontend-stub:v1@sha256:{_C}",
            ]
        )
    return "\n".join(values) + "\n"


def _run_contract(
    tmp_path: Path,
    content: str,
    *,
    inherited: dict[str, str] | None = None,
    file_mode: int = 0o600,
    mode: str = "eval",
) -> subprocess.CompletedProcess[str]:
    repo = tmp_path / "repo"
    staging = repo / "ops" / "staging"
    staging.mkdir(parents=True)
    env_file = staging / "rc.env"
    env_file.write_text(content, encoding="utf-8")
    env_file.chmod(file_mode)
    command = (
        f'source "{CONTRACT}"; '
        f'rc_contract_load "{repo}" "{mode}" && '
        "printf contract-valid"
    )
    env = {
        "HOME": str(tmp_path),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    }
    env.update(inherited or {})
    return subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-p", "-c", command],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _replace_line(content: str, key: str, replacement: str | None) -> str:
    lines = [line for line in content.splitlines() if not line.startswith(f"{key}=")]
    if replacement is not None:
        lines.append(f"{key}={replacement}")
    return "\n".join(lines) + "\n"


def test_rc_contract_accepts_only_complete_nonproduction_literal_input(
    tmp_path: Path,
) -> None:
    # Construct the redaction canary from inert fragments so the repository's
    # own secret scanner does not mistake a test-only value for a credential.
    secret = "rcOnlyCredential" + "Value12345"
    result = _run_contract(tmp_path, _valid_contract())

    assert result.returncode == 0, result.stderr
    assert result.stdout == "contract-valid"
    assert secret not in result.stderr


@pytest.mark.parametrize(
    ("content", "reason", "key"),
    [
        (
            _replace_line(_valid_contract(), "RC_QDRANT_SNAPSHOT_SHA256", None),
            "missing_or_empty_key",
            "RC_QDRANT_SNAPSHOT_SHA256",
        ),
        (
            _replace_line(_valid_contract(), "RC_AUTHORITY_EPOCH", None),
            "missing_or_empty_key",
            "RC_AUTHORITY_EPOCH",
        ),
        (
            _replace_line(_valid_contract(), "RC_DATA_SEED_STATUS", "BLOCKED_EXTERNAL"),
            "blocked_external",
            "RC_DATA_SEED_STATUS",
        ),
        (
            _replace_line(_valid_contract(), "RC_POSTGRES_PASSWORD", ""),
            "missing_or_empty_key",
            "RC_POSTGRES_PASSWORD",
        ),
        (
            _replace_line(_valid_contract(), "RC_POSTGRES_SNAPSHOT_SHA256", "0" * 64),
            "invalid_sha256",
            "RC_POSTGRES_SNAPSHOT_SHA256",
        ),
        (
            _replace_line(
                _valid_contract(), "RC_AUTHORITY_EPOCH", f"sha256:{'0' * 64}"
            ),
            "invalid_sha256",
            "RC_AUTHORITY_EPOCH",
        ),
        (
            _replace_line(
                _valid_contract(), "RC_AUTHORITY_EPOCH", f"sha256:{'A' * 64}"
            ),
            "invalid_sha256",
            "RC_AUTHORITY_EPOCH",
        ),
        (
            _replace_line(
                _valid_contract(), "RC_QDRANT_COLLECTION", "sealai_v2_knowledge_v1"
            ),
            "invalid_rc_collection",
            "RC_QDRANT_COLLECTION",
        ),
        (
            _replace_line(
                _valid_contract(),
                "RC_LLM_STUB_IMAGE",
                "ghcr.io/example/production-provider:latest",
            ),
            "invalid_immutable_image",
            "RC_LLM_STUB_IMAGE",
        ),
        (
            _valid_contract() + "OPENAI_API_KEY=must-not-enter-rc\n",
            "forbidden_key",
            "OPENAI_API_KEY",
        ),
    ],
)
def test_rc_contract_fails_closed_without_echoing_values(
    tmp_path: Path, content: str, reason: str, key: str
) -> None:
    result = _run_contract(tmp_path, content)

    assert result.returncode == 78
    assert reason in result.stderr
    assert key in result.stderr
    assert "must-not-enter-rc" not in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    "name",
    [
        "OPENAI_API_KEY",
        "MISTRAL_API_KEY",
        "DATABASE_URL",
        "SEALAI_V2_QDRANT_URL",
        "DOCKER_HOST",
        "COMPOSE_FILE",
    ],
)
def test_rc_contract_rejects_inherited_prod_or_target_environment(
    tmp_path: Path, name: str
) -> None:
    marker = "do-not-print-this-value"
    result = _run_contract(tmp_path, _valid_contract(), inherited={name: marker})

    assert result.returncode == 78
    assert "inherited_forbidden_variable" in result.stderr
    assert name in result.stderr
    assert marker not in result.stderr


def test_rc_contract_rejects_group_readable_or_symlinked_file(tmp_path: Path) -> None:
    permissive = _run_contract(
        tmp_path / "permissive", _valid_contract(), file_mode=0o640
    )
    assert permissive.returncode == 78
    assert "unsafe_contract_mode" in permissive.stderr

    repo = tmp_path / "linked" / "repo"
    staging = repo / "ops" / "staging"
    staging.mkdir(parents=True)
    target = tmp_path / "linked" / "real.env"
    target.write_text(_valid_contract(), encoding="utf-8")
    target.chmod(0o600)
    (staging / "rc.env").symlink_to(target)
    result = subprocess.run(
        [
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-p",
            "-c",
            f'source "{CONTRACT}"; rc_contract_load "{repo}" eval',
        ],
        cwd=repo,
        env={
            "HOME": str(tmp_path),
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 78
    assert "unsafe_contract_file" in result.stderr


def test_rc_source_binding_accepts_parent_and_rejects_gate_control_head(
    tmp_path: Path,
) -> None:
    gate_control = "a" * 40
    source_parent = "b" * 40
    base_command = f'source "{CONTRACT}"; '
    env = {
        "HOME": str(tmp_path),
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    }

    accepted = subprocess.run(
        [
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-p",
            "-c",
            base_command
            + f'rc_contract_bind_approved_source "{gate_control}" '
            + f'"{source_parent}" "{source_parent}"; '
            + 'printf %s "${RC_APPROVED_SOURCE_SHA}"',
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert accepted.returncode == 0, accepted.stderr
    assert accepted.stdout == source_parent

    rejected = subprocess.run(
        [
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-p",
            "-c",
            base_command
            + f'rc_contract_bind_approved_source "{gate_control}" '
            + f'"{source_parent}" "{gate_control}"',
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode == 78
    assert "approved_source_mismatch" in rejected.stderr
    assert rejected.stdout == ""


@pytest.mark.parametrize(
    "checkout",
    ["/home/thorsten/sealai", "/home/thorsten/sealai/worktrees/release-candidate"],
)
def test_rc_contract_rejects_known_production_checkout(checkout: str) -> None:
    result = subprocess.run(
        [
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-p",
            "-c",
            f'source "{CONTRACT}"; '
            f'rc_contract_assert_nonproduction_canonical_path "{checkout}"',
        ],
        env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 78
    assert "production_checkout_forbidden" in result.stderr
    assert result.stdout == ""


def test_rc_contract_accepts_control_only_commit_and_rejects_dirty_served_tree(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "backend" / "sealai_v2").mkdir(parents=True)
    (repo / "ops").mkdir()
    served_files = {
        "backend/sealai_v2/app.py": "VALUE = 1\n",
        "backend/requirements-v2.txt": "example==1.0\n",
        "backend/.dockerignore": "__pycache__\n",
        "backend/Dockerfile.v2": "FROM scratch\n",
        "backend/docker-entrypoint-v2.sh": "#!/bin/sh\n",
    }
    for relative, content in served_files.items():
        (repo / relative).write_text(content, encoding="utf-8")
    subprocess.run(["/usr/bin/git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["/usr/bin/git", "-C", str(repo), "config", "user.email", "rc@test.invalid"],
        check=True,
    )
    subprocess.run(
        ["/usr/bin/git", "-C", str(repo), "config", "user.name", "RC Test"],
        check=True,
    )
    subprocess.run(["/usr/bin/git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        ["/usr/bin/git", "-C", str(repo), "commit", "-qm", "source"],
        check=True,
    )
    source_sha = subprocess.check_output(
        ["/usr/bin/git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    (repo / "ops" / "gate-control.txt").write_text("gate\n", encoding="utf-8")
    subprocess.run(["/usr/bin/git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        ["/usr/bin/git", "-C", str(repo), "commit", "-qm", "gate control"],
        check=True,
    )
    command = (
        f'source "{CONTRACT}"; '
        f'rc_contract_assert_served_tree_binding "{repo}" "{source_sha}"'
    )
    env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}

    clean = subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-p", "-c", command],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert clean.returncode == 0, clean.stderr

    (repo / "backend" / "sealai_v2" / "app.py").write_text(
        "VALUE = 2\n", encoding="utf-8"
    )
    dirty = subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-p", "-c", command],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert dirty.returncode == 78
    assert "dirty_served_tree" in dirty.stderr
    assert "app.py" not in dirty.stderr


def test_rc_compose_has_only_segmented_internal_networks_and_rc_data_paths() -> None:
    text_content = COMPOSE.read_text(encoding="utf-8")
    value = yaml.safe_load(text_content)

    assert set(value["networks"]) == {
        "rc_edge",
        "rc_postgres",
        "rc_qdrant",
        "rc_provider",
    }
    assert all(
        network.get("internal") is True for network in value["networks"].values()
    )
    assert all(
        network.get("external") is not True for network in value["networks"].values()
    )
    assert "sealai_default" not in text_content
    assert ".env.prod" not in text_content

    expected_networks = {
        "nginx-staging": {"rc_edge"},
        "backend-v2-staging": {
            "rc_edge",
            "rc_postgres",
            "rc_qdrant",
            "rc_provider",
        },
        "rc-eval": {"rc_postgres", "rc_qdrant", "rc_provider"},
        "rc-postgres": {"rc_postgres"},
        "rc-qdrant": {"rc_qdrant"},
        "rc-llm-stub": {"rc_provider"},
        "rc-auth-stub": {"rc_edge"},
        "rc-frontend-stub": {"rc_edge"},
    }
    for service_name, expected in expected_networks.items():
        networks = value["services"][service_name]["networks"]
        actual = set(networks) if isinstance(networks, dict) else set(networks)
        assert actual == expected, service_name

    nginx = value["services"]["nginx-staging"]
    assert nginx["ports"] == ["127.0.0.1:8443:443"]
    for service in value["services"].values():
        for mount in service.get("volumes", []):
            source = mount.split(":", 1)[0]
            assert source != "/etc/letsencrypt"
            assert not source.startswith("/var/lib/docker/volumes/")

    for volume_name, volume in value["volumes"].items():
        assert volume["external"] is True, volume_name
        assert volume["name"].startswith("sealai-rc-")


def test_rc_compose_forces_real_retrieval_and_noneligible_local_stub() -> None:
    text_content = COMPOSE.read_text(encoding="utf-8")
    value = yaml.safe_load(text_content)
    environment = value["services"]["rc-eval"]["environment"]

    assert environment["SEALAI_V2_RETRIEVER_BACKEND"] == "qdrant"
    assert "@rc-postgres:5432/sealai_v2_rc" in environment["SEALAI_V2_DATABASE_URL"]
    assert environment["SEALAI_V2_QDRANT_URL"] == "http://rc-qdrant:6333"
    assert environment["QDRANT_URL"] == "http://rc-qdrant:6333"
    assert environment["SEALAI_V2_MISTRAL_BASE_URL"] == "http://rc-llm-stub:8080/v1"
    assert environment["SEALAI_V2_OPENAI_BASE_URL"] == "http://rc-llm-stub:8080/v1"
    assert environment["SEALAI_EVAL_EVIDENCE_CLASS"] == "RC_STUB_NON_ELIGIBLE"
    assert environment["SEALAI_V2_L1_MODEL"] == "rc-stub-noneligible-v1"
    assert environment["SEALAI_V2_KNOWLEDGE_AUTHORITY_EPOCH"] == (
        "${RC_AUTHORITY_EPOCH:?RC authority epoch required by RC contract}"
    )
    assert environment["SEALAI_V2_DATABASE_URL"]
    assert environment["SEALAI_V2_QDRANT_COLLECTION"]

    for forbidden in (
        "${OPENAI_API_KEY",
        "${MISTRAL_API_KEY",
        "${POSTGRES_PASSWORD",
        "${DATABASE_URL",
        "${QDRANT_URL",
    ):
        assert forbidden not in text_content


def test_eval_and_staging_entrypoints_use_only_the_rc_contract() -> None:
    run_eval = RUN_EVAL.read_text(encoding="utf-8")
    wrapper = WRAPPER.read_text(encoding="utf-8")

    assert run_eval.startswith("#!/bin/bash -p\n")
    assert "/bin/bash -p ops/tree-hash.sh" in run_eval
    assert 'rc_contract_load "${REPO_ROOT}" eval' in run_eval
    checkout_guard = run_eval.index("rc_contract_assert_nonproduction_checkout")
    served_tree_guard = run_eval.index("rc_contract_assert_served_tree_binding")
    snapshot_guard = run_eval.index("rc_contract_assert_snapshot_volumes")
    compose_build = run_eval.index('"${COMPOSE[@]}" build rc-eval')
    post_build_tree_guard = run_eval.index("POST_BUILD_TREE_HASH")
    immutable_run_binding = run_eval.index('"RC_BACKEND_IMAGE=${IMAGE_ID}"')
    compose_run = run_eval.index('"${EVAL_COMPOSE[@]}" run --rm --no-deps')
    assert (
        checkout_guard
        < served_tree_guard
        < snapshot_guard
        < compose_build
        < post_build_tree_guard
        < immutable_run_binding
        < compose_run
    )
    assert "rc_contract_assert_snapshot_volumes" in run_eval
    assert "/usr/bin/env -i" in run_eval
    assert "COMPOSE_DISABLE_ENV_FILE=1" in run_eval
    assert '--env-file "${RC_ENV_FILE}"' in run_eval
    assert "docker-compose.staging.yml" in run_eval
    assert "--no-deps" in run_eval
    assert 'retriever_backend != "qdrant"' in run_eval
    assert "Postgres snapshot is empty" in run_eval
    assert "Qdrant knowledge collection is empty" in run_eval
    assert "RC_STUB_NON_ELIGIBLE" in run_eval

    for content in (run_eval, wrapper):
        assert ".env.prod" not in content
        assert "sealai_default" not in content
        assert "docker-compose.yml" not in content
        assert "SEALAI_V2_DATABASE_URL=" not in content
        assert "SEALAI_V2_QDRANT_URL=" not in content


@pytest.mark.parametrize("include_web_inputs", [False, True])
def test_compose_config_renders_without_contacting_the_daemon(
    tmp_path: Path, include_web_inputs: bool
) -> None:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker Compose CLI not installed")
    env_file = tmp_path / "rc.env"
    env_file.write_text(_valid_contract(staging=include_web_inputs), encoding="utf-8")
    env_file.chmod(0o600)
    env = {
        "COMPOSE_DISABLE_ENV_FILE": "1",
        "HOME": os.environ.get("HOME", str(tmp_path)),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "RC_BACKEND_IMAGE": f"sha256:{_A}",
        "RC_TREE_HASH": "a" * 40,
        "RC_GIT_SHA": "b" * 40,
    }
    result = subprocess.run(
        [
            docker,
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(COMPOSE),
            "--profile",
            "rc-eval",
            "config",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "sealai-rc-postgres-net-" in result.stdout
    assert "sealai-rc-qdrant-net-" in result.stdout
    assert "sealai_default" not in result.stdout
