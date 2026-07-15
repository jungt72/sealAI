from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _module():
    path = Path(__file__).resolve().parents[2] / "ops" / "check-secret-hygiene.py"
    spec = importlib.util.spec_from_file_location("secret_hygiene_raw", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rules(module, content: bytes, path: str = "fixtures/blob.bin") -> set[str]:
    return {
        finding.rule for finding in module.scan_blob(path, content, source="raw-test")
    }


def test_confirmed_junk_byte_bypass_is_closed() -> None:
    module = _module()
    candidate = b"synthetic_raw_fixture_value_1234567890"
    secret = b"OPENAI_API_KEY=" + b"sk-" + candidate
    variants = (
        secret + (b"\xff" * 12),
        secret + (b"\x80" * 12),
        bytes((0, 1, 2, 128, 255)) * 4 + secret,
        secret + bytes((0, 1, 2, 128, 255)) * 4,
        bytes((0, 128, 255)) * 5 + secret + bytes((255, 128, 0)) * 5,
    )
    for content in variants:
        findings = module.scan_blob(
            "config/settings.conf", content, source="raw-bypass-test"
        )
        assert findings
        assert "content.sensitive-assignment" in {item.rule for item in findings}
        assert candidate.decode() not in module.render_findings(findings)


def test_every_required_ascii_secret_class_survives_binary_junk() -> None:
    module = _module()
    candidate = b"synthetic_raw_fixture_value_123456"
    jwt = b".".join(
        (
            b"eyJ" + b"hbGciOiJub25lIn0",
            b"eyJ" + b"zdWIiOiJ0ZXN0In0",
            b"c3ludGhldGljLXNpZ25hdHVyZQ",
        )
    )
    samples = {
        "content.private-key-pem": b"-----BEGIN " + b"PRIVATE KEY-----",
        "content.jwt": jwt,
        "content.bearer-token": b"Authoriz" + b"ation: Bearer " + candidate,
        "content.api-token": b"sk-" + (b"a" * 24),
        "content.connection-string": (
            b"post" + b"gresql://fixture:" + candidate + b"@db/example"
        ),
        "content.sensitive-assignment": b"DB_PASSWORD=" + candidate,
        "content.sensitive-json": json.dumps(
            {"CLIENT_SECRETS": candidate.decode()}
        ).encode(),
    }
    for expected, signature in samples.items():
        rules = _rules(module, b"\x80\xff" * 8 + signature + b"\xff\x80" * 8)
        normalized_expected = (
            "content.sensitive-assignment"
            if expected == "content.sensitive-json"
            else expected
        )
        assert normalized_expected in rules


def test_binary_without_signature_stays_clean_and_embedded_secret_is_found() -> None:
    module = _module()
    deterministic_binary = bytes((0, 1, 2, 3, 128, 129, 254, 255)) * 8
    png_like = b"\x89PNG\r\n\x1a\n" + bytes((0, 2, 4, 128, 255)) * 6
    zip_like = b"PK\x03\x04" + bytes((0, 1, 128, 254)) * 6
    assert _rules(module, deterministic_binary) == set()
    assert _rules(module, png_like) == set()
    assert _rules(module, zip_like) == set()

    candidate = b"synthetic_embedded_fixture_value_123456"
    embedded = deterministic_binary + b"API_TOKEN=" + candidate + deterministic_binary
    assert "content.sensitive-assignment" in _rules(module, embedded)
    assert "content.database-dump" in _rules(module, b"PG" + b"DMP" + b"\x00\xff")


def test_fragmented_sensitive_assignments_fail_closed() -> None:
    module = _module()
    candidate = b"synthetic_fragment_fixture_value_123456"
    samples = (
        b"DB_PASSWORD=" + candidate + b"\xff" * 8,
        b"\x80" * 8 + b"API_TOKEN=" + candidate,
        b"\xff" * 8 + b"AUTH_SECRETS=" + candidate + b"\x80" * 8,
    )
    for content in samples:
        assert "content.sensitive-assignment" in _rules(module, content)

    damaged_value = b"\xff" * 8 + b"CLIENT_SECRETS=" + b"\xff" * 8
    assert "content.unscannable-sensitive-data" in _rules(module, damaged_value)


def test_raw_and_text_findings_deduplicate_without_values() -> None:
    module = _module()
    candidate = b"sk-" + (b"a" * 24)
    findings = module.scan_blob("fixtures/runtime.conf", candidate, source="dedup-test")
    matching = [item for item in findings if item.rule == "content.api-token"]
    assert len(matching) == 1
    assert candidate.decode() not in module.render_findings(findings)


def test_outputs_and_exceptions_never_disclose_raw_value(capsys) -> None:
    module = _module()
    candidate = "synthetic_redaction_fixture_value_123456"
    content = b"\xff" * 8 + b"API_TOKEN=" + candidate.encode() + b"\x80" * 8
    findings = module.scan_blob("fixtures/blob.bin", content, source="redaction-test")
    rendered = module.render_findings(findings)
    print(rendered)
    captured = capsys.readouterr()
    metadata_json = json.dumps(
        [
            {
                "rule": item.rule,
                "path": item.path,
                "source": item.source,
                "line_number": item.line_number,
            }
            for item in findings
        ]
    )
    assert candidate not in captured.out
    assert candidate not in captured.err
    assert candidate not in metadata_json
    assert all(not hasattr(item, "value") for item in findings)

    try:
        module.decode_scan_candidates(candidate.encode() + b"\xff")
    except module.ScannerError as exc:
        assert candidate not in str(exc)
    else:
        raise AssertionError("damaged text must not be reported as clean")


def test_deterministic_prefix_suffix_mutations_preserve_detection() -> None:
    module = _module()
    candidate = b"synthetic_mutation_fixture_value_123456"
    originals = (
        b"OPENAI_API_KEY=" + candidate,
        b"Authoriz" + b"ation: Bearer " + candidate,
        b"post" + b"gresql://fixture:" + candidate + b"@db/example",
        b"-----BEGIN " + b"PRIVATE KEY-----",
    )
    junk_values = (b"\x80", b"\xff")
    counts = (0, 1, 12)
    for original in originals:
        for junk in junk_values:
            for prefix_count in counts:
                for suffix_count in counts:
                    mutated = junk * prefix_count + original + junk * suffix_count
                    assert module.scan_blob(
                        "fixtures/mutated.conf", mutated, source="mutation-test"
                    )


def test_each_damaged_assignment_marker_has_a_safe_outcome() -> None:
    module = _module()
    samples = (
        b"DB_PASSWORD=abc" + b"\xff",
        b"DB_PASSWORD=Sup3rSec" + b"\xff" + b"ret",
        b"API_TOKENS=short" + b"\x80",
        b'CLIENT_SECRETS="abc' + b"\xff" + b'"',
    )
    for content in samples:
        findings = module.scan_blob(
            "config/damaged.conf", content, source="assignment-marker-test"
        )
        assert {item.rule for item in findings} == {
            "content.unscannable-sensitive-data"
        }

    complete = b"AUTH_SECRETS=" + b"synthetic_complete_fixture_123456" + b"\xff"
    assert "content.sensitive-assignment" in _rules(module, complete)

    for placeholder in (b"${DB_PASSWORD}", b"INJECT_AT_RUNTIME", b"REPLACE_ME"):
        assert (
            module.scan_blob(
                "config/placeholder.conf",
                b"DB_PASSWORD=" + placeholder,
                source="assignment-placeholder-test",
            )
            == []
        )


def test_each_damaged_connection_marker_fails_closed() -> None:
    module = _module()
    samples = (
        b"post" + b"gresql://user:abc" + b"\xff" + b"def@db/example",
        b"red" + b"is://user:Sup3r" + b"\x80" + b"Secret@redis/0",
        b"htt" + b"ps://user:abc" + b"\xff" + b"@example.test/",
        b"am" + b"qp://user:pass" + b"\x80" + b"word@queue/vhost",
    )
    for content in samples:
        findings = module.scan_blob(
            "config/damaged-url.conf", content, source="connection-marker-test"
        )
        assert {item.rule for item in findings} == {
            "content.unscannable-sensitive-data"
        }

    placeholder = b"post" + b"gresql://user:${DB_PASSWORD}@db/example"
    assert (
        module.scan_blob(
            "config/placeholder-url.conf",
            placeholder,
            source="connection-placeholder-test",
        )
        == []
    )


def test_fragmented_token_prefixes_fail_closed_without_broad_prefix_blocking() -> None:
    module = _module()
    samples = (
        b"sk-abcdefghij" + b"\xff" + b"klmnopqrstuvwxyz123456",
        b"Authoriz" + b"ation: Bearer abcdefgh" + b"\xff" + b"ijklmnopqrstuv",
        b"eyJabcdef." + b"\xff" + b"ghijklmnop.qrstuvwxyz123456",
        b"ghp_abcdefghij" + b"\x80" + b"klmnopqrstuvwxyz",
        b"xoxb-1234567890-" + b"\xff" + b"abcdefghijklmnop",
        b"AKIA12345678" + b"\xff" + b"90ABCDEF",
    )
    for content in samples:
        findings = module.scan_blob(
            "fixtures/damaged-token.bin", content, source="token-marker-test"
        )
        assert {item.rule for item in findings} == {
            "content.unscannable-sensitive-data"
        }

    for negative in (b"sk-", b"eyJ", b"Bearer", b"AKIA"):
        assert _rules(module, negative) == set()


def test_marker_coverage_is_per_marker_not_global_or_per_line() -> None:
    module = _module()
    pem_and_assignment = b"-----BEGIN " + b"PRIVATE KEY-----\nDB_PASSWORD=abc" + b"\xff"
    rules = [
        item.rule
        for item in module.scan_blob(
            "fixtures/multiple.bin", pem_and_assignment, source="marker-coverage-test"
        )
    ]
    assert "content.private-key-pem" in rules
    assert "content.unscannable-sensitive-data" in rules

    token_and_connection = (
        b"sk-"
        + (b"a" * 24)
        + b"\npost"
        + b"gresql://user:abc"
        + b"\xff"
        + b"@db/example"
    )
    rules = [
        item.rule
        for item in module.scan_blob(
            "fixtures/multiple.bin", token_and_connection, source="marker-coverage-test"
        )
    ]
    assert "content.api-token" in rules
    assert "content.unscannable-sensitive-data" in rules

    same_line = b"DB_PASSWORD=abc" + b"\xff" + b" API_TOKEN=short" + b"\x80"
    findings = module.scan_blob(
        "fixtures/same-line.bin", same_line, source="marker-coverage-test"
    )
    unresolved = [
        item for item in findings if item.rule == "content.unscannable-sensitive-data"
    ]
    assert len(unresolved) == 2
    assert {item.line_number for item in unresolved} == {1}
