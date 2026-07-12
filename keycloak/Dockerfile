# sealingAI Keycloak 26.7.0. The amd64 manifest is digest-pinned so a rebuilt
# release cannot silently pick up different upstream bytes.
FROM quay.io/keycloak/keycloak:26.7.0@sha256:1362a9d9f13ab325231ea133610cc905e12805804abc7acbef552dd613720aa6

# Pre-compile with required features — no secrets baked in
RUN /opt/keycloak/bin/kc.sh build \
    --db=postgres \
    --health-enabled=true \
    --metrics-enabled=true

# Non-secret runtime defaults. Only the DB credential is injected at runtime.
ENV KC_DB=postgres \
    KC_DB_URL=jdbc:postgresql://postgres:5432/sealai

ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
# Hostname, proxy, and HTTP behavior stay runtime-configured through compose/env.
CMD ["start", "--optimized"]
