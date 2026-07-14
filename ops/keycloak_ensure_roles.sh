#!/bin/bash -p
set -euo pipefail
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

# Idempotently reconciles the sealingAI realm through Keycloak's supported
# Admin CLI. Credentials are accepted only for this process; the script never
# sources .env.prod and never leaves an authenticated kcadm session behind.

KEYCLOAK_CONTAINER="${KEYCLOAK_CONTAINER:-keycloak}"
KEYCLOAK_SERVER="${KEYCLOAK_SERVER:-http://localhost:8080}"
KEYCLOAK_AUTH_REALM="${KEYCLOAK_AUTH_REALM:-master}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-sealAI}"
KEYCLOAK_TARGET_EMAIL="${KEYCLOAK_TARGET_EMAIL:-mail@thorsten-jung.de}"
KEYCLOAK_ADMIN_CLIENT_ID="${KEYCLOAK_ADMIN_CLIENT_ID:-}"
KEYCLOAK_ADMIN_CLIENT_SECRET="${KEYCLOAK_ADMIN_CLIENT_SECRET:-}"
KEYCLOAK_ADMIN_USER="${KEYCLOAK_ADMIN_USER:-}"
KEYCLOAK_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-}"
KEYCLOAK_DELETE_ADMIN_CLIENT="${KEYCLOAK_DELETE_ADMIN_CLIENT:-false}"
KEYCLOAK_DELETE_ADMIN_USER="${KEYCLOAK_DELETE_ADMIN_USER:-false}"
KEYCLOAK_SECURITY_PROFILE="${KEYCLOAK_SECURITY_PROFILE:-production}"
KCADM_CONFIG="/tmp/sealai-kcadm-$$.config"
KCADM_JSON="/tmp/sealai-kcadm-$$.json"

PRODUCT_ROLES=(
  user_basic
  user_pro
  manufacturer
  admin
  capability_reviewer
  knowledge_reviewer
  decision_reviewer
)

die() {
  printf 'keycloak_ensure_roles: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  docker exec "$KEYCLOAK_CONTAINER" rm -f "$KCADM_CONFIG" "$KCADM_JSON" >/dev/null 2>&1 || true
}
trap cleanup EXIT

command -v docker >/dev/null 2>&1 || die "docker is required"
command -v jq >/dev/null 2>&1 || die "jq is required"
docker inspect "$KEYCLOAK_CONTAINER" >/dev/null 2>&1 || die "container '$KEYCLOAK_CONTAINER' is not running"

case "$KEYCLOAK_SECURITY_PROFILE" in
  test|production) ;;
  *) die "KEYCLOAK_SECURITY_PROFILE must be 'test' or 'production'" ;;
esac

kcadm() {
  docker exec "$KEYCLOAK_CONTAINER" /opt/keycloak/bin/kcadm.sh "$@" --config "$KCADM_CONFIG"
}

kcadm_update_json() {
  local resource="$1"
  local payload="$2"
  printf '%s' "$payload" | docker exec -i "$KEYCLOAK_CONTAINER" /bin/bash -ec \
    'cat > "$1"' -- "$KCADM_JSON"
  kcadm update "$resource" -r "$KEYCLOAK_REALM" -f "$KCADM_JSON" >/dev/null
  docker exec "$KEYCLOAK_CONTAINER" rm -f "$KCADM_JSON" >/dev/null
}

kcadm_create_json() {
  local resource="$1"
  local payload="$2"
  printf '%s' "$payload" | docker exec -i "$KEYCLOAK_CONTAINER" /bin/bash -ec \
    'cat > "$1"' -- "$KCADM_JSON"
  kcadm create "$resource" -r "$KEYCLOAK_REALM" -f "$KCADM_JSON" >/dev/null
  docker exec "$KEYCLOAK_CONTAINER" rm -f "$KCADM_JSON" >/dev/null
}

flow_executions() {
  local flow_alias="$1"
  local encoded_flow_alias
  encoded_flow_alias="$(jq -rn --arg value "$flow_alias" '$value | @uri')"
  kcadm get "authentication/flows/$encoded_flow_alias/executions" -r "$KEYCLOAK_REALM"
}

set_execution_requirement() {
  local flow_alias="$1"
  local execution_id="$2"
  local requirement="$3"
  local encoded_flow_alias
  encoded_flow_alias="$(jq -rn --arg value "$flow_alias" '$value | @uri')"
  kcadm update "authentication/flows/$encoded_flow_alias/executions" -r "$KEYCLOAK_REALM" -n \
    -s "id=$execution_id" -s "requirement=$requirement" >/dev/null
}

