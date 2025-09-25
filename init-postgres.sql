-- Erstelle den Benutzer keycloak, falls er nicht existiert
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'keycloak') THEN
        CREATE ROLE keycloak WITH LOGIN PASSWORD 'Katerkimba123';
    END IF;
END $$;

-- Wechsle zur Datenbank sealai_db (bereits durch POSTGRES_DB erstellt)
\connect sealai_db

-- Gewähre keycloak Berechtigungen für sealai_db
GRANT ALL PRIVILEGES ON DATABASE sealai_db TO keycloak;

-- Gewähre keycloak Zugriff auf alle Tabellen im Schema public
GRANT ALL ON SCHEMA public TO keycloak;
