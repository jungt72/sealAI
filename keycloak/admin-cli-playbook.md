# Keycloak Admin-CLI Playbook (Stand: November 2025)

Schnelle, wiederholbare Einrichtung von Keycloak per `kcadm.sh` (Admin: `admin`/`admin`). Alle Befehle werden von der Projektwurzel ausgeführt; Keycloak muss per `docker compose up -d keycloak postgres` laufen.

## 1) CLI Session öffnen

```bash
kc="docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh"
$kc config credentials --server http://localhost:8080 --realm master --user admin --password admin
```

## 2) Realm anlegen/aktualisieren (Security Defaults)

```bash
REALM=sealAI

# anlegen, falls nicht vorhanden
$kc get realms/$REALM >/dev/null 2>&1 || \
  $kc create realms -s realm=$REALM -s enabled=true -s displayName="SealAI" -s loginTheme=sealai

# sichere Default-Settings (TLS, MFA-ready, kurze Tokens)
$kc update realms/$REALM \
  -s sslRequired=all \
  -s loginTheme=sealai \
  -s registrationAllowed=true \
  -s registrationEmailAsUsername=true \
  -s loginWithEmailAllowed=true \
  -s rememberMe=true \
  -s verifyEmail=true \
  -s resetPasswordAllowed=true \
  -s internationalizationEnabled=true \
  -s supportedLocales='["de","en"]' \
  -s defaultLocale=de \
  -s bruteForceProtected=true \
  -s failureFactor=6 \
  -s permanentLockout=false \
  -s maxFailureWaitSeconds=900 \
  -s waitIncrementSeconds=60 \
  -s quickLoginCheckMilliSeconds=800 \
  -s ssoSessionIdleTimeout=1800 \
  -s ssoSessionMaxLifespan=28800 \
  -s clientSessionIdleTimeout=900 \
  -s clientSessionMaxLifespan=10800 \
  -s accessTokenLifespan=300 \
  -s accessTokenLifespanForImplicitFlow=0 \
  -s offlineSessionIdleTimeout=604800 \
  -s offlineSessionMaxLifespanEnabled=true
```

## 3) MFA / Required Actions aktivieren

```bash
$kc update authentication/required-actions/CONFIGURE_TOTP -r $REALM -s defaultAction=true -s enabled=true
$kc update authentication/required-actions/VERIFY_EMAIL -r $REALM -s defaultAction=true -s enabled=true
```

## 4) Client (z. B. NextAuth) mit PKCE & restriktiven Redirects

```bash
CLIENT_ID=nextauth
CLIENT_SECRET=$(openssl rand -hex 32)
FRONTEND_URL=http://localhost:3000

# Client anlegen (falls neu)
$kc get clients -r $REALM -q clientId=$CLIENT_ID | grep '"id"' >/dev/null 2>&1 || \
  $kc create clients -r $REALM \
    -s clientId=$CLIENT_ID \
    -s name="NextAuth Frontend" \
    -s protocol=openid-connect \
    -s publicClient=false \
    -s serviceAccountsEnabled=false \
    -s standardFlowEnabled=true \
    -s implicitFlowEnabled=false \
    -s directAccessGrantsEnabled=false \
    -s attributes.'pkce.code.challenge.method'=S256 \
    -s attributes.'oauth2.device.authorization.grant.enabled'=false \
    -s attributes.'client.secret.creation.time'=$(date +%s) \
    -s attributes.'access.token.signed.response.alg'="RS256" \
    -s secret=$CLIENT_SECRET \
    -s rootUrl=$FRONTEND_URL \
    -s adminUrl=$FRONTEND_URL \
    -s redirectUris="[$FRONTEND_URL/*]" \
    -s webOrigins="[$FRONTEND_URL]"

# Client-Scopes (Profile, Email, Roles) sicherstellen
$kc update "clients/$( $kc get clients -r $REALM -q clientId=$CLIENT_ID --fields id --format csv | tail -n1 )" -r $REALM \
  -s defaultClientScopes='["profile","email","roles"]' \
  -s optionalClientScopes='["address","phone","offline_access"]'
```

## 5) Rollen & Test-User

```bash
$kc create roles -r $REALM -s name=user_basic 2>/dev/null || true
$kc create roles -r $REALM -s name=user_pro 2>/dev/null || true
$kc create roles -r $REALM -s name=manufacturer 2>/dev/null || true
$kc create roles -r $REALM -s name=admin 2>/dev/null || true

$kc create users -r $REALM -s username=admin -s enabled=true -s email=admin@example.com 2>/dev/null || true
$kc set-password -r $REALM --username admin --new-password admin
$kc add-roles -r $REALM --uusername admin --rolename admin --rolename user_basic || true
```

Für den produktiven Realm mit persistenter Datenbank ist der repo-konforme
Kurzweg:

```bash
./ops/keycloak_ensure_roles.sh
```

Der Helper liest standardmäßig `.env.prod`, zielt auf den realen Realm
`sealAI` und legt genau diese Realm-Rollen idempotent an:
`user_basic`, `user_pro`, `manufacturer`, `admin`.

## 6) SMTP (Transaktions-Mails)

```bash
$kc update realms/$REALM \
  -s smtpServer='{"host":"smtp.example.com","port":"587","from":"no-reply@sealai.net","fromDisplayName":"SealAI Auth","auth":"true","ssl":"false","starttls":"true","user":"smtp-user","password":"smtp-pass"}'
```

## 7) Backup & Export

```bash
# einzelner Realm-Export (ohne sensible Keys)
$kc get realms/$REALM > keycloak-realm-backup/${REALM}-$(date +%F).json
```

### Kurze Checkliste Best Practices (2025)
- TLS erzwingen (`sslRequired=all`), Hostname-Strict in `keycloak.conf`.
- PKCE + eingeschränkte Redirects/WebOrigins; keine impliziten Flows.
- Brute-Force-Schutz aktiv, moderate Token-Lebensdauern, Remember-Me nur explizit.
- MFA als Required Action, E-Mail-Verifikation aktiv.
- Login-Theme auf `sealai`, eigene Inhalte in `/keycloak/themes/sealai`.
- Regelmäßige Realm-Backups; Secrets nicht mit in Git speichern.
