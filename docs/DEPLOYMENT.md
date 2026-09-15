# Setup and deployment

This design-partner beta has two runtimes: a browser-hosted Python application and a native Streamlit application. The owner has authorized the integrated release. Build, CI and live acceptance results must still be recorded for the exact deployed revision; see the [release review](design-partner/release-review.md). Choose the boundary that matches the intended users and data.

## Supported environment

Python **3.11 and 3.12** are supported. Do not run with the obsolete Python 3.9 virtual environment or weaken dependencies to accommodate it. The verified local runtime is 3.12.14. Python 3.11 dependency resolution passed a dry run; local runtime tests on 3.11 are still unverified. The checked-in CI matrix runs both versions; local runtime verification is distinct from completed remote CI.

```bash
cd /Users/aryan/Desktop/Workspace/Projects/ai-reliability-studio
bash scripts/bootstrap.sh --check
bash scripts/bootstrap.sh --dev
```

The script uses an existing supported `.venv` or locates Python 3.12/3.11 for a new one. Set `PYTHON_BIN` to an absolute supported interpreter path when needed. It refuses an existing unsupported/broken `.venv`, preserves it, and explains that a backup path must be chosen manually. It never changes `.env`. Runtime and development installation both use `requirements-lock.txt` constraints; `--dev` also installs verification tools.

Manual equivalent for an **absent** `.venv`:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip check
```

An `.env` file is optional. Use shell variables for mode selection or copy selected settings from `.env.example` into a private configuration. Never overwrite an existing `.env` as part of setup and never commit credentials. Blank provider credentials are sufficient for the synthetic sample.

## Public sample mode: safe default

```bash
APP_ACCESS_MODE=public-demo .venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
```

Each Streamlit session receives a dedicated in-memory SQLite repository. The UI accepts bundled sample data only; direct-provider and external-target execution/health checks fail closed before credential resolution or network access. The configured persistent `DATABASE_URL` is not opened for the anonymous UI session.

New sessions and process restarts do not restore earlier sample data. Idle expiration defaults to 24 hours and is checked when the app next receives a request. Session cleanup and OS memory/swap behavior are not an encrypted erasure guarantee. Public sample mode must not accept confidential inputs. A publicly hosted native sample needs appropriate TLS, resource limits and abuse protection, and must verify independent sessions on the actual deployment. Verify two independent visitors on the actual deployment; local isolation tests alone do not certify its configuration.

## Browser distribution and hosting

The [browser app](https://ai-reliability-studio.a3103.chatgpt.site/) serves Studio and pinned Python/WebAssembly assets from the web host. It does not run a persistent Streamlit server for each visitor. `APP_ACCESS_MODE=browser` is set by the browser bootstrap and accepted only when `sys.platform == "emscripten"`. A native process with that environment value fails closed; it must use one of the native access modes instead.

The retained browser runtime is **Stlite 0.76.0 / Streamlit 1.41.0, Pyodide 0.26.4 / Python 3.12.1**. Native verification uses **Python 3.12.14** and its separate locked dependencies. Presentation compatibility must be checked against the embedded Streamlit version. The browser's saved-answer workflow supports uploads, explicit source review, replacements and resumable downloads. Direct generation uses a restricted provider worker; custom assistant HTTP endpoints are unavailable in this runtime. Use native local mode or import saved answers for an existing assistant.

Browser work lives in tab memory with no automatic durable save. Closing/reloading the tab or returning after the 24-hour inactivity limit clears unexported work. The resumable workspace contains source text, answers and review notes; an HTML/JSON/CSV report is not a workspace backup. Asset caches store application files, not the review workspace. Device sleep, suspended tabs and hosting failures can interrupt execution.

Build from the repository root with a supported Python and Node version from `browser_site/package.json` (CI uses Node 24). The dependency builder accepts only a fresh output directory and can reuse its verified cache:

```bash
python3.12 browser_runtime/dependencies/build_dependencies.py \
  --output browser_site/.build/browser-vendor \
  --cache browser_site/.cache/browser-dependencies
