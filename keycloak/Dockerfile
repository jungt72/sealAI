FROM quay.io/keycloak/keycloak:26.2.0

ENV KC_DB=postgres \
    KC_DB_URL=jdbc:postgresql://postgres:5432/sealai \
    KC_DB_USERNAME=jungt72 \
    KC_DB_PASSWORD=Katerkimba123 \
    KC_DB_URL_PROPERTIES=?sslmode=disable \
    KEYCLOAK_ADMIN=admin \
    KEYCLOAK_ADMIN_PASSWORD=admin \
    KC_FEATURES=persistent-user-sessions \
    KC_HTTP_ENABLED=true \
    KC_HTTP_PORT=8080 \
    KC_HTTPS_PORT=8443

RUN /opt/keycloak/bin/kc.sh build

COPY --chown=1000:0 certs/cert.pem /etc/x509/https/tls.crt
COPY --chown=1000:0 certs/key.pem  /etc/x509/https/tls.key

RUN chmod 640 /etc/x509/https/tls.key && chmod 644 /etc/x509/https/tls.crt

ENTRYPOINT ["/opt/keycloak/bin/kc.sh", "start", "--optimized"]
