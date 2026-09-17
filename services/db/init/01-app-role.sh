#!/bin/sh
# Runs once, after 00-schema.sql, when the db volume is first created (as the owner, a superuser).
# Creates `lauretta_app`, the role api and worker connect as: it logs in, reads and writes rows,
# and can do nothing else. It is no superuser and has no BYPASSRLS, so row-level security holds
# for it. The checkpoint tables are created later by the owner (the worker's DATABASE_OWNER_URL),
# so default privileges grant it those as they appear.
set -eu
: "${DB_APP_PASSWORD:?set DB_APP_PASSWORD (the lauretta_app role's password)}"

psql -v ON_ERROR_STOP=1 -v app_password="$DB_APP_PASSWORD" \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE ROLE lauretta_app LOGIN PASSWORD :'app_password'
    NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
GRANT CONNECT ON DATABASE :"DBNAME" TO lauretta_app;
GRANT USAGE ON SCHEMA public TO lauretta_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO lauretta_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO lauretta_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO lauretta_app;
SQL