reconcile_browser_mfa_flow() {
  local browser_flow browser_executions direct_otp_id forms_execution
  local forms_execution_id forms_flow_alias forms_executions password_execution_id
  local otp_flow_execution otp_flow_execution_id otp_flow_alias otp_requirement
  local otp_executions condition_execution_id otp_execution_id
  browser_flow="$(kcadm get "realms/$KEYCLOAK_REALM" | jq -r '.browserFlow')"
  browser_executions="$(flow_executions "$browser_flow")"

  # A Conditional OTP Form cannot run at the browser-flow root because no user
  # exists in the authentication context yet. Disable any legacy root execution
  # created by an older reconciler, then restore Keycloak's standard order:
  # username/password first, credential-conditioned OTP second.
  while IFS= read -r direct_otp_id; do
    [[ -n "$direct_otp_id" ]] || continue
    set_execution_requirement "$browser_flow" "$direct_otp_id" DISABLED
  done < <(jq -r \
    '.[] | select(.level == 0 and .providerId == "auth-conditional-otp-form") | .id' \
    <<<"$browser_executions")

  forms_execution="$(jq -er \
    '[.[] | select(
        .level == 0
        and .authenticationFlow == true
        and (.displayName | test("(^| )forms$"; "i"))
      )]
     | if length == 1 then .[0] else error("expected one browser forms subflow") end' \
    <<<"$browser_executions")"
  forms_execution_id="$(jq -r '.id' <<<"$forms_execution")"
  forms_flow_alias="$(jq -r '.displayName' <<<"$forms_execution")"
  set_execution_requirement "$browser_flow" "$forms_execution_id" ALTERNATIVE

  forms_executions="$(flow_executions "$forms_flow_alias")"
  password_execution_id="$(jq -er \
    '[.[] | select(.level == 0 and .providerId == "auth-username-password-form")]
     | if length == 1 then .[0].id else error("expected one username/password execution") end' \
    <<<"$forms_executions")"
  set_execution_requirement "$forms_flow_alias" "$password_execution_id" REQUIRED

  otp_flow_execution="$(jq -er \
    '[.[] | select(
        .level == 0
        and .authenticationFlow == true
        and (.displayName | test("Conditional (OTP|2FA)"; "i"))
      )]
     | if length == 1 then .[0] else error("expected one conditional OTP subflow") end' \
    <<<"$forms_executions")"
  otp_flow_execution_id="$(jq -r '.id' <<<"$otp_flow_execution")"
  otp_flow_alias="$(jq -r '.displayName' <<<"$otp_flow_execution")"
  if [[ "$KEYCLOAK_SECURITY_PROFILE" == "production" ]]; then
    otp_requirement=CONDITIONAL
  else
    otp_requirement=DISABLED
  fi
  set_execution_requirement "$forms_flow_alias" "$otp_flow_execution_id" "$otp_requirement"

  otp_executions="$(flow_executions "$otp_flow_alias")"
  condition_execution_id="$(jq -er \
    '[.[] | select(.level == 0 and .providerId == "conditional-user-configured")]
     | if length == 1 then .[0].id else error("expected one user-configured condition") end' \
    <<<"$otp_executions")"
  otp_execution_id="$(jq -er \
    '[.[] | select(.level == 0 and .providerId == "auth-otp-form")]
     | if length == 1 then .[0].id else error("expected one OTP form") end' \
    <<<"$otp_executions")"
  set_execution_requirement "$otp_flow_alias" "$condition_execution_id" REQUIRED
  set_execution_requirement "$otp_flow_alias" "$otp_execution_id" REQUIRED
}

