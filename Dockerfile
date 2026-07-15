# Stage 1: Keycloak Builder
FROM quay.io/keycloak/keycloak:24.0.1@sha256:8e38bc8a4e0606e38a37401422dfbf414e2b73797952dfe94c9b56e2f9207897 AS builder

ENV KC_DB=postgres
ENV KC_FEATURES=persistent-user-sessions

RUN /opt/keycloak/bin/kc.sh build

# Stage 2: Final Image
FROM quay.io/keycloak/keycloak:24.0.1@sha256:8e38bc8a4e0606e38a37401422dfbf414e2b73797952dfe94c9b56e2f9207897

COPY --from=builder /opt/keycloak/ /opt/keycloak/

ENV KC_DB=postgres
ENV KC_DB_URL=jdbc:postgresql://postgres:5432/keycloak
ENV KC_DB_USERNAME=keycloak
ENV KC_DB_PASSWORD=keycloak
ENV KEYCLOAK_ADMIN=admin
ENV KEYCLOAK_ADMIN_PASSWORD=admin
ENV KC_HOSTNAME_STRICT=false
ENV KC_HOSTNAME_STRICT_HTTPS=false
ENV KC_PROXY=edge

EXPOSE 8080 8443

ENTRYPOINT ["/opt/keycloak/bin/kc.sh", "start"]
