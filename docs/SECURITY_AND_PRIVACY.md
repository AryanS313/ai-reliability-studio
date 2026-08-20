# Security and privacy

## Threat model

Protected assets include customer documents, evaluation datasets, prompts, target configuration, provider responses, credentials, scores, review comments, exports, and audit history. Primary threats are cross-workspace access, forged identity headers, credential persistence/leakage, malicious uploads, decompression abuse, prompt injection, PII disclosure, unsafe external targets, destructive operations, and misleading quality evidence.

## Identity and authorization

- Development defaults to a single local user. `APP_ENV=production` refuses `AUTH_MODE=single-user`.
- Production supports trusted proxy/OIDC-proxy headers only when `AUTH_TRUSTED_PROXY=true`; the edge proxy must strip client-supplied identity headers and inject authenticated values plus `X-Auth-Issued-At`. Control characters, stale/future sessions, unknown/disabled users, revoked memberships, and sessions older than a user's revocation timestamp are rejected.
- Membership roles are owner, admin, editor, reviewer, and viewer. Repository methods re-check persisted membership and minimum role.
- All workspace-owned reads/writes include `workspace_id`. PostgreSQL adds RLS as defense in depth.
- Cross-workspace project, run, execution, review, and export identifiers are rejected.

## Secrets

Persisted target configurations may contain `secret://NAME` references only. Raw secret-like values are rejected. Runtime resolvers use environment or deployment-managed secret values. Sanitized errors, metadata, structured logs, audit payloads, and reports redact secret fields/patterns.

Do not place secrets in prompts, documents, datasets, CLI arguments, filenames, or Git. Rotate a credential immediately if it may have entered a run or log.

## Uploads and extraction

The loader sanitizes filenames, enforces extension and size limits, limits batch/document count, detects duplicates, constrains extracted character counts, sanitizes HTML, and rejects unsafe archive paths/decompression conditions. Legacy `.doc` receives an actionable conversion error. Image-only PDF content is not guessed; use a separately isolated OCR worker with its own limits.

File parsing libraries process untrusted input. Keep pinned dependencies updated, run parsers with least privilege, and restrict egress. The loader accepts an isolated malware-scanner adapter and fails closed in production when scanning is required but unavailable. Its OCR extension records the provider and never treats an unavailable OCR result as successful extraction.

## Privacy and retention

Evaluation data may contain personal or regulated information. Collect only what is necessary. The UI provides an explicit privacy notice and redacted exports; production-log ingestion redacts secrets and can redact detected PII. Detection is defense in depth, not a substitute for source-system minimization.

Workspace retention is configurable. Purge operations are owner-only, workspace scoped, transactional, and audited while immutable audit history is retained. A legal-hold-aware retention policy interface exists for deployment orchestration. Backups, replicas, object storage, observability systems, and exported files need matching deletion and retention controls outside this repository.

## Destructive actions

There is no destructive global database reset. Clearing results requires admin authorization and explicit confirmation; resetting a workspace requires owner authorization and deletes only that workspace’s entities. Audit history is retained. Always back up production storage before migrations or bulk retention operations.

## External target controls

External URLs require HTTPS outside local development. Production refuses an empty host allowlist, resolves approved hosts before each call, rejects private/reserved DNS results, disables redirects, and verifies the final response URL did not change origin. Request/response byte limits, TLS verification, and timeouts are enforced. The deployment network must still enforce approved egress as defense in depth. Authentication failures, 429s, invalid JSON paths, oversized responses, and response-shape errors are sanitized execution failures.

## Reports, logs, and exports

Reports carry immutable run/candidate/input/evaluator/threshold provenance, evidence classification, calibration/review status, execution counts, and limitations. PII redaction is on by default, secret references are removed, CSV cells are protected against spreadsheet formula injection, and exports over the configured row limit are rejected rather than assembled unboundedly in memory. Export creation is workspace-scoped and audited.

Structured logs redact authentication headers, API keys, secret references, cookies, tokens, and detected PII. Correlation and run IDs remain available, while errors are categorized as user, evaluator, provider, internal, or security events. Sanitizer failures emit a content-withheld event and cannot alter an evaluation result. `LOG_RETENTION_DAYS` defines the expected sink cutoff; the external log backend must enforce deletion.

## Prompt injection and evidence integrity

Retrieved documents and user questions are untrusted input to the target assistant. Test prompt-injection behavior explicitly. The evaluation platform never treats target instructions as system authority, never promotes suggested prompts automatically, and never allows a target-provided citation to validate evidence that was not retrieved.

## Production checklist

- PostgreSQL backups and restore drill completed.
- RLS enabled and tested with at least two workspaces and the application database role.
- TLS, trusted proxy header stripping, user provisioning, and role mapping verified.
- Secrets supplied by a managed runtime; no raw secrets in database/logs/exports.
- Network egress allowlist, timeouts, rate limits, and request-size controls enabled.
- File malware scanning and parser isolation configured.
- Retention/deletion policy covers primary storage, backups, logs, and exports.
- Error monitoring and health probes contain no sensitive payloads.
- Synthetic mode disabled or visibly segregated from production evidence.
- Incident response owner and private vulnerability reporting route established.
