# SealAI Keycloak – enable health + metrics at build time (KC 25.x)
# Path: keycloak/Dockerfile

FROM quay.io/keycloak/keycloak:25.0.4

# Build-time features so /health/* works
RUN /opt/keycloak/bin/kc.sh build \
    --db=postgres \
    --health-enabled=true \
    --metrics-enabled=true

# Runtime config (no secrets here)
ENV KC_DB=postgres \
    KC_DB_URL=jdbc:postgresql://postgres:5432/sealai \
    KC_DB_USERNAME=sealai

ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
CMD ["start", "--optimized", "--http-enabled=true", "--hostname-strict=false"]
