import os
import shutil
import subprocess
from pathlib import Path


def _make_mock_bin(tmp_path: Path) -> str:
    mock_bin = tmp_path / "mockbin"
    mock_bin.mkdir(parents=True, exist_ok=True)

    # Fixed date output for deterministic filenames
    date_script = mock_bin / "date"
    date_script.write_text("#!/bin/bash\necho \"2025-01-02_03-04\"\n", encoding="utf-8")
    date_script.chmod(0o755)

    # Docker mock to satisfy kcadm calls and cp
    docker_script = mock_bin / "docker"
    docker_script.write_text(
        """#!/bin/bash
cmd="$1"
shift
if [[ "$cmd" == "exec" ]]; then
  if printf "%s " "$@" | grep -q "partial-export"; then
    echo '{"realm":"mock-realm"}'
  fi
  exit 0
fi
if [[ "$cmd" == "cp" ]]; then
  src="$1"
  dst="$2"
  src_path="${src#*:}"
  cp "$src_path" "$dst"
  exit 0
fi
echo "Unhandled docker command: $cmd" >&2
exit 1
""",
        encoding="utf-8",
    )
    docker_script.chmod(0o755)

    return str(mock_bin)


def _script_path() -> Path:
    return Path(__file__).resolve().parents[2] / "backup_keycloak.sh"


def test_backup_requires_admin_creds(tmp_path: Path):
    env = {
        "ENV_FILE": "/nonexistent",
        "HOME": str(tmp_path / "home"),
        "KEYCLOAK_REALM": "sealAI",
        "PATH": os.environ.get("PATH", ""),
    }

    result = subprocess.run(
        ["bash", str(_script_path())],
        env=env,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )

    assert result.returncode != 0
    assert "KEYCLOAK_ADMIN" in result.stderr


def test_backup_exports_realm_with_mock_docker(tmp_path: Path):
    mock_bin = _make_mock_bin(tmp_path)
    backup_dir = tmp_path / "exports"
    home_dir = tmp_path / "home"
    home_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)

    env = {
        "ENV_FILE": "/nonexistent",
        "HOME": str(home_dir),
        "TARGET_DIR": str(backup_dir),
        "KEYCLOAK_REALM": "realm1",
        "KEYCLOAK_ADMIN": "admin",
        "KEYCLOAK_ADMIN_PASSWORD": "pw",
        "PATH": f"{mock_bin}:{os.environ.get('PATH', '')}",
    }

    result = subprocess.run(
        ["bash", str(_script_path())],
        env=env,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    )

    assert result.returncode == 0, result.stderr
    expected_file = backup_dir / "realm1-realm-2025-01-02_03-04.json"
    assert expected_file.exists(), "backup file not created"
    assert "mock-realm" in expected_file.read_text(), "backup content not copied"

    shutil.rmtree(backup_dir, ignore_errors=True)
