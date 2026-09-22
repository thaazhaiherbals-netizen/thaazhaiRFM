# Understanding the two environments

An environment is the same application code connected to different settings and
data. We develop using local data, then deploy the reviewed code with live settings.

## Local (daily work)

- Root `.env.local`: backend/database settings on this computer.
- `apps/web/.env.local`: frontend's public API address, localhost:8000.
- `compose.yaml`: starts PostgreSQL and Python API in Docker.
- Browser localhost:3000 -> API localhost:8000 -> local PostgreSQL.
- Database is accessible from your computer at localhost:5433.
- Inside Docker the API uses the service name `postgres` on port 5432.
- Database name: thaazhai_dev; username: thaazhai.
- Password is the local-only LOCAL_DB_PASSWORD value in `.env.local`.

The local database is persistent, not a temporary test database. Product seeds are
loaded locally; historical orders are not copied from Supabase. Future automated
database tests must still use a separate disposable database ending in _check,
not this development database.

Changing LOCAL_DB_USER/PASSWORD/NAME does not change existing PostgreSQL accounts
inside a previously initialized volume. These variables initialize an empty
database only. Keep the initial local credentials unless you intentionally update
the database account. Use URL-safe local credentials; if you change them, update
DATABASE_URL for native access consistently too.

## Which settings does Python read?

1. Read APP_ENV from the process environment; default is development.
2. Development reads root `.env.local`; production reads root `.env.production`.
3. Process variables override values from the chosen file (how Render works).
4. Neither file can change the environment selector.
5. Test mode reads no env file.
6. The legacy shared `.env` is ignored.

Paths are resolved relative to the repository, not your terminal directory.
Development/test connections reject remote hosts and host query overrides.
The Docker development configuration explicitly selects development and constructs
a URL for the local postgres service, independent of any live settings.

The existing db.py creates a SQLAlchemy engine from DATABASE_URL. Production forces
sslmode=require. Restart services after changing settings; configuration is cached.

## Live (later)

The production file is a private template with DATABASE_URL left empty. Supply the
Supabase PostgreSQL direct or session-pooler connection string when deploying.
Supabase URL/service-role API keys are reserved for future integrations, not needed
for current SQLAlchemy database access.

Render receives secrets in its environment settings, not committed files. It uses
APP_ENV=production. A missing production DATABASE_URL fails startup rather than
falling back to development. Production keeps its own frontend build/API URL.

An explicit native production selection would be:
`$env:APP_ENV = "production"` before starting Python. Do not use that for daily
development. Return to the default with `Remove-Item Env:APP_ENV`.
The local Docker command always starts development services.

No deploy automatically runs migrations. Because the Supabase schema and seeds
already exist, compare schema and migration history before any production change.
Completing development does not automatically copy the local database into live.

## Files in Git

Commit only example env files. Actual .env.local, .env.production and the frontend
.env.local are ignored by Git and excluded from Docker image builds.
Only the API/database receive database credentials; the frontend receives an API URL.
