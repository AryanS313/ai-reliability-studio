# Database migrations

SQLite development databases are migrated additively by `src.migrations`. The
migrator creates `schema_migrations`, adds workspace/version columns, backfills
legacy rows into the default local workspace, and creates immutable version
records. It never drops an application table.

PostgreSQL production deployments apply `migrations/postgres.sql` using the
application migration command. The schema includes foreign keys and workspace
row-level security. Back up the database, verify restore capability, apply the
migration with a migration-capable role, then test the policies using the less
privileged application role before deploying a new release. See
`docs/MIGRATION_GUIDE.md` for the compatibility and cutover procedure.
