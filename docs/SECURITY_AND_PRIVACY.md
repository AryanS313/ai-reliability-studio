# Security and privacy

## What this beta protects

Protected assets include documents, datasets, prompts, assistant configuration, credentials, responses, scores, human reviews, exports, and audit history. Threats considered include cross-session/workspace access, spoofed identity, secrets in responses, unsafe uploads/endpoints, destructive actions, and misleading evaluation evidence.

## Access modes

| Configuration | Intended use | Storage and access |
|---|---|---|
| `APP_ACCESS_MODE=public-demo` (default) | Anonymous sample walkthrough | One in-memory SQLite database per Streamlit session. Sample-only; no custom uploads, provider keys, real model calls or external HTTP calls. |
| `APP_ACCESS_MODE=local`, `APP_ENV=development`, `AUTH_MODE=single-user` | A trusted design partner evaluating approved test data on their computer | Persistent configured SQLite workspace. Start with `--server.address 127.0.0.1`. Anyone who can reach this server is the same trusted operator; never expose it remotely. |
| `APP_ACCESS_MODE=authenticated`, `APP_ENV=production`, `AUTH_MODE=proxy` or `oidc-proxy` | Shared installation with operator-managed infrastructure | Verified proxy identity, provisioned memberships, PostgreSQL and row-level security; requires the controls below. This is an integration boundary, not a claim of operational production readiness. |

Unknown access modes fail closed. Local mode is refused in production. Anonymous state never opens the configured persistent database. Request context is bound independently on every UI rerun, including download callbacks. Changing identity within an existing session discards its UI state, including documents, results and runtime keys, before another screen is rendered.

### Authenticated installation

`AUTH_TRUSTED_PROXY=true` means the operator has verified that the reverse proxy strips user-supplied `X-Auth-*` headers, supplies authenticated `X-Auth-Subject`, `X-Auth-Email`, and `X-Auth-Issued-At`, and prevents clients from reaching Streamlit directly. Setting this variable alone does not create that security boundary.

`AUTH_REQUIRE_ISSUED_AT` defaults to true in production; `AUTH_SESSION_MAX_AGE_SECONDS` defaults to 3600. `AUTH_ALLOWED_EMAIL_DOMAIN` can narrow access. Unknown/disabled users, revoked memberships, invalid/stale/future issue times, and sessions before a user's revocation timestamp are refused. Every repository operation checks the persisted role rather than trusting a role supplied by a caller. Admins cannot grant ownership or alter owner memberships.

Repository queries scope projects, assets, runs, results and exports to workspace membership. PostgreSQL policies add a second boundary. Validate the deployed application database role, proxy, and two independent identities before shared use. Tests on a disposable PostgreSQL service are useful evidence about application queries, not proof of a production network boundary.

## Credentials and external calls

Public-demo provider and external adapters reject real calls before network access. Private sessions may use entered credentials or explicitly configured provider credentials. Password fields are memory-only. Saved target configuration stores references such as `secret://SESSION_EXTERNAL_AUTH`, never the resolved value. `SecretResolver` reads only explicitly supplied values by default; access to environment secrets requires a trusted caller's `environment_names` allowlist. A user-supplied reference cannot extract an arbitrary server environment variable.

External target configuration rejects credential-bearing query parameters, fragments, embedded URL credentials, raw authentication/API-key/cookie header values, header injection, transport/proxy-header overrides, and raw credential fields in request templates. These checks do not identify every possible proprietary string. Do not put credentials in custom paths or ordinary text fields.

Both provider and external transports compare returned data against known runtime credentials. A credential echo is discarded as an invalid response, carries no quality score, and requires rotation/investigation. Errors and reports also redact known secret field names/patterns and secret references. Redaction cannot prove that arbitrary confidential content is absent; review exports before sharing.

Provider SDK transports use official provider origins and ignore inherited alternate base URLs/proxies and ambient credentials. External HTTP requests use HTTPS with certificate/hostname verification; loopback HTTP is permitted only for development. The actual connection pins a validated DNS address while preserving the original TLS hostname, preventing a second DNS lookup from switching destinations. Redirects and inherited HTTP proxies are not followed. DNS resolution rejects non-public/reserved/multicast addresses by default; local loopback development is the exception.

