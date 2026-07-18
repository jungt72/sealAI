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


def test_sensitive_key_classifier_handles_plural_and_technical_names() -> None:
    sensitive = _module().is_sensitive_key

    for key in (
        "DB_PASSWORDS",
        "API_TOKENS",
        "AUTH_SECRETS",
        "CLIENT_SECRETS",
        "PRIVATE_KEYS",
        "ACCESS_TOKENS",
        "database_passwords",
        "client_secrets",
        "DB_PASSWORD_PRIMARY",
        "CLIENT_SECRET_CURRENT",
    ):
        assert sensitive(key)
    for key in (
        "MAX_OUTPUT_TOKENS",
        "INPUT_TOKEN_COUNT",
        "TOKEN_LIMIT",
        "TOKEN_BUDGET",
        "CONTEXT_TOKENS",
        "TOKENS_PER_MINUTE",
        "SEALAI_V2_EVAL_JUDGE_MAX_OUTPUT_TOKENS",
        "TLS_SECRET_NAME",
        "PASSWORD_POLICY",
        "CLIENT_SECRET_CREATION_TIME",
    ):
        assert not sensitive(key)


def test_assignment_and_json_share_sensitive_key_classification() -> None:
    module = _module()
    candidate = "synthetic_nonproduction_value_12345"
    keys = (
        "DB_PASSWORDS",
        "API_TOKENS",
        "AUTH_SECRETS",
        "CLIENT_SECRETS",
        "PRIVATE_KEYS",
        "ACCESS_TOKENS",
        "database_passwords",
        "client_secrets",
        "DB_PASSWORD_PRIMARY",
        "CLIENT_SECRET_CURRENT",
    )
    for key in keys:
        assignment = f"{key}={candidate}".encode()
        json_value = json.dumps({key: candidate}).encode()
        assert {
            item.rule for item in module.scan_blob("x.conf", assignment, source="test")
        } == {"content.sensitive-assignment"}
        assert {
            item.rule for item in module.scan_blob("x.json", json_value, source="test")
        } == {"content.sensitive-assignment"}


def test_technical_token_fields_and_placeholders_remain_clean() -> None:
    module = _module()
    candidate = "synthetic_nonproduction_value_12345"
    for key in (
        "MAX_OUTPUT_TOKENS",
        "INPUT_TOKEN_COUNT",
        "TOKEN_LIMIT",
        "TOKEN_BUDGET",
        "CONTEXT_TOKENS",
        "TOKENS_PER_MINUTE",
    ):
        assert (
            module.scan_blob("x.conf", f"{key}={candidate}".encode(), source="test")
            == []
        )
        assert (
            module.scan_blob(
                "x.json", json.dumps({key: candidate}).encode(), source="test"
            )
            == []
        )
    assert (
        module.scan_blob("x.conf", b"CLIENT_SECRETS=SET_IN_SECRET_STORE", source="test")
        == []
    )
    assert module.scan_blob("x.conf", b"CLIENT_SECRETS=short", source="test") == []


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


def test_utf16_wide_text_encodings_are_scanned_and_redacted() -> None:
    module = _module()
    candidate = "synthetic_wide_fixture_value_123456"
    samples = (
        (f"OPENAI_API_KEY={candidate}", "utf-16", "content.sensitive-assignment"),
        (f"Bearer {candidate}", "utf-16be", "content.bearer-token"),
        (
            "-----BEGIN " + f"PRIVATE KEY-----\n{candidate}",
            "utf-16le",
            "content.private-key-pem",
        ),
        (
            "post" + f"gresql://fixture:{candidate}@db/service",
            "utf-16be",
            "content.connection-string",
        ),
    )
    for index, (text, encoding, expected) in enumerate(samples):
        content = text.encode(encoding)
        if index == 1:
            content = b"\xfe\xff" + content
        findings = module.scan_blob("fixture.conf", content, source="wide-test")
        rendered = module.render_findings(findings)
        assert expected in {item.rule for item in findings}
        assert candidate not in rendered
        assert all(
            set(item.line().split())
            >= {f"path={item.path}", f"source={item.source}", "value=[REDACTED]"}
            for item in findings
        )


def test_utf8_behavior_is_unchanged_and_binary_data_stays_quiet() -> None:
    module = _module()
    candidate = "synthetic_utf8_fixture_value_123456"
    text = f"OPENAI_API_KEY={candidate}"
    utf8 = module.scan_blob("fixture.conf", text.encode(), source="test")
    utf8_bom = module.scan_blob(
        "fixture.conf", b"\xef\xbb\xbf" + text.encode(), source="test"
    )
    assert [(item.rule, item.line_number) for item in utf8] == [
        (item.rule, item.line_number) for item in utf8_bom
    ]
    binary = bytes(range(256)) * 2
    assert module.scan_blob("fixture.bin", binary, source="test") == []
    assert candidate not in module.render_findings(utf8)


def test_textlike_unsupported_encoding_fails_closed() -> None:
    module = _module()
    content = b"OPENAI_API_KEY=synthetic_fixture_value_12345\xff"
    findings = module.scan_blob("fixture.conf", content, source="test")
    assert "content.sensitive-assignment" in {item.rule for item in findings}
    assert "synthetic_fixture_value" not in module.render_findings(findings)


def test_inconsistent_wide_character_data_fails_closed() -> None:
    module = _module()
    malformed_utf16le = (b"A\x00" * 15) + b"\x00\xd8"
    try:
        module.scan_blob("fixture.conf", malformed_utf16le, source="test")
    except module.ScannerError:
        pass
    else:
        raise AssertionError("inconsistent wide-character data must fail closed")


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