authenticate() {
  if [[ -n "$KEYCLOAK_ADMIN_CLIENT_ID" && -n "$KEYCLOAK_ADMIN_CLIENT_SECRET" ]]; then
    docker exec \
      --env SEALAI_KCADM_SECRET="$KEYCLOAK_ADMIN_CLIENT_SECRET" \
      "$KEYCLOAK_CONTAINER" \
      /bin/bash -ec \
      'exec /opt/keycloak/bin/kcadm.sh config credentials --server "$1" --realm "$2" --client "$3" --secret "$SEALAI_KCADM_SECRET" --config "$4"' \
      -- "$KEYCLOAK_SERVER" "$KEYCLOAK_AUTH_REALM" "$KEYCLOAK_ADMIN_CLIENT_ID" "$KCADM_CONFIG" \
      >/dev/null
    return
  fi

  if [[ -n "$KEYCLOAK_ADMIN_USER" && -n "$KEYCLOAK_ADMIN_PASSWORD" ]]; then
    docker exec \
      --env SEALAI_KCADM_PASSWORD="$KEYCLOAK_ADMIN_PASSWORD" \
      "$KEYCLOAK_CONTAINER" \
      /bin/bash -ec \
      'exec /opt/keycloak/bin/kcadm.sh config credentials --server "$1" --realm "$2" --user "$3" --password "$SEALAI_KCADM_PASSWORD" --config "$4"' \
      -- "$KEYCLOAK_SERVER" "$KEYCLOAK_AUTH_REALM" "$KEYCLOAK_ADMIN_USER" "$KCADM_CONFIG" \
      >/dev/null
    return
  fi

  die "provide a temporary admin client ID/secret or an interactive admin user/password via environment variables"
}

ensure_realm_role() {
  local role="$1"
  local description="$2"
  if kcadm get "roles/$role" -r "$KEYCLOAK_REALM" >/dev/null 2>&1; then
    return 0
  fi
  kcadm create roles -r "$KEYCLOAK_REALM" -s "name=$role" -s "description=$description" >/dev/null
}

ensure_group() {
  local name="$1"
  local groups group_id
  groups="$(kcadm get groups -r "$KEYCLOAK_REALM" --fields id,name,path)"
  group_id="$(jq -r --arg name "$name" '.[] | select(.name == $name and .path == ("/" + $name)) | .id' <<<"$groups" | head -n1)"
  if [[ -z "$group_id" ]]; then
    group_id="$(kcadm create groups -r "$KEYCLOAK_REALM" -s "name=$name" -i)"
  fi
  [[ -n "$group_id" ]] || die "unable to resolve group '$name'"
  printf '%s' "$group_id"
}

find_target_user() {
  local users
  users="$(kcadm get users -r "$KEYCLOAK_REALM" -q "email=$KEYCLOAK_TARGET_EMAIL" --fields id,username,email,enabled)"
  jq -er --arg email "${KEYCLOAK_TARGET_EMAIL,,}" \
    '[.[] | select((.email // "" | ascii_downcase) == $email)]
     | if length == 1 then .[0] else error("expected exactly one enabled target user") end' \
    <<<"$users"
}

delete_temporary_admin_identity() {
  if [[ "$KEYCLOAK_DELETE_ADMIN_CLIENT" == "true" ]]; then
    [[ "$KEYCLOAK_ADMIN_CLIENT_ID" == sealai-recovery-* ]] || \
      die "refusing to delete an admin client without the sealai-recovery- prefix"

    local clients client_id
    clients="$(kcadm get clients -r "$KEYCLOAK_AUTH_REALM" -q "clientId=$KEYCLOAK_ADMIN_CLIENT_ID" --fields id,clientId)"
    client_id="$(jq -r --arg client "$KEYCLOAK_ADMIN_CLIENT_ID" '.[] | select(.clientId == $client) | .id' <<<"$clients" | head -n1)"
    [[ -n "$client_id" ]] || die "temporary admin client was not found for deletion"
    kcadm delete "clients/$client_id" -r "$KEYCLOAK_AUTH_REALM" >/dev/null
  fi

  if [[ "$KEYCLOAK_DELETE_ADMIN_USER" == "true" ]]; then
    [[ "$KEYCLOAK_ADMIN_USER" == sealai-recovery-* ]] || \
      die "refusing to delete an admin user without the sealai-recovery- prefix"

    local users user_id
    users="$(kcadm get users -r "$KEYCLOAK_AUTH_REALM" -q "username=$KEYCLOAK_ADMIN_USER" --fields id,username)"
    user_id="$(jq -r --arg user "$KEYCLOAK_ADMIN_USER" '.[] | select(.username == $user) | .id' <<<"$users" | head -n1)"
    [[ -n "$user_id" ]] || die "temporary admin user was not found for deletion"
    kcadm delete "users/$user_id" -r "$KEYCLOAK_AUTH_REALM" >/dev/null
  fi
}

authenticate

realm_before="$(kcadm get "realms/$KEYCLOAK_REALM")"
smtp_configured="$(jq -r '((.smtpServer.host // "") | length) > 0' <<<"$realm_before")"

