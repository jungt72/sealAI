CREATE USER postgres WITH SUPERUSER PASSWORD 'postgres';
CREATE DATABASE keycloak OWNER postgres;
CREATE USER keycloak WITH PASSWORD 'keycloak';
