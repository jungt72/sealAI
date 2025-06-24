# keycloak/Dockerfile

FROM quay.io/keycloak/keycloak:26.2.0

COPY themes /opt/keycloak/themes
COPY realm-export.json /opt/keycloak/data/import/realm-export.json

RUN /opt/keycloak/bin/kc.sh build

ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
CMD ["start", "--import-realm"]