if [[ "$KEYCLOAK_SECURITY_PROFILE" == "production" ]]; then
  verify_email=true
  # Missing SMTP must never force an insecure onboarding fallback. Registration remains closed,
  # paid-provider routes independently require email_verified=true, and recovery stays disabled
  # until an owner supplies and validates the external mail transport under GATE-06.
  reset_enabled="$smtp_configured"
  if [[ "$smtp_configured" != "true" ]]; then
    printf '%s\n' \
      'BLOCKED_EXTERNAL: SMTP absent; self-registration and password recovery remain disabled.' >&2
  fi
else
  verify_email=false
  reset_enabled=false
fi

printf 'Reconciling realm security policy for %s (profile=%s)...\n' \
  "$KEYCLOAK_REALM" "$KEYCLOAK_SECURITY_PROFILE"
kcadm update "realms/$KEYCLOAK_REALM" \
  -s 'sslRequired=EXTERNAL' \
  -s 'registrationAllowed=false' \
  -s 'registrationEmailAsUsername=true' \
  -s 'loginWithEmailAllowed=true' \
  -s 'duplicateEmailsAllowed=false' \
  -s "verifyEmail=$verify_email" \
  -s "resetPasswordAllowed=$reset_enabled" \
  -s 'rememberMe=true' \
  -s 'internationalizationEnabled=true' \
  -s 'defaultLocale=de' \
  -s 'supportedLocales=["de","en"]' \
  -s 'accessTokenLifespan=300' \
  -s 'ssoSessionIdleTimeout=3600' \
  -s 'ssoSessionMaxLifespan=43200' \
  -s 'clientSessionIdleTimeout=3600' \
  -s 'clientSessionMaxLifespan=43200' \
  -s 'offlineSessionIdleTimeout=604800' \
  -s 'offlineSessionMaxLifespanEnabled=true' \
  -s 'offlineSessionMaxLifespan=2592000' \
  -s 'eventsEnabled=true' \
  -s 'eventsExpiration=604800' \
  -s 'adminEventsEnabled=true' \
  -s 'adminEventsDetailsEnabled=false' \
  -s 'bruteForceProtected=true' \
  -s 'bruteForceStrategy=MULTIPLE' \
  -s 'failureFactor=6' \
  -s 'permanentLockout=false' \
  -s 'maxFailureWaitSeconds=900' \
  -s 'waitIncrementSeconds=60' \
  -s 'quickLoginCheckMilliSeconds=1000' \
  -s 'minimumQuickLoginWaitSeconds=60' \
  -s 'passwordPolicy=length(15) and maxLength(128) and notUsername(undefined) and notEmail(undefined) and passwordHistory(5)' \
  >/dev/null

printf 'Reconciling progressive registration profile...\n'
user_profile="$(kcadm get users/profile -r "$KEYCLOAK_REALM")"
user_profile="$(jq \
  '(.attributes[] | select(.name == "firstName" or .name == "lastName")) |= del(.required)' \
  <<<"$user_profile")"
kcadm_update_json users/profile "$user_profile"

# TOTP stays available but is never a default action for public accounts.
printf 'Reconciling required actions...\n'
kcadm update authentication/required-actions/CONFIGURE_TOTP \
  -r "$KEYCLOAK_REALM" -s 'enabled=true' -s 'defaultAction=false' >/dev/null
kcadm update authentication/required-actions/UPDATE_PASSWORD \
  -r "$KEYCLOAK_REALM" -s 'enabled=true' -s 'defaultAction=false' >/dev/null

declare -A role_descriptions=(
  [user_basic]='Base access to sealingAI'
  [user_pro]='Professional sealingAI workspace access'
  [manufacturer]='Manufacturer partner access'
  [admin]='sealingAI product administration'
  [capability_reviewer]='Review sealingAI capability profiles'
  [knowledge_reviewer]='Review governed sealing knowledge'
  [decision_reviewer]='Review governed engineering decisions'
)
printf 'Reconciling product roles and administrator groups...\n'
for role in "${PRODUCT_ROLES[@]}"; do
  ensure_realm_role "$role" "${role_descriptions[$role]}"
done
default_role_name="$(jq -r '.defaultRole.name // empty' <<<"$realm_before")"
[[ -n "$default_role_name" ]] || die "realm default role could not be resolved"
kcadm add-roles -r "$KEYCLOAK_REALM" --rname "$default_role_name" \
  --rolename user_basic >/dev/null
