# Changelog

This technical changelog complements the [living product history and PM handoff](docs/PRODUCT_EVOLUTION.md). Package version, application release, evaluator identity and hosting version are separate; they do not independently prove deployment or readiness.

## Application 2026.09.17.1 — hosted custom workflow correction

Merged through [Restore secure custom reviews on the main website](https://github.com/AryanS313/ai-reliability-studio/pull/13); all five [merged-main checks](https://github.com/AryanS313/ai-reliability-studio/actions/runs/35162489389) passed. The primary Streamlit site reports this release and its custom project, preparation, consented HTTPS connection, synthetic review, downloads and independent-session behavior were exercised there. Exact receipts and remaining acceptance limits are in the [hosted workflow review](docs/design-partner/hosted-workflow-review.md). Package remains 1.0.0, evaluator `deterministic-v8`, report schema 2.1. The optional browser deployment remains on application `2026.09.16.1`.

- Correct the unapproved sample-only restriction: make isolated, temporary custom workspaces the native default. Keep project preparation, uploads, prompt editing, assistant/provider setup, consented execution, review, comparisons and exports on the main website.
- Explain Connect and Evaluate choices as **My existing assistant** or **A model with my documents**; clarify the test name, assistant address and temporary access key after the owner identified confusing terminology.
- Record the owner's non-negotiable main-site requirement in `AGENTS.md`; customer onboarding must never require a terminal, installation or local workspace.
- Preserve per-visitor memory databases, fresh session credentials, privacy acknowledgment and explicit external-call consent; prevent use of deployment-owner keys and shared persistent storage.
- Bound session/database/run/call capacity and retries. Permit public HTTPS assistant endpoints through validated DNS, pinned TLS and redirect/proxy restrictions; keep private destinations blocked.
- Process document and question files in credential-stripped subprocesses with bounded input/output, one parser slot, CPU/wall-time limits and Linux address-space limits. These are resource controls, not an OS sandbox or malware scanner.
- Add private project download/resume with schema and checksum validation, single restore admission and atomic rollback. Restored real-run history is explicitly unverified; synthetic history stays synthetic and qualifying calibration is not imported. Credentials must be entered again.
- Fix malformed restored cases/targets, valid token-usage paths incorrectly detected as secrets, and successful HTTPS responses rejected after their completed socket closed. Preserve execution failures outside quality averages.
- Align visible upload limits with validators: ordinary hosted files 2 MiB, connection settings 1 MiB, project archives 20 MiB. Preserve the older browser runtime's uploader API.
- Extend hosted workflow, isolation, transport, parser and restore regressions; add Linux container import checks. Frozen local verification: **1,205 passed, zero skipped**, including six PostgreSQL tests; **87.53% coverage**; Ruff, formatting, mypy, native dependency checks and diff checks passed.
- Preserve the complete product history, correction rationale, measured versus missing evidence, operating limits and deployment distinctions. Real-account acceptance, independent usability, customer retention and commercial outcomes remain unvalidated; Cloudflare migration remains paused.

## Application 2026.09.16.1 — design-partner browser beta

Published as Sites version 8; package remains 1.0.0. GitHub publication/CI state is maintained in the living history and release report.

- Narrow the primary workflow to support-assistant release review with six primary steps and a one-action 32-case synthetic example.
- Replace primary JSON/configuration displays with readable decisions, evidence, forms and optional engineering exports.
- Enforce privacy/project/role prerequisites, explicit credentials and external-call consent, sample-only native public mode and private browser sessions.
- Integrate saved-answer review, source fidelity, replacement comparisons and workspace restoration from September main.
- Advance evaluation to `deterministic-v8` and reports to schema 2.1; preserve critical failures, calibration/compatibility limits and unknown measurements.
- Add privacy-safe local product events, a full metric dictionary, design-partner discovery plan and living product-evolution record.
- Patch compatible browser dependencies and document retained compiled-package advisories with actual Wasm reachability evidence.
- Pin patched setuptools for Python 3.11 installations after remote auditing exposed inherited tooling; explicitly select the private workspace for CLI smoke checks without weakening public-mode or synthetic-verdict safeguards.

## September 7–8, 2026 — public workflow repairs

Historical application releases 2026.09.07.1 through 2026.09.08.2; evaluator progressed from v6 to v7. These changes were merged before the current design-partner integration.

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