python3.12 -m unittest discover -s browser_runtime/dependencies -p 'test_*.py' -v
node --test browser_runtime/tests/fetch-worker-retry.test.mjs
cd browser_site
python3.12 scripts/assemble-runtime.py --source ..
npm ci
npm run lint
npx tsc --noEmit
npm audit
npm run build
```

Do not overwrite an existing vendor directory to bypass a failed build. Inspect the generated manifest, source hashes and compatibility checks. Never copy `.env`, runtime databases, credentials or local verification artifacts into the browser source bundle. The build produces the web wrapper and runtime assets; it does not publish them. Deploy through the existing Sites project's approved hosting workflow, retaining its identity and bindings. See [browser edition](browser-edition.md), [web wrapper build](../browser_site/README.md) and [dependency reconstruction](../browser_runtime/dependencies/README.md).

A hosted browser page requires HTTPS, `Cross-Origin-Opener-Policy: same-origin` and `Cross-Origin-Embedder-Policy: require-corp`. Verify `crossOriginIsolated` in the page and workers. Fixed same-origin Blob module entry points preserve isolation where the host omits custom asset response headers. The provider bridge requires WebAssembly workers, `SharedArrayBuffer` and `Atomics.wait`; missing capabilities fail closed. Keep the restricted provider destinations, nonstreaming response bounds, sequential execution and worker lifecycle cleanup intact. Document and source text must not enter telemetry or hosting logs.

Before marking a hosted update verified, exercise first boot, the 32-case synthetic review, saved-answer import/review/replacement/resume, session/key clearing, two independent tabs, narrow layouts and authorized provider error paths at the final origin. Real key/account acceptance requires an approved account and call; fixtures do not establish CORS or provider acceptance at that origin. A reachable landing page or health endpoint alone does not validate these workflows.

Browser dependency security is assessed separately from native `pip-audit` and the wrapper's npm audit. The pinned Stlite/Pyodide runtime includes compiled packages that cannot be replaced with native wheels. Pure-Python package updates and [scoped compiled-package advisory analysis](design-partner/browser-dependency-review.md) are tracked for this release; do not describe the browser bundle as vulnerability-free based on archive hashes or a clean wrapper audit.

## Native public container

The root Dockerfile uses a non-root runtime and an explicit source copy list that excludes credentials, environment files and databases. Start a local preview with explicit sample-only mode:

```bash
docker build -t ai-reliability-studio .
docker run --rm -e APP_ACCESS_MODE=public-demo -p 127.0.0.1:8501:8501 ai-reliability-studio
```

A public installation needs HTTPS with WebSocket support and resource/abuse controls. Keep XSRF protection enabled. `/_stcore/health` checks process availability; separately exercise the UI. In native public-demo mode, custom uploads, provider-key execution and external assistant calls remain disabled even if an allowlist is set. Restart policies do not override a host's inactivity policy; see [hosting options](HOSTING_OPTIONS.md).

## Private design-partner workspace

```bash
APP_ACCESS_MODE=local .venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
```

`local` is an explicit trusted-operator mode. It stores versioned inputs/results in SQLite and has no login boundary. Keep its bind address at `127.0.0.1`; do not expose it through a public tunnel or shared reverse proxy. `APP_ENV=production` refuses local access mode.

Use **Start → Prepare → Connect → Evaluate → Review → History**. The custom flow requires data-handling acknowledgment and a saved project. The Connect form supports a question field and answer JSON path without authoring a target configuration file. For example, a POST endpoint accepting `{"question":"..."}` and returning `{"answer":"..."}` uses question field `question` and answer path `$.answer`. Provide a session-only credential through the password control. Save makes no call; health or test requests require explicit consent.

For advanced protocols use the form's optional request/response fields or `examples/external_target.json` with the CLI. Set `APP_ACCESS_MODE=local` explicitly for real CLI calls. Local loopback HTTP targets are supported for transport development; ordinary remote targets require HTTPS and must pass destination checks. Local reference servers validate transport only, not a real assistant's quality.

The public/private distinction is enforced by the adapters as well as the UI. Direct providers use official destinations, bounded transport timeouts, no SDK retry doubling, and no inherited base-URL/proxy/organization routing. External credential references resolve supplied values; only trusted code can opt into named environment secrets. An endpoint that echoes a configured key is rejected before its response is saved or scored.

## Shared authenticated hosting: prerequisites

This is a separately validated deployment, not a switch that makes the local beta enterprise-ready:

- Trusted identity proxy that strips incoming `X-Auth-*` headers, injects verified identity, and blocks direct access to the app backend.
- Provisioned users, workspace memberships and roles; disabled/revoked users and identity freshness checked on every rerun. A changed identity requires a fresh session.
- A currently supported managed PostgreSQL release, TLS, an appropriate application role, RLS, migrations, retention, tested backups and restore.
- Restricted egress/host allowlists, secret management, request/upload/rate limits, TLS termination, sanitized monitoring and incident ownership.
- Durable worker/artifact/scheduler adapters if runs must survive web-process restarts.
- Scanner/parser isolation and any needed OCR, configured before accepting data that depends on those controls. Required malware scanning fails closed if no scanner exists.

Illustrative environment settings (supply `DATABASE_URL` and credentials through managed secrets, not this file):

```dotenv
APP_ACCESS_MODE=authenticated
APP_ENV=production
AUTH_MODE=oidc-proxy
AUTH_TRUSTED_PROXY=true
AUTH_ALLOWED_EMAIL_DOMAIN=example.com
AUTH_REQUIRE_ISSUED_AT=true
AUTH_SESSION_MAX_AGE_SECONDS=3600
RETENTION_DAYS=90
LOG_RETENTION_DAYS=30
REQUIRE_MALWARE_SCAN=true
EXTERNAL_TARGET_ALLOWED_HOSTS=assistant-staging.example.com
ALLOW_PRIVATE_EXTERNAL_TARGETS=false
```

The trusted proxy must provide `X-Auth-Subject`, `X-Auth-Email`, and `X-Auth-Issued-At`; `X-Auth-Name` is optional. Merely adding these headers to an untrusted client request is not authentication. `AUTH_MODE=single-user` cannot serve authenticated production workspaces. A UI mode setting does not replace secure ingress, database permissions, or host egress restrictions.

After these controls are in place, the private backend may bind an address reachable **only by the trusted proxy**:

```bash
.venv/bin/python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Do not disable XSRF protection or CORS to work around proxy errors. Configure secure forwarding, request limits and timeouts at the edge. The checked-in Streamlit configuration defaults to loopback and disables Streamlit usage statistics.