printf 'Product roles ready; reconciling groups...\n'

PLATFORM_GROUP='platform-admins'
GOVERNANCE_GROUP='governance-reviewers'
platform_group_id="$(ensure_group "$PLATFORM_GROUP")"
governance_group_id="$(ensure_group "$GOVERNANCE_GROUP")"

printf 'Reconciling group product-role mappings...\n'
kcadm add-roles -r "$KEYCLOAK_REALM" --gname "$PLATFORM_GROUP" \
  --rolename admin --rolename user_basic >/dev/null
kcadm add-roles -r "$KEYCLOAK_REALM" --gname "$GOVERNANCE_GROUP" \
  --rolename capability_reviewer --rolename knowledge_reviewer --rolename decision_reviewer >/dev/null

printf 'Reconciling the privileged owner...\n'
target_user="$(find_target_user)"
target_user_id="$(jq -r '.id' <<<"$target_user")"
target_username="$(jq -r '.username' <<<"$target_user")"
target_enabled="$(jq -r '.enabled' <<<"$target_user")"
[[ "$target_enabled" == "true" ]] || die "target user is disabled"

# Preserve unrelated required actions. Test mode removes the inaccessible OTP
# credential; production requires a fresh enrollment whenever none exists.
user_state="$(kcadm get "users/$target_user_id" -r "$KEYCLOAK_REALM")"
owner_credentials="$(kcadm get "users/$target_user_id/credentials" -r "$KEYCLOAK_REALM")"
if [[ "$KEYCLOAK_SECURITY_PROFILE" == "test" ]]; then
  required_actions="$(jq -c '[.requiredActions[]? | select(. != "CONFIGURE_TOTP")]' <<<"$user_state")"
  kcadm update "users/$target_user_id" -r "$KEYCLOAK_REALM" \
    -s "requiredActions=$required_actions" >/dev/null
  while IFS= read -r credential_id; do
    [[ -n "$credential_id" ]] || continue
    kcadm delete "users/$target_user_id/credentials/$credential_id" \
      -r "$KEYCLOAK_REALM" >/dev/null
  done < <(jq -r '.[] | select(.type == "otp") | .id' <<<"$owner_credentials")
else
  otp_count="$(jq '[.[] | select(.type == "otp")] | length' <<<"$owner_credentials")"
  if [[ "$otp_count" -eq 0 ]]; then
    required_actions="$(jq -c \
      '[.requiredActions[]?] | if index("CONFIGURE_TOTP") then . else . + ["CONFIGURE_TOTP"] end' \
      <<<"$user_state")"
  else
    required_actions="$(jq -c \
      '[.requiredActions[]? | select(. != "CONFIGURE_TOTP")]' <<<"$user_state")"
  fi
  kcadm update "users/$target_user_id" -r "$KEYCLOAK_REALM" \
    -s "requiredActions=$required_actions" >/dev/null
fi
kcadm update "users/$target_user_id/groups/$platform_group_id" -r "$KEYCLOAK_REALM" >/dev/null
kcadm update "users/$target_user_id/groups/$governance_group_id" -r "$KEYCLOAK_REALM" >/dev/null
# Realm administration is intentionally owner-specific instead of inherited
# from a reusable group: adding a future product admin must not silently grant
# control over Keycloak itself.
kcadm add-roles -r "$KEYCLOAK_REALM" --uid "$target_user_id" \
  --cclientid realm-management --rolename realm-admin >/dev/null

printf 'Reconciling ordered browser authentication and MFA...\n'
reconcile_browser_mfa_flow

# The V1 Auth.js client is confidential and accepts one exact callback only.
printf 'Reconciling OIDC clients...\n'
nextauth_id="$(kcadm get clients -r "$KEYCLOAK_REALM" -q clientId=nextauth --fields id,clientId | jq -r '.[] | select(.clientId == "nextauth") | .id' | head -n1)"
[[ -n "$nextauth_id" ]] || die "nextauth client not found"
kcadm update "clients/$nextauth_id" -r "$KEYCLOAK_REALM" \
  -s 'publicClient=false' \
  -s 'bearerOnly=false' \
  -s 'standardFlowEnabled=true' \
  -s 'implicitFlowEnabled=false' \
  -s 'directAccessGrantsEnabled=false' \
  -s 'serviceAccountsEnabled=false' \
  -s 'redirectUris=["https://sealingai.com/api/auth/callback/keycloak"]' \
  -s 'webOrigins=["https://sealingai.com"]' \
  -s 'attributes."pkce.code.challenge.method"=S256' \
  -s 'attributes."oauth2.device.authorization.grant.enabled"=false' \
  >/dev/null

