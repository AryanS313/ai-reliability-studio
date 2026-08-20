# Migration guide

## From the legacy SQLite app

The application automatically runs additive SQLite migrations on startup. Before first upgrade:

1. Stop writes and copy the SQLite file to backup storage.
2. Configure `DATABASE_PATH` or `DATABASE_URL` to the existing file.
3. Start the upgraded application once and inspect `schema_migrations`.
4. Verify legacy projects, documents, prompts, runs, and result rows.
5. Run the migration and workspace-isolation tests from the test suite against a disposable copy.

Legacy rows are assigned to the default local workspace. Existing IDs and result columns are preserved. New version records, normalized executions/scores, and workspace identifiers are added. Unknown user tables are not dropped.

The old global clear operation has been removed. Use the explicitly confirmed workspace-scoped clear/reset operations.

## SQLite to PostgreSQL

There is no automatic cross-database bulk copier in this release. Treat migration as a controlled data project:

1. Apply `migrations/postgres.sql` to an empty database.
2. Provision identities, workspaces, memberships, and projects.
3. Export/transform legacy inputs and results with explicit workspace mappings.
4. Import parent entities before immutable versions, then runs, executions, scores, reviews, exports, and audit events.
5. Recompute or validate hashes; never silently map two source workspaces into one.
6. Reconcile counts and spot-check provenance/result JSON.
7. Test RLS from at least two member identities before cutover.
8. Keep the source database read-only until retention policy permits deletion.

## Behavioral compatibility

- Sample FinSure onboarding remains available.
- Existing document formats, prompt comparison, provider paths, legacy dataset columns, and CSV export remain supported.
- `mock-model` is now explicitly synthetic and cannot produce readiness evidence.
- Missing provider credentials now create configuration/execution errors instead of silently returning a mock response.
- Title-only source mentions no longer earn citation-support credit.
- Quality metrics exclude infrastructure failures; error rates are separately gated.

These changes intentionally make prior optimistic results non-comparable unless re-evaluated under the new evaluator version.

## Version and rollback policy

Run manifests store the application and evaluator version. Keep prior reports and manifests during transition. Database migrations are forward/additive; roll back application code without reversing schema. Any future destructive cleanup must be a separate, reviewed migration with backups and explicit operator confirmation.
