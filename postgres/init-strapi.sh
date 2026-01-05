#!/usr/bin/env bash
set -euo pipefail

echo "Initializing Strapi database/user..."

: "${STRAPI_DB_NAME:=strapi_db}"
: "${STRAPI_DB_USER:=strapi_user}"
: "${STRAPI_DB_PASSWORD:?STRAPI_DB_PASSWORD must be set}"

export PGPASSWORD=${POSTGRES_PASSWORD:-}

psql_cmd=(psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER")

user_exists=$("${psql_cmd[@]}" -tAc "SELECT 1 FROM pg_roles WHERE rolname='${STRAPI_DB_USER}'")
if [[ "$user_exists" != "1" ]]; then
  "${psql_cmd[@]}" -c "CREATE ROLE \"${STRAPI_DB_USER}\" LOGIN PASSWORD '${STRAPI_DB_PASSWORD}';"
else
  "${psql_cmd[@]}" -c "ALTER ROLE \"${STRAPI_DB_USER}\" WITH PASSWORD '${STRAPI_DB_PASSWORD}';"
fi

db_exists=$("${psql_cmd[@]}" -tAc "SELECT 1 FROM pg_database WHERE datname='${STRAPI_DB_NAME}'")
if [[ "$db_exists" != "1" ]]; then
  "${psql_cmd[@]}" -c "CREATE DATABASE \"${STRAPI_DB_NAME}\" OWNER \"${STRAPI_DB_USER}\";"
else
  "${psql_cmd[@]}" -c "ALTER DATABASE \"${STRAPI_DB_NAME}\" OWNER TO \"${STRAPI_DB_USER}\";"
fi

"${psql_cmd[@]}" -c "GRANT ALL PRIVILEGES ON DATABASE \"${STRAPI_DB_NAME}\" TO \"${STRAPI_DB_USER}\";"

echo "Strapi DB initialization complete."