`EXTERNAL_TARGET_ALLOWED_HOSTS` is a comma-separated exact hostname allowlist and is mandatory in production. Keep `ALLOW_PRIVATE_EXTERNAL_TARGETS=false` unless a trusted operator has separately restricted private-network egress. Limits are `MAX_EXTERNAL_REQUEST_BYTES` (2 MiB), `MAX_EXTERNAL_RESPONSE_BYTES` (5 MiB), configured target timeouts, and bounded retries. Retried external requests require an idempotent assistant endpoint; connection checks make one explicitly authorized call and do not establish answer quality. Missing health paths never produce a fabricated successful health check.

## Uploads

Public-demo accepts no custom files. Private custom workflows require an approved-data acknowledgement and saved project. The loader sanitizes filenames, bounds file/batch size, checks supported extensions, limits archive expansion and extracted output, detects duplicates, and retains extraction warnings. Current defaults are `MAX_UPLOAD_BYTES=20971520`, `MAX_DOCUMENTS_PER_UPLOAD=50`, `MAX_EXTRACTED_CHARACTERS=5000000`, and `MAX_DATASET_ROWS=10000`. Legacy `.doc` needs conversion; image-only PDFs need a separately configured OCR service.

The local beta parses operator-approved files in the app process. It does not claim malware isolation. `REQUIRE_MALWARE_SCAN` defaults to true when `APP_ENV=production`; ingestion refuses when the required scanner is missing/unavailable. An OCR extension records whether text was actually extracted; no guessed text is substituted. Shared ingestion additionally requires sandboxed workers, maintained parsers, least privilege and restricted egress.

## Storage, privacy, retention and deletion

Local/authenticated runs store source text, prompts, questions, expected answers, assistant answers and provenance to make evidence inspectable. Real requests send selected inputs to the provider/endpoint shown in preflight. Use approved test data and review the provider's agreements and the deployment's access policy before sensitive use. The UI acknowledgement is enforced; it is not a substitute for those agreements.

Public session data lives in process memory and disappears when the session repository is released or the process exits. There is no promised 24-hour retention window or persistent public history. Memory may remain while Streamlit retains a disconnected session, and operating systems may retain swap. The public boundary therefore remains sample-only.

Persistent workspaces default to `RETENTION_DAYS=90`. Expiration requires the owner-scoped purge operation or a configured scheduler; setting the variable alone does not run deletion. Audit history is retained by reset/purge operations. Backups, replicas, object storage, exported files and log sinks require separate retention/deletion controls. `LOG_RETENTION_DAYS=30` describes the expected log-sink policy; the sink must enforce it.

The UI restricts destructive operations to owners, requires the exact confirmation phrase, and targets only the active workspace. The repository requires admin for clearing results and owner for reset/purge. Global database reset is removed. PostgreSQL test fixtures deliberately reset a schema and refuse unless `TEST_POSTGRES_ALLOW_RESET=true`; use only a disposable database.

Privacy-safe product events use fixed names and allowlisted numeric/boolean/enumerated fields with a random session identifier. They contain no document content, questions, prompts, answers, credential values, email addresses or free-text notes. Workspace IDs may associate events with local projects without sending them to a third-party analytics service. Inspect the event schema before adding fields.

## Evidence and exports

Runs separate infrastructure failures from scored answers. Failed execution does not become a synthetic success or raise quality averages. Synthetic scenarios are explicit workflow fixtures and cannot receive a real launch verdict. Citation/contradiction checks, unknown evidence, independent calibration, confidence intervals and comparison compatibility are separate constraints; inspect limitations and the underlying source before accepting a finding.

Source/prompt/dataset/target versions and run manifests preserve provenance. Only the latest document version enters a reopened corpus; earlier versions remain stored as history. Repeating persistence of the same execution is idempotent: it cannot create extra scores or inflate completion counts. Server-reported model identity stays distinct from requested configuration.

HTML/JSON/CSV reports redact execution data, summary values, metadata and candidate labels. Secret references are removed, HTML is escaped, formula-like CSV cells are escaped, and `MAX_EXPORT_ROWS` bounds export size. Export clicks are workspace-scoped and audited. Redaction is incomplete by nature: a human must review confidential exports.

## Requirements before shared production use

The local beta does not supply managed identity, a verified trusted proxy, managed/current PostgreSQL operations, durable worker/queue/artifact services, malware scanning, OCR, encrypted backups, restore drills, automatic retention, centralized monitoring, incident response, or deployment-specific egress validation. Those are operator dependencies and must be verified before hosting confidential multi-user data. Keep public sharing on the sample-only mode until that work is complete.

The live service was not altered during this task. Do not infer its effective access mode or isolation from local source alone. Follow an owner-approved deployment with independent two-session verification before asserting live controls.