# The V2 browser client remains public, Authorization Code + PKCE only. The callback and
# post-logout redirect are exact; stale wildcard/:8443 entries are intentionally removed.
v2_id="$(kcadm get clients -r "$KEYCLOAK_REALM" -q clientId=sealai-v2 --fields id,clientId | jq -r '.[] | select(.clientId == "sealai-v2") | .id' | head -n1)"
[[ -n "$v2_id" ]] || die "sealai-v2 client not found"
kcadm update "clients/$v2_id" -r "$KEYCLOAK_REALM" \
  -s 'publicClient=true' \
  -s 'bearerOnly=false' \
  -s 'standardFlowEnabled=true' \
  -s 'implicitFlowEnabled=false' \
  -s 'directAccessGrantsEnabled=false' \
  -s 'serviceAccountsEnabled=false' \
  -s 'redirectUris=["https://sealingai.com/dashboard/callback"]' \
  -s 'webOrigins=["https://sealingai.com"]' \
  -s 'attributes."post.logout.redirect.uris"=https://sealingai.com/dashboard/' \
  -s 'attributes."pkce.code.challenge.method"=S256' \
  -s 'attributes."oauth2.device.authorization.grant.enabled"=false' \
  >/dev/null

realm_state="$(kcadm get "realms/$KEYCLOAK_REALM")"
printf 'Verifying reconciled Keycloak state...\n'
jq -e --argjson verify_email "$verify_email" --argjson reset_enabled "$reset_enabled" \
  '.eventsEnabled == true
   and .eventsExpiration == 604800
   and .adminEventsEnabled == true
   and .adminEventsDetailsEnabled == false
   and .bruteForceProtected == true
   and .registrationAllowed == false
   and .registrationEmailAsUsername == true
   and .verifyEmail == $verify_email
   and .resetPasswordAllowed == $reset_enabled
   and .internationalizationEnabled == true
   and .defaultLocale == "de"
   and .ssoSessionIdleTimeout == 3600
   and .ssoSessionMaxLifespan == 43200
   and (.passwordPolicy | contains("length(15)"))' \
  <<<"$realm_state" >/dev/null || die "realm security policy read-back failed"

user_state="$(kcadm get "users/$target_user_id" -r "$KEYCLOAK_REALM")"
owner_credentials="$(kcadm get "users/$target_user_id/credentials" -r "$KEYCLOAK_REALM")"
if [[ "$KEYCLOAK_SECURITY_PROFILE" == "test" ]]; then
  jq -e '(.requiredActions | index("CONFIGURE_TOTP")) == null' \
    <<<"$user_state" >/dev/null || die "test profile still requires TOTP"
  jq -e '[.[] | select(.type == "otp")] | length == 0' \
    <<<"$owner_credentials" >/dev/null || die "test profile still has an OTP credential"
else
  if jq -e '[.[] | select(.type == "otp")] | length == 0' \
    <<<"$owner_credentials" >/dev/null; then
    jq -e '(.requiredActions | index("CONFIGURE_TOTP")) != null' \
      <<<"$user_state" >/dev/null || die "production profile does not require privileged TOTP enrollment"
  else
    jq -e '(.requiredActions | index("CONFIGURE_TOTP")) == null' \
      <<<"$user_state" >/dev/null || die "production profile keeps redundant TOTP enrollment action"
  fi
fi

browser_flow="$(jq -r '.browserFlow' <<<"$realm_state")"
browser_executions="$(flow_executions "$browser_flow")"
jq -e \
  '[.[] | select(
      .level == 0
      and .providerId == "auth-conditional-otp-form"
      and .requirement != "DISABLED"
    )] | length == 0' \
  <<<"$browser_executions" >/dev/null || die "OTP still executes before user identification"
forms_execution="$(jq -er \
  '[.[] | select(
      .level == 0
      and .authenticationFlow == true
      and (.displayName | test("(^| )forms$"; "i"))
      and .requirement == "ALTERNATIVE"
    )]
   | if length == 1 then .[0] else error("browser forms subflow is not uniquely ALTERNATIVE") end' \
  <<<"$browser_executions")"
