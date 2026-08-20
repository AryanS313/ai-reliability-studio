# Implementation report

## Outcome

The repository was transformed from a single-user demo dashboard with global SQLite state, overlap scoring, and silent mock fallback into a versioned, workspace-scoped reliability evaluation platform.

## Critical correctness prevention

The original evaluator could award a high score to an answer that reversed a policy constraint—for example, saying refunds after 30 days **are** eligible without fraud when the source says they are **not** eligible unless fraud is suspected. The new deterministic constraint evaluator identifies negation and exception conflicts, labels a policy contradiction, caps correctness at 0.15 and overall quality at 0.25, assigns high hallucination risk, and blocks launch regardless of average or advisory judge output. A required regression test preserves this behavior.

## Delivered

- Additive SQLite migrations, PostgreSQL schema/RLS, immutable versions, normalized executions/scores, audit/export/review entities, RBAC, and workspace isolation.
- Honest synthetic execution, direct provider adapters, external HTTP target adapter, secret references, sanitized explicit failures, and no provider-to-mock fallback.
- Strict datasets, structural extraction/chunking, provenance, duplicate/upload controls, hybrid retrieval, and retrieval metrics.
- Bounded execution, retry/backoff, timeouts, cancellation, resume/checkpoints, cache, and idempotency.
- Claim/citation/escalation/safety evaluators, multiple acceptable answers/rubrics, deterministic contradiction overrides, explanations, confidence, and advisory-judge policy.
- High-precision contextual PII detection and proposition/scope-aligned contradiction checks, including citation-ID, Luhn, conditional-policy, and numeric-boundary regressions.
- Held-out human-label calibration with immutable evaluator/threshold versions, per-label confusion matrices and observed error rates, persistence, UI workflow, and insufficient-evidence gating.
- Candidate-specific gates/counts, confidence intervals, comparisons/regressions, reports, CLI/CI, human review foundations, drift/log ingestion, health, metrics, retention, and redaction.
- Updated Streamlit onboarding, target setup, preflight, dataset coverage, run history/comparison, paginated failure analysis, candidate dashboards, scoped destructive actions, and audited exports.
- Pinned dependencies, Ruff, mypy, branch-aware coverage threshold, unit/integration/UI tests, legal/security/contribution files, examples, architecture/methodology/security/deployment/migration documentation, and changelog.

## Compatibility

The FinSure demo, supported file formats, local SQLite setup, provider integrations, prompt comparison, legacy dataset columns, and legacy result/export fields are retained. Behavior that produced misleading evidence was intentionally tightened: synthetic results are non-launch evidence, provider failures do not become mock successes, and title-only citations do not prove support.

## Remaining deployment risks

- Exercise the PostgreSQL migration/RLS against the chosen managed PostgreSQL version and application role before production cutover.
- Replace the non-production in-memory queue, local artifact/schedule adapters, and unavailable scanner/OCR adapters with durable managed implementations before production use.
- Validate exact provider model availability/pricing and external target egress allowlists in the deployment environment.
- Establish representative held-out datasets and human-review calibration; the included examples are demonstrations, not production acceptance evidence.

## Verification

The supported Python 3.12/OpenSSL environment now passes:

- 145 unit, integration, migration, tenant-isolation, evaluator, target, execution, reporting, operational, and Streamlit UI tests, with four PostgreSQL-service tests skipped locally and available in the dedicated CI profile;
- 76.96% branch-aware source coverage against a required 70% threshold;
- Ruff lint and formatting checks with no findings;
- mypy over all 34 source modules with no findings;
- `pip check`, `git diff --check`, SQLite migration/health checks, Streamlit server startup, and the CLI synthetic-evidence smoke assertion.

The synthetic CLI intentionally exits with code 2 and reports `Synthetic demonstration — no launch verdict`; CI asserts this behavior rather than ignoring the failure.
