#!/usr/bin/env bash
set -euo pipefail

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
KCADM_CONFIG="/tmp/sealai-kcadm-$$.config"

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
  docker exec "$KEYCLOAK_CONTAINER" rm -f "$KCADM_CONFIG" >/dev/null 2>&1 || true
}
trap cleanup EXIT

command -v docker >/dev/null 2>&1 || die "docker is required"
command -v jq >/dev/null 2>&1 || die "jq is required"
docker inspect "$KEYCLOAK_CONTAINER" >/dev/null 2>&1 || die "container '$KEYCLOAK_CONTAINER' is not running"

kcadm() {
  docker exec "$KEYCLOAK_CONTAINER" /opt/keycloak/bin/kcadm.sh "$@" --config "$KCADM_CONFIG"
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
    kcadm update "roles/$role" -r "$KEYCLOAK_REALM" -s "description=$description" >/dev/null
  else
    kcadm create roles -r "$KEYCLOAK_REALM" -s "name=$role" -s "description=$description" >/dev/null
  fi
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

printf 'Reconciling realm security policy for %s...\n' "$KEYCLOAK_REALM"
kcadm update "realms/$KEYCLOAK_REALM" \
  -s 'sslRequired=EXTERNAL' \
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
  -s 'passwordPolicy=length(14) and maxLength(128) and notUsername(undefined) and notEmail(undefined) and passwordHistory(5)' \
  >/dev/null

# MFA is required only for privileged users, not silently for every customer.
printf 'Reconciling privileged required actions...\n'
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

PLATFORM_GROUP='platform-admins'
GOVERNANCE_GROUP='governance-reviewers'
platform_group_id="$(ensure_group "$PLATFORM_GROUP")"
governance_group_id="$(ensure_group "$GOVERNANCE_GROUP")"

kcadm add-roles -r "$KEYCLOAK_REALM" --gname "$PLATFORM_GROUP" \
  --rolename admin --rolename user_basic >/dev/null
kcadm add-roles -r "$KEYCLOAK_REALM" --gname "$PLATFORM_GROUP" \
  --cclientid realm-management --rolename realm-admin >/dev/null
kcadm add-roles -r "$KEYCLOAK_REALM" --gname "$GOVERNANCE_GROUP" \
  --rolename capability_reviewer --rolename knowledge_reviewer --rolename decision_reviewer >/dev/null

target_user="$(find_target_user)"
target_user_id="$(jq -r '.id' <<<"$target_user")"
target_username="$(jq -r '.username' <<<"$target_user")"
target_enabled="$(jq -r '.enabled' <<<"$target_user")"
[[ "$target_enabled" == "true" ]] || die "target user is disabled"

# Required actions are assigned before privileged groups, so no fresh admin
# token is issued until the owner has replaced the password and enrolled TOTP.
kcadm update "users/$target_user_id" -r "$KEYCLOAK_REALM" \
  -s 'requiredActions=["UPDATE_PASSWORD","CONFIGURE_TOTP"]' >/dev/null
kcadm update "users/$target_user_id/groups/$platform_group_id" -r "$KEYCLOAK_REALM" >/dev/null
kcadm update "users/$target_user_id/groups/$governance_group_id" -r "$KEYCLOAK_REALM" >/dev/null

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

# The V2 browser client remains public, Authorization Code + PKCE only. Stale
# staging :8443 origins are intentionally removed after the production cutover.
v2_id="$(kcadm get clients -r "$KEYCLOAK_REALM" -q clientId=sealai-v2 --fields id,clientId | jq -r '.[] | select(.clientId == "sealai-v2") | .id' | head -n1)"
[[ -n "$v2_id" ]] || die "sealai-v2 client not found"
kcadm update "clients/$v2_id" -r "$KEYCLOAK_REALM" \
  -s 'publicClient=true' \
  -s 'bearerOnly=false' \
  -s 'standardFlowEnabled=true' \
  -s 'implicitFlowEnabled=false' \
  -s 'directAccessGrantsEnabled=false' \
  -s 'serviceAccountsEnabled=false' \
  -s 'redirectUris=["https://sealingai.com/dashboard/*"]' \
  -s 'webOrigins=["https://sealingai.com"]' \
  -s 'attributes."pkce.code.challenge.method"=S256' \
  -s 'attributes."oauth2.device.authorization.grant.enabled"=false' \
  >/dev/null

realm_state="$(kcadm get "realms/$KEYCLOAK_REALM")"
printf 'Verifying reconciled Keycloak state...\n'
jq -e \
  '.eventsEnabled == true
   and .eventsExpiration == 604800
   and .adminEventsEnabled == true
   and .adminEventsDetailsEnabled == false
   and .bruteForceProtected == true
   and .ssoSessionIdleTimeout == 3600
   and .ssoSessionMaxLifespan == 43200
   and (.passwordPolicy | contains("length(14)"))' \
  <<<"$realm_state" >/dev/null || die "realm security policy read-back failed"

user_state="$(kcadm get "users/$target_user_id" -r "$KEYCLOAK_REALM")"
jq -e \
  '(.requiredActions | index("UPDATE_PASSWORD")) != null
   and (.requiredActions | index("CONFIGURE_TOTP")) != null' \
  <<<"$user_state" >/dev/null || die "privileged required-action read-back failed"

user_groups="$(kcadm get "users/$target_user_id/groups" -r "$KEYCLOAK_REALM")"
jq -e --arg platform "$PLATFORM_GROUP" --arg governance "$GOVERNANCE_GROUP" \
  '([.[].name] | index($platform)) != null and ([.[].name] | index($governance)) != null' \
  <<<"$user_groups" >/dev/null || die "privileged group membership read-back failed"

realm_management_id="$(kcadm get clients -r "$KEYCLOAK_REALM" -q clientId=realm-management --fields id,clientId | jq -r '.[] | select(.clientId == "realm-management") | .id' | head -n1)"
[[ -n "$realm_management_id" ]] || die "realm-management client not found"
platform_admin_roles="$(kcadm get "groups/$platform_group_id/role-mappings/clients/$realm_management_id" -r "$KEYCLOAK_REALM")"
jq -e '([.[].name] | index("realm-admin")) != null' \
  <<<"$platform_admin_roles" >/dev/null || die "realm-admin group mapping read-back failed"

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
   and .redirectUris == ["https://sealingai.com/dashboard/*"]
   and .webOrigins == ["https://sealingai.com"]
   and .attributes["pkce.code.challenge.method"] == "S256"' \
  <<<"$v2_state" >/dev/null || die "sealai-v2 client policy read-back failed"

printf 'Deleting the temporary recovery identity...\n'
delete_temporary_admin_identity

printf 'Keycloak reconciliation complete: user=%s realm=%s groups=/%s,/%s\n' \
  "$target_username" "$KEYCLOAK_REALM" "$PLATFORM_GROUP" "$GOVERNANCE_GROUP"
