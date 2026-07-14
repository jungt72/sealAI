from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _module():
    path = Path(__file__).resolve().parents[2] / "ops" / "check-secret-hygiene.py"
    spec = importlib.util.spec_from_file_location("secret_hygiene", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sensitive_key_classifier_uses_token_boundaries() -> None:
    pattern = _module().ENV_SENSITIVE_KEY_RE

    assert pattern.search("PAPERLESS_TOKEN")
    assert pattern.search("OPENAI_API_KEY")
    assert pattern.search("POSTGRES_PASSWORD")
    assert not pattern.search("SEALAI_V2_EVAL_JUDGE_MAX_OUTPUT_TOKENS")


def test_scanner_detects_each_supported_secret_class() -> None:
    module = _module()
    candidate = "opaque_fixture_value_1234567890"
    compact_token = ".".join(
        (
            "eyJ" + "hbGciOiJub25lIn0",
            "eyJ" + "zdWIiOiJ0ZXN0In0",
            "c3ludGhldGljLXNpZ25hdHVyZQ",
        )
    )
    samples = {
        "content.private-key-pem": (
            "fixtures/server.txt",
            ("-----BEGIN " + "PRIVATE KEY-----\n" + candidate).encode(),
        ),
        "content.private-jwk": (
            "fixtures/account.json",
            json.dumps(
                {"kty": "RSA", "n": "synthetic", "e": "AQAB", "d": candidate}
            ).encode(),
        ),
        "content.jwt": ("fixtures/session.txt", compact_token.encode()),
        "content.bearer-token": (
            "fixtures/request.txt",
            ("Authoriz" + "ation: " + "Bearer " + candidate).encode(),
        ),
        "content.sensitive-assignment": (
            "fixtures/runtime.conf",
            ("OPENAI_" + "API_KEY=" + candidate).encode(),
        ),
        "content.connection-string": (
            "fixtures/runtime.conf",
            ("post" + "gresql://example_user:" + candidate + "@db/service").encode(),
        ),
        "content.database-dump": (
            "fixtures/archive.bin",
            ("PG" + "DMP" + candidate).encode(),
        ),
    }

    for expected_rule, (path, content) in samples.items():
        rules = {
            finding.rule for finding in module.scan_blob(path, content, source="test")
        }
        assert expected_rule in rules


def test_filename_policy_blocks_private_material_envs_and_dumps() -> None:
    module = _module()

    assert "filename.private-key" in {
        item.rule for item in module.scan_blob("certs/service.key", b"", source="test")
    }
    assert "filename.env" in {
        item.rule for item in module.scan_blob("config/.env.prod", b"", source="test")
    }
    assert "filename.database-dump" in {
        item.rule
        for item in module.scan_blob("backups/prod.pgdump", b"", source="test")
    }


def test_placeholder_example_is_allowed_but_still_scanned() -> None:
    module = _module()
    placeholder = ("OPENAI_" + "API_KEY=SET_IN_SECRET_STORE\n").encode()

    assert (
        module.scan_blob("config/runtime.env.example", placeholder, source="test") == []
    )


def test_lowercase_and_hex_sensitive_literals_fail_closed() -> None:
    module = _module()
    candidates = (
        "abcdefgh",
        "deadbeef",
    )

    for candidate in candidates:
        content = ("SERVICE_" + "TOKEN=" + candidate).encode()
        rules = {
            item.rule
            for item in module.scan_blob(
                "fixtures/runtime.conf", content, source="test"
            )
        }
        assert "content.sensitive-assignment" in rules


def test_markdown_unquoted_sensitive_literal_fails_closed() -> None:
    module = _module()
    content = ("SERVICE_" + "TOKEN=" + "lowercasevalue").encode()

    rules = {
        item.rule
        for item in module.scan_blob("docs/capture.md", content, source="test")
    }

    assert "content.sensitive-assignment" in rules


def test_private_jwk_d_fails_closed_even_when_short() -> None:
    module = _module()
    content = json.dumps({"kty": "EC", "crv": "P-256", "d": "abc"}).encode()

    rules = {
        item.rule
        for item in module.scan_blob("fixtures/keyset.json", content, source="test")
    }

    assert "content.private-jwk" in rules


def test_code_expression_is_not_misclassified_as_literal_secret() -> None:
    module = _module()

    assert (
        module.scan_blob("service.py", b"token = runtime.token\n", source="test") == []
    )


def test_rendered_findings_never_include_detected_value() -> None:
    module = _module()
    candidate = "opaque_redaction_probe_1234567890"
    content = ("SERVICE_" + "TOKEN=" + candidate).encode()

    findings = module.scan_blob("fixtures/runtime.conf", content, source="test")
    rendered = module.render_findings(findings)

    assert findings
    assert candidate not in rendered
    assert "content.sensitive-assignment" in rendered


def test_confirmed_credentials_and_raw_auth_evidence_are_absent() -> None:
    root = Path(__file__).resolve().parents[2]
    exact_paths = (
        root / "certs" / "tls.key",
        root / "keycloak" / "certs" / "key.pem",
    )
    raw_directories = (
        root / "docs" / "debug_internal_error" / "20251222T100929Z",
        root / "docs" / "debug_internal_error" / "live",
        root / "nginx" / "certbot" / "accounts",
    )

    assert all(not path.exists() for path in exact_paths)
    for directory in raw_directories:
        assert not directory.exists() or not any(
            path.is_file() for path in directory.rglob("*")
        )
