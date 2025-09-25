CREATE USER keycloak WITH PASSWORD 'Katerkimba!1';
CREATE DATABASE sealai_db OWNER keycloak;
GRANT ALL PRIVILEGES ON DATABASE sealai_db TO keycloak;
