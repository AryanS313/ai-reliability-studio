# Setup and deployment

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env
streamlit run app.py
```

Local mode uses SQLite and an explicit single-user workspace. Do not load proprietary or regulated data into a public demo.

## Production prerequisites

- Python 3.11 or 3.12 with pinned `requirements.txt`. Do not use the macOS system Python 3.9/LibreSSL runtime;
  create a fresh virtual environment from a supported CPython build.
- Managed PostgreSQL with backups, TLS, and migration privileges.
- Trusted authentication proxy that strips inbound `X-Auth-*` headers and injects `X-Auth-Subject`, `X-Auth-Email`, and optional `X-Auth-Name`.
- Runtime-managed provider/external-target secrets.
- TLS termination, restrictive egress, rate limiting, upload scanning, centralized logs, and error monitoring.
- Durable worker/scheduler if evaluations must survive web-process restarts.

Minimum runtime configuration:

```dotenv
APP_ENV=production
AUTH_MODE=oidc-proxy
AUTH_TRUSTED_PROXY=true
AUTH_ALLOWED_EMAIL_DOMAIN=example.com
AUTH_REQUIRE_ISSUED_AT=true
AUTH_SESSION_MAX_AGE_SECONDS=3600
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/ars
RETENTION_DAYS=90
LOG_RETENTION_DAYS=30
REQUIRE_MALWARE_SCAN=true
EXTERNAL_TARGET_ALLOWED_HOSTS=assistant-staging.example.com,assistant.example.com
ALLOW_PRIVATE_EXTERNAL_TARGETS=false
```

Do not put the database password in a checked-in `.env`; the example only names the variable. Configure model IDs and pricing values for the exact providers approved by your organization.

## Database rollout

1. Back up and verify restore capability.
2. Apply `migrations/postgres.sql` using the application migration role.
3. Provision users, workspaces, memberships, and roles.
4. Run two-workspace isolation checks with the application role and RLS enabled.
5. Start the application and call the repository health check.

The application sets transaction-local `ars.workspace_id` for workspace queries. Keep explicit application predicates and RLS enabled.

## Process model

Run Streamlit behind the authenticated reverse proxy:

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Do not disable XSRF protection. Do not enable permissive CORS as a workaround for proxy configuration. Configure forwarded headers, secure cookies, request limits, and idle timeouts at the edge.

The bundled web executor and `InMemoryJobQueue` are in process. `LocalArtifactStore` is host-local and `LocalScheduleRegistry` only records configuration; all explicitly declare themselves non-production. For durable production runs, implement the shipped queue, artifact, scheduler, malware-scanner, and OCR interfaces using managed services. Persist leases, heartbeats, cancellation, checkpoints, and idempotency in PostgreSQL or the queue backend. Production document ingestion fails closed when `REQUIRE_MALWARE_SCAN=true` and no scanner is supplied.

## CI

GitHub Actions installs pinned development dependencies, runs Ruff, format verification, mypy, the 70% branch-aware coverage gate, unit/integration/UI tests, and an explicit synthetic workflow smoke test whose expected result is a blocked launch gate. Artifacts include coverage and the synthetic report.

For real-target regression gates, inject a narrowly scoped test secret and use a non-production endpoint/dataset. Never run destructive or customer-facing targets from untrusted pull requests.

## Operations

- Monitor execution counts/status, p95 latency, error rates, gate failures, queue age, database health, and cost warnings.
- Alert on authentication failures, cross-workspace authorization failures, retention failures, high execution error rate, and critical safety labels.
- Keep logs structured and payload-free where possible. Secret/PII redaction is defense in depth.
- Configure the log/trace sink to enforce `LOG_RETENTION_DAYS`; the application exposes the cutoff policy but cannot delete records held by an external sink.
- Test backup restore, cancellation/resume, rate-limit behavior, and dependency/provider outage scenarios.

## Rollback

Application rollback is safe because migrations are additive. Do not attempt to drop new tables/columns during an incident. Roll back the application image, retain new data, and investigate compatibility before any later cleanup migration.
