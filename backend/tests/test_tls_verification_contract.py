from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
OPS_ROOT = REPO_ROOT / "ops"
TLS_HELPER = OPS_ROOT / "lib" / "verified-tls.sh"
TLS_SMOKE_SCRIPTS = (
    OPS_ROOT / "check-domain-readiness.sh",
    OPS_ROOT / "smoke-live-pilot-readiness.sh",
    OPS_ROOT / "smoke-v2.sh",
    OPS_ROOT / "stack_smoke.sh",
    OPS_ROOT / "verify_langgraph_v2_sse.sh",
)


def _bash(
    function_call: str,
    *,
    args: tuple[str, ...] = (),
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = f'source "$1"; {function_call}'
    return subprocess.run(
        ["/bin/bash", "-c", command, "tls-contract", str(TLS_HELPER), *args],
        cwd=REPO_ROOT,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )


def test_operational_shell_scripts_have_no_tls_verification_bypass() -> None:
    short_insecure_flag = re.compile(r"(?<![A-Za-z0-9_])-k(?![A-Za-z0-9_])")

    for path in OPS_ROOT.rglob("*.sh"):
        source = path.read_text(encoding="utf-8")
        assert "--insecure" not in source, path
        assert short_insecure_flag.search(source) is None, path


def test_tls_smokes_share_the_verified_client_contract_and_parse() -> None:
    for path in (*TLS_SMOKE_SCRIPTS, TLS_HELPER):
        result = subprocess.run(
            ["/bin/bash", "-n", str(path)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{path}: {result.stderr}"

    for path in TLS_SMOKE_SCRIPTS:
        source = path.read_text(encoding="utf-8")
        assert "lib/verified-tls.sh" in source
        assert "SEALAI_CURL_TLS_ARGS" in source


@pytest.mark.parametrize(
    "origin",
    (
        "http://sealingai.com",
        "https://user@sealingai.com",
        "https://sealingai.com/path",
        "https://sealingai.com?debug=1",
        "https://sealingai.com#fragment",
        "https://sealingai.com:0",
        "https://sealingai.com:65536",
        "https://-bad.sealingai.com",
    ),
)
def test_https_origin_validation_rejects_unsafe_values(origin: str) -> None:
    # Pass the untrusted string as an argument, never as shell source.
    result = _bash('sealai_validate_https_origin "$2" TEST_URL', args=(origin,))
    assert result.returncode != 0


def test_https_origin_validation_accepts_expected_origins() -> None:
    for origin in ("https://sealingai.com", "https://sealingai.com:8443"):
        result = _bash('sealai_validate_https_origin "$2" TEST_URL', args=(origin,))
        assert result.returncode == 0, result.stderr


def test_custom_ca_must_be_safe_and_is_added_to_both_clients(tmp_path: Path) -> None:
    ca_file = tmp_path / "audit-ca.pem"
    ca_file.write_text("synthetic public CA fixture\n", encoding="utf-8")
    result = _bash(
        'sealai_configure_tls_client; [[ " ${SEALAI_CURL_TLS_ARGS[*]} " == *" --cacert $TLS_CA_FILE "* ]]; '
        '[[ " ${SEALAI_OPENSSL_CA_ARGS[*]} " == *" -CAfile $TLS_CA_FILE "* ]]',
        env={"TLS_CA_FILE": str(ca_file)},
    )
    assert result.returncode == 0, result.stderr

    symlink = tmp_path / "linked-ca.pem"
    symlink.symlink_to(ca_file)
    result = _bash("sealai_configure_tls_client", env={"TLS_CA_FILE": str(symlink)})
    assert result.returncode != 0

    result = _bash(
        "sealai_configure_tls_client", env={"TLS_CA_FILE": "relative-ca.pem"}
    )
    assert result.returncode != 0


def test_security_header_contract_is_fail_closed(tmp_path: Path) -> None:
    headers = {
        "hsts": "Strict-Transport-Security: max-age=31536000; includeSubDomains",
        "csp": "Content-Security-Policy: default-src 'self'; object-src 'none'",
        "xcto": "X-Content-Type-Options: nosniff",
        "referrer": "Referrer-Policy: no-referrer",
        "permissions": "Permissions-Policy: geolocation=(), microphone=(), camera=()",
    }
    header_file = tmp_path / "headers.txt"

    header_file.write_text("\r\n".join(headers.values()) + "\r\n", encoding="utf-8")
    result = _bash('sealai_assert_security_headers "$2" true', args=(str(header_file),))
    assert result.returncode == 0, result.stderr

    header_file.write_text(
        "\r\n".join(
            value
            if name != "permissions"
            else "Permissions-Policy: geolocation=(), microphone=(), camera=*"
            for name, value in headers.items()
        )
        + "\r\n",
        encoding="utf-8",
    )
    result = _bash('sealai_assert_security_headers "$2" true', args=(str(header_file),))
    assert result.returncode != 0

    for omitted in headers:
        header_file.write_text(
            "\r\n".join(value for name, value in headers.items() if name != omitted)
            + "\r\n",
            encoding="utf-8",
        )
        result = _bash(
            'sealai_assert_security_headers "$2" true', args=(str(header_file),)
        )
        assert result.returncode != 0, omitted


def test_nginx_security_headers_cover_server_and_dashboard_contexts() -> None:
    default = (REPO_ROOT / "nginx" / "default.conf").read_text(encoding="utf-8")
    dashboard = (REPO_ROOT / "nginx" / "snippets" / "v2_dashboard.conf").read_text(
        encoding="utf-8"
    )
    analytics = (REPO_ROOT / "nginx" / "analytics.rybbit.conf.template").read_text(
        encoding="utf-8"
    )

    assert default.count("add_header Permissions-Policy") == default.count(
        "add_header Referrer-Policy"
    )
    assert default.count(
        'Permissions-Policy "geolocation=(), microphone=(), camera=()" always;'
    ) == default.count("add_header Permissions-Policy")
    for required in (
        "Strict-Transport-Security",
        "Content-Security-Policy",
        "X-Content-Type-Options",
        "Referrer-Policy",
        "Permissions-Policy",
    ):
        assert f"add_header {required}" in dashboard
    for source in (dashboard, analytics):
        assert (
            'add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;'
            in source
        )


def test_domain_readiness_verifies_chain_hostname_and_exact_san() -> None:
    source = (OPS_ROOT / "check-domain-readiness.sh").read_text(encoding="utf-8")

    assert '-connect "${host}:443"' in source
    assert '-servername "$host"' in source
    assert "-min_protocol TLSv1.2" in source
    assert "-verify_return_error" in source
    assert '-verify_hostname "$host"' in source
    assert 'grep -Fqx -- "DNS:${host}"' in source
