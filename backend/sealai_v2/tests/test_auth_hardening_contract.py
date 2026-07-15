from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_both_keycloak_exports_are_closed_and_verification_required():
    for relative in ("keycloak/realm-export.json", "keycloak/import/realm-export.json"):
        realm = json.loads((ROOT / relative).read_text())
        assert realm["registrationAllowed"] is False
        assert realm["verifyEmail"] is True
        assert realm["bruteForceProtected"] is True


def test_keycloak_reconciler_cannot_reopen_registration_or_restore_wildcard_callback():
    reconciler = (ROOT / "ops/keycloak_ensure_roles.sh").read_text()
    assert "-s 'registrationAllowed=false'" in reconciler
    assert "-s 'registrationAllowed=true'" not in reconciler
    assert "BLOCKED_EXTERNAL: SMTP absent" in reconciler
    assert 'redirectUris=["https://sealingai.com/dashboard/callback"]' in reconciler
    assert 'redirectUris=["https://sealingai.com/dashboard/*"]' not in reconciler


def test_governance_reconciler_is_separate_read_only_by_default():
    broad = (ROOT / "ops/keycloak_ensure_roles.sh").read_text()
    governance = (ROOT / "ops/keycloak_governance_reconcile.py").read_text()
    manifest = json.loads(
        (ROOT / "security/keycloak-governance-v1.json").read_text(encoding="utf-8")
    )

    assert "governance roles unchanged" in broad
    assert "governance-reviewers" not in broad
    assert manifest["forbidden_role_names"] == ["admin"]
    assert manifest["assignment_policy"]["manage_user_memberships"] is False
    assert 'parser.add_argument("--apply", action="store_true")' in governance
    assert (
        "--apply requires --expected-manifest-sha256 and --expected-state-sha256"
        in governance
    )
    assert "if args.apply:" in governance


def test_nginx_access_log_format_cannot_record_query_strings():
    config = (ROOT / "nginx/default.conf").read_text()
    policy = config.split("server {", 1)[0]
    log_format = policy.split("log_format sealai_without_query", 1)[1].split(";", 1)[0]
    assert "$request_uri" not in log_format
    assert "$args" not in log_format
    assert "$remote_addr" not in log_format
    assert "$remote_user" not in log_format
    assert "$http_user_agent" not in log_format
    assert "$http_referer" not in log_format
    assert "$http_authorization" not in log_format
    assert "$request_id" in log_format
    assert '"$request_method $uri $server_protocol"' in policy
    assert "/dashboard/callback 0;" in policy
    assert "protocol/openid-connect/(auth|token|logout)" in policy
    assert "~^/api/v2/cases/ 0;" in policy


def test_nginx_upgrade_map_has_one_http_context_authority():
    default = (ROOT / "nginx/default.conf").read_text()
    tuning = (ROOT / "nginx/00-tuning.conf").read_text()
    assert default.count("map $http_upgrade $connection_upgrade") == 0
    assert tuning.count("map $http_upgrade $connection_upgrade") == 1


def test_frontend_case_transport_contains_no_case_query_builder():
    client = (ROOT / "frontend-v2/src/api/client.ts").read_text()
    case_state = (ROOT / "frontend-v2/src/lib/caseId.ts").read_text()
    assert "?case_id=" not in client
    assert "searchParams.set(CASE" not in case_state
    memory_route = (ROOT / "backend/sealai_v2/api/routes/memory_v2.py").read_text()
    assert 'alias="X-SealAI-Case-Id"' in memory_route


def test_provider_kill_switch_and_budget_contract_are_wired_fail_closed_in_compose():
    compose = (ROOT / "docker-compose.deploy.yml").read_text()
    assert (
        "SEALAI_V2_PROVIDER_REQUESTS_ENABLED: "
        "${SEALAI_V2_PROVIDER_REQUESTS_ENABLED:-false}"
    ) in compose
    assert "SEALAI_V2_PROVIDER_BUDGET_CONTRACT_SHA256" in compose
    assert "SEALAI_V2_PROVIDER_REQUEST_RESERVATION_MICROS" in compose
