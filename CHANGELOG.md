# Changelog

All notable changes are documented here. The project follows semantic versioning for application and evaluator behavior.

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