forms_flow_alias="$(jq -r '.displayName' <<<"$forms_execution")"
forms_executions="$(flow_executions "$forms_flow_alias")"
jq -e \
  '[.[] | select(
      .level == 0
      and .providerId == "auth-username-password-form"
      and .requirement == "REQUIRED"
    )] | length == 1' \
  <<<"$forms_executions" >/dev/null || die "username/password does not precede MFA"
conditional_otp_flow="$(jq -er \
  '[.[] | select(
      .level == 0
      and .authenticationFlow == true
      and (.displayName | test("Conditional (OTP|2FA)"; "i"))
    )]
   | if length == 1 then .[0] else error("conditional OTP subflow is not unique") end' \
  <<<"$forms_executions")"
if [[ "$KEYCLOAK_SECURITY_PROFILE" == "production" ]]; then
  jq -e '.requirement == "CONDITIONAL"' \
    <<<"$conditional_otp_flow" >/dev/null || die "production OTP subflow is not conditional"
else
  jq -e '.requirement == "DISABLED"' \
    <<<"$conditional_otp_flow" >/dev/null || die "test profile still enables the OTP subflow"
fi

user_groups="$(kcadm get "users/$target_user_id/groups" -r "$KEYCLOAK_REALM")"
jq -e --arg platform "$PLATFORM_GROUP" --arg governance "$GOVERNANCE_GROUP" \
  '([.[].name] | index($platform)) != null and ([.[].name] | index($governance)) != null' \
  <<<"$user_groups" >/dev/null || die "privileged group membership read-back failed"

realm_management_id="$(kcadm get clients -r "$KEYCLOAK_REALM" -q clientId=realm-management --fields id,clientId | jq -r '.[] | select(.clientId == "realm-management") | .id' | head -n1)"
[[ -n "$realm_management_id" ]] || die "realm-management client not found"
owner_admin_roles="$(kcadm get "users/$target_user_id/role-mappings/clients/$realm_management_id" -r "$KEYCLOAK_REALM")"
jq -e '([.[].name] | index("realm-admin")) != null' \
  <<<"$owner_admin_roles" >/dev/null || die "realm-admin owner mapping read-back failed"

governance_roles="$(kcadm get "groups/$governance_group_id/role-mappings/realm" -r "$KEYCLOAK_REALM")"
jq -e \
  '([.[].name] | index("capability_reviewer")) != null
   and ([.[].name] | index("knowledge_reviewer")) != null
   and ([.[].name] | index("decision_reviewer")) != null' \
  <<<"$governance_roles" >/dev/null || die "governance role mapping read-back failed"

nextauth_state="$(kcadm get "clients/$nextauth_id" -r "$KEYCLOAK_REALM")"
jq -e \
  '.publicClient == false
   and .standardFlowEnabled == true
   and .implicitFlowEnabled == false
   and .directAccessGrantsEnabled == false
   and .redirectUris == ["https://sealingai.com/api/auth/callback/keycloak"]
   and .webOrigins == ["https://sealingai.com"]
   and .attributes["pkce.code.challenge.method"] == "S256"' \
  <<<"$nextauth_state" >/dev/null || die "nextauth client policy read-back failed"

v2_state="$(kcadm get "clients/$v2_id" -r "$KEYCLOAK_REALM")"
jq -e \
  '.publicClient == true
   and .standardFlowEnabled == true
   and .implicitFlowEnabled == false
   and .directAccessGrantsEnabled == false
   and .redirectUris == ["https://sealingai.com/dashboard/callback"]
   and .webOrigins == ["https://sealingai.com"]
   and .attributes["post.logout.redirect.uris"] == "https://sealingai.com/dashboard/"
   and .attributes["pkce.code.challenge.method"] == "S256"' \
  <<<"$v2_state" >/dev/null || die "sealai-v2 client policy read-back failed"

# Revoke pre-existing sessions after policy and privileged mappings are verified.
printf 'Revoking pre-existing owner sessions...\n'
kcadm create "users/$target_user_id/logout" -r "$KEYCLOAK_REALM" -b '{}' >/dev/null

printf 'Deleting the temporary recovery identity...\n'
delete_temporary_admin_identity

printf 'Keycloak reconciliation complete: user=%s realm=%s groups=/%s,/%s\n' \
  "$target_username" "$KEYCLOAK_REALM" "$PLATFORM_GROUP" "$GOVERNANCE_GROUP"
