# SealAI Keycloak – build an optimized image on the validated 26.5.7 line.
# Path: keycloak/Dockerfile

FROM quay.io/keycloak/keycloak:26.5.7

# Pre-compile with required features — no secrets baked in
RUN /opt/keycloak/bin/kc.sh build \
    --db=postgres \
    --health-enabled=true \
    --metrics-enabled=true

# Non-secret runtime defaults — credentials injected via env at container start
ENV KC_DB=postgres \
    KC_DB_URL=jdbc:postgresql://postgres:5432/sealai

ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
# Hostname, proxy, and HTTP behavior stay runtime-configured through compose/env.
CMD ["start", "--optimized"]
