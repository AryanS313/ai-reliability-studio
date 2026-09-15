# Changelog

All notable changes are documented here. The project follows semantic versioning for application and evaluator behavior.

## Unreleased — public workflow repairs

- Add guided sample, saved-answer import/review/export/resume, and live-evaluation paths while retaining advanced project tools.
- Keep automatic checks separate from explicit source reviews, preserve AI-assisted attribution, and compare only the supplied replacement cases.
- Isolate anonymous visitors in temporary per-session databases and require session-supplied keys. Explicit deletion clears that visitor's data and keys.
- Repair the pinned provider transports and Claude Sonnet 5 sampling parameters; distinguish requested settings from provider defaults and preserve usage when a provider returns no answer text.
- Preserve numeric token budgets during secret redaction so foundation-model targets can be saved and run. Keep actual credential fields redacted.
- Apply the runtime dependency constraints to Community Cloud installs and expose the app release in Settings for deployment verification.
- Repair constraint, citation, escalation, uncertainty, reporting, and calibration provenance handling. Evaluator `deterministic-v6` addresses scoped exemptions, epistemic abstentions, and unverified citation support; these are regression fixes, not a general accuracy claim.
- Add a non-root container with a health check and CI startup verification. Community Cloud hibernation remains a host limitation; hosting guidance documents the separate always-running requirement.

## 1.0.0 — 2026-08-20

### Added

- Workspace identity, RBAC, tenant-scoped repositories, additive SQLite migrations, PostgreSQL schema/RLS, immutable input versions, audit logs, export records, retention controls, and review entities.
- Synthetic, foundation-model, and external HTTP target adapters; execution retries/backoff, concurrency, cancellation, resume/checkpoints, caching, and idempotency.
- Strict versioned datasets, structured document provenance, hybrid retrieval and retrieval metrics.
- Claim-level groundedness, exact citation support/completeness, structured escalation, hard constraint checks, safety labels, candidate gates, confidence intervals, regressions, reports, CLI and CI.
- Human review, drift/log ingestion, structured observability, security/privacy/deployment/migration documentation, examples, and UI smoke tests.
- Held-out evaluator calibration UI/persistence, candidate-centric dashboards and comparisons, layered redacted failure analysis, provenance-rich reports, and deterministic synthetic failure scenarios.
- Explicit durable queue, artifact-store, scheduler, malware-scanner, OCR, and legal-hold-aware retention interfaces with non-production local adapters.

### Changed

- Mock behavior is generic, prompt independent, visibly synthetic, and ineligible for launch verdicts.
- Provider/configuration failures are explicit execution errors and are excluded from quality scoring.
- Launch readiness is computed independently per prompt/model/target candidate.
- Citation correctness requires evidence support; a source title alone no longer passes.
- Destructive actions are explicit and workspace scoped.
- Trusted proxy sessions enforce issued-at freshness and persisted user/membership revocation; external HTTP targets reject DNS rebinding and redirects.

### Preserved

- FinSure onboarding, existing file formats, local SQLite, provider selection, prompt comparison, legacy dataset/result columns, and CSV export.