## Database rollout and recovery

1. Verify backups and a restore rehearsal before a real migration.
2. Apply `migrations/postgres.sql` using a suitably privileged migration role.
3. Provision identities, workspaces and memberships, then use the restricted application role for serving traffic.
4. Verify two-workspace reads/writes/exports and role restrictions with RLS enabled, including revoked identity and reruns.
5. Check the app's exact deployment data paths, migration idempotency and recovery before admitting partner data.

Repository operations use explicit workspace predicates and transaction-local `ars.workspace_id`. SQLite migration preserves earlier versions and associates legacy data with the local workspace. Review migration effects on a copy of existing data before moving an established workspace to shared hosting.

Additive migrations reduce rollback risk but **do not guarantee that every older application version can read newer data**. Preserve backups, verify backward compatibility, and roll back the application only to a tested compatible revision. Do not drop tables/columns during an incident as a shortcut. `migrations/README.md` and `docs/MIGRATION_GUIDE.md` describe the implemented schema process.

## Verification and CI

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy src
.venv/bin/pytest
.venv/bin/python -m pip check
.venv/bin/python -m pip_audit --strict
```

PostgreSQL service tests require a **disposable database** and explicit reset permission. The fixture resets its test schema; never point it at a workspace database. Provision an empty test database, set `TEST_POSTGRES_URL` privately, then run:

```bash
TEST_POSTGRES_ALLOW_RESET=true .venv/bin/pytest -m postgres tests/test_postgres_integration.py --no-cov -q
```

For the entire suite with no service skips, use the same disposable `TEST_POSTGRES_URL` and reset flag with `.venv/bin/pytest`. Without that URL, PostgreSQL cases skip and must be reported as unverified. The recorded complete local run used a disposable PostgreSQL 16.2 test binary via a private Unix socket; it is not a recommended managed deployment version.

The CI workflow configures Python 3.11/3.12 checks, dependency consistency/auditing, bootstrap preflight, Ruff/formatting, mypy, tests with branch-enabled coverage, and a synthetic CLI smoke whose expected exit is 2. A separate disposable PostgreSQL service job verifies migration/RLS behavior. Browser distribution and container jobs also exercise their build/startup boundaries. The release record must distinguish configured jobs from completed CI runs for the integrated revision. Vulnerability audits depend on a reachable advisory service; a failed/unavailable audit is not a clean result.

The [release review](design-partner/release-review.md) records final integrated results and manual-testing limitations. Offline provider/HTTP fixtures do not prove a live account/key or real customer endpoint works.

## Operations and remaining adapters

The bundled executor/queue is in process; artifacts are host-local; the local schedule registry only records configuration. Durable execution, scheduling, scanning/OCR, retention jobs, shared storage, monitoring/alerts and backup operations require deployed adapters and tests. Do not advertise these as production services merely because their interfaces exist.

Monitor terminal run accounting, execution errors, latency, unknown/retried costs, queue/resource limits, database health, authentication/authorization failures and privacy findings. Keep payloads out of telemetry. Enforce `LOG_RETENTION_DAYS` in external sinks; the app cannot delete data already copied to an external log service. Workspace audits retain authorization metadata and fixed product events; the latter contain no prompts, answers, documents, credentials or free-form personal data. See the [security review](design-partner/security-review.md) and [success-metric dictionary](design-partner/success-metrics.md).
