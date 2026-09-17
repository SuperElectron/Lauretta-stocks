#!/bin/sh
# Runs once, after 00-schema.sql, when the db volume is first created (as the owner, a superuser).
#
#   lauretta_app       what api and worker query as: reads and writes rows, nothing else. No
#                      superuser and no BYPASSRLS, so row-level security holds for it.
#   lauretta_migrator  creates and owns LangGraph's checkpoint tables (the worker's
#                      DATABASE_SETUP_URL, at startup). No superuser, no BYPASSRLS and no rights on
#                      the user tables, so the worker never holds a superuser password.
#
# Passwords are read inside psql (\getenv), so they never show in the process list. They are set
# here once: to change one later, run `ALTER ROLE <role> PASSWORD '...'` as the owner too.
set -eu
: "${DB_APP_PASSWORD:?set DB_APP_PASSWORD (the lauretta_app role's password)}"
: "${DB_MIGRATOR_PASSWORD:?set DB_MIGRATOR_PASSWORD (the lauretta_migrator role's password)}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv app_password DB_APP_PASSWORD
\getenv migrator_password DB_MIGRATOR_PASSWORD
CREATE ROLE lauretta_app LOGIN PASSWORD :'app_password'
    NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE ROLE lauretta_migrator LOGIN PASSWORD :'migrator_password'
    NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
GRANT CONNECT ON DATABASE :"DBNAME" TO lauretta_app, lauretta_migrator;
GRANT USAGE ON SCHEMA public TO lauretta_app;
GRANT USAGE, CREATE ON SCHEMA public TO lauretta_migrator;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO lauretta_app;
-- The checkpoint tables lauretta_migrator creates later.
ALTER DEFAULT PRIVILEGES FOR ROLE lauretta_migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO lauretta_app;
ALTER DEFAULT PRIVILEGES FOR ROLE lauretta_migrator IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO lauretta_app;
SQL
