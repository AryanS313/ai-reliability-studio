# Design-partner success metric dictionary

Version 1 — 16 September 2026. Owner: product lead. This is a measurement contract and proposed pilot targets, **not a claim of traction or achieved targets**. Local test results belong in the verification report; customer measures remain unmeasured until research or pilot usage occurs.

## Measurement rules

- The outcome to optimize is **a team making a documented, evidence-supported decision about an actual assistant revision**, then returning when another revision needs evaluation. A high score, passing verdict, page view, or demo run is not that outcome.
- Categories have distinct questions: acquisition = whom we reach; activation = first value; workflow = completing a task; integrity = whether evidence is valid; reliability = whether execution works; security = whether permitted boundaries hold; retention = return behavior; outcomes = value to the customer; operability = ability to maintain the service. One event may support more than one metric; do not sum unlike metrics into a health score.
- Cohort unit is an eligible **team/project**, not a browser, seat, or fabricated visitor identity. Within a local session, a session identifier can measure a path; it cannot identify a returning person. Deduplicate runs by stored run identity and intentional action, not Streamlit rerenders.
- Split synthetic, real foundation-model, external-assistant, and local test-harness activity. Demo completion measures onboarding only. Real customer activation, retention, and outcomes exclude synthetic runs, internal tests, and founder-assisted demonstrations unless separately labeled.
- Report numerator, denominator, dates, environment, assistance, and exclusions. A zero denominator is **not measurable**, not 0% or 100%. Missing events do not imply success. For fewer than 20 teams, show counts prominently; pilot thresholds are learning rules, not statistically validated benchmarks.
- Product targets below are initial hypotheses for the first 5–10 eligible partner teams. Security/integrity invariants apply even at sample size one. Targets are not service-level commitments.
- Keep evaluation scores and case evidence inside the authorized project. Calculate aggregate measurements there; never copy case contents to product analytics. Synthetic fixture results establish code behavior, not evaluator validity on partner language and policies.

### Baseline notation

| Code | Meaning |
|---|---|
| U-C | Customer baseline unmeasured: no recruited-cohort data or independent user study supplied. Do not substitute local agent testing. |
| U-R | Runtime baseline unmeasured: no prospective, instrumented pilot operating window. Existing run records are not automatically representative. |
| V | Supported-runtime pre-change baseline, recorded by the coordinating audit on Python 3.12.14 at `d2fb73e`: **145 passed, 4 PostgreSQL tests skipped, 76.96% reported coverage**. Skipped services were unverified at this baseline. Use the dated final verification report for post-change results and exact diff; this supersedes the earlier Python 3.9 compatibility harness. |
| S-13 | Pre-change source inspection found 13 top-level navigation destinations in `app.py`. This is a structural proxy, not measured cognitive load, task time, or completion. |

The dictionary intentionally retains these pre-change baselines. Record observed post-change values in a dated scorecard with sample sizes; do not silently rewrite a baseline after improving the product.

### Sources and instrumentation boundary

- **E — product events:** allowlisted local events from `src/product_analytics.py` and its application call sites. The schema recognizes `session_started`, `project_created`, `project_reopened`, `sample_loaded`, `document_ingested`, `dataset_saved`, `target_configured`, `target_health_checked`, `run_started`, `run_completed`, `report_viewed`, `comparison_viewed`, `report_exported`, `decision_recorded`, and `workflow_error`. The implementation is authoritative about which attributes and event calls exist. Schema support is not proof that every UI/CLI path emits an event, nor an implemented aggregate dashboard.
- **R — repository records:** versioned manifests, executions, evaluations, comparison outputs, calibration, and review/audit records, queried only within the authorized workspace. Do not export underlying prompts, documents, answers, names, or credential values into telemetry.
- **H — human research:** consented task observations, domain-reviewer adjudication, and de-identified pilot totals kept outside analytics/repository. Raw personal/contact data stays in a separately controlled research record, not event payloads.
- **T — verification:** automated tests, browser/AppTest observations, package/audit checks, and setup/migration/recovery rehearsals with a dated environment record.
- **O — operating observations:** deployment probes, resource measurements, and sanitized incident summaries. Managed collection and alerting are deployment responsibilities; local process counters do not establish uptime.

Allowed event attributes are fixed enums, booleans, bounded numeric counts/durations, and necessary local application entity references. Deny arbitrary free text, filenames, target URLs, project names, referrers, IPs, user agents, emails, user identifiers, raw exception messages, prompts, answers, document text, or credentials. Do not fingerprint public visitors or join separate public-demo sessions. Audit authentication metadata, if present in the storage envelope, is access-control data and must not become marketing telemetry. Do not describe an audit-backed sink as fully anonymous.

Implemented property groups are `mode`, `target_type`, `outcome`, `stage`, `format`, `decision`, and `next_action` enums; non-negative bounded `project_id`, `run_id`, case/execution/scored/error/document/chunk/action counts; `synthetic` and `ranking_supported` booleans; and bounded finite `duration_ms`. `journey_id` is a random 32-character hexadecimal value (passed as `session_id` to the event API, then stored under a name distinct from authentication session credentials) and the schema is versioned. Source/channel qualification, consent state, human understanding, release opportunities, and customer outcomes require H/T/R evidence; they are not silently inferred from fields the event schema does not collect.

The beta has **no external analytics collector**. Any central analytics or cross-device cohort tracking needs a separately reviewed data contract and deployment controls. Research metrics can be recorded manually as de-identified counts; they do not justify adding tracking fields. Deletion/retention follows the documented workspace policy and audit retention limits; the privacy notice must not promise that browser closure immediately purges every audit record.

## 1. Acquisition and qualification

### A1 — Qualified opportunities reached

- **Definition / formula:** number of distinct teams reached in the recruitment window that meet all ICP filters: support/knowledge assistant, actual staging endpoint, upcoming revision, engineer, and domain owner. Count each team once per 30-day window.
- **Required source / baseline:** H recruitment ledger with coded eligibility only; **U-C**.
- **Target / failure threshold:** 6 qualified conversations in the first 30 days of authorized recruiting; fewer than 3 triggers an audience/channel review.
- **Guardrail / validation:** no credit for general interest, student demos, internal tests, or unverified endpoint ownership; product lead reviews eligibility against concrete recent-release artifacts.
- **Owner / classification:** product lead; **leading**.

### A2 — Qualified reach share

- **Definition / formula:** qualified teams ÷ all teams completing screening in the same channel/window. Unanswered screenings are reported separately, never classified as qualified.
- **Required source / baseline:** H coded screening totals, optionally a manually selected channel enum; **U-C**.
- **Target / failure threshold:** at least 60%; below 40% across 10 screenings triggers positioning/recruitment changes.
- **Guardrail / validation:** publish channel and denominator; do not buy traffic to inflate reach or discard disqualified contacts from the denominator. Audit screening criteria before recruitment.
- **Owner / classification:** product lead; **leading**.

### A3 — Evaluation-ready qualification

- **Definition / formula:** qualified teams with approved test data, endpoint access, and an identified release/domain owner available within seven days ÷ qualified teams screened.
- **Required source / baseline:** H readiness checklist containing coded yes/no states, not credentials or personal names; **U-C**.
- **Target / failure threshold:** at least 70%; below 50% after 6 qualified teams means adoption prerequisites are too costly or recruitment is premature.
- **Guardrail / validation:** access must be actually authorized; do not count promised production-data access or omit security review. Verify with the team, not product-event inference.
- **Owner / classification:** product lead with partner engineering owner; **leading**.

## 2. Activation and time-to-value

### B1 — Unassisted sample completion

- **Definition / formula:** first-time participants who load the sample, finish a synthetic run, and reach its report without assistance ÷ all first-time participants who attempt the sample. Report event completion separately from human understanding.
- **Required source / baseline:** E `session_started` → `sample_loaded` → `run_completed` → `report_viewed`, plus H assistance log; **U-C** (local golden-path success is T only).
- **Target / failure threshold:** at least 4 of 5 independent participants; fewer than 4 of 5 blocks the claim of unassisted onboarding readiness.
- **Guardrail / validation:** do not count retries as new successes or exclude abandoned attempts. Fresh-session browser task, screen observation with consent, and event reconciliation.
- **Owner / classification:** product/UX owner; **leading**.

### B2 — Sample time and action budget

- **Definition / formula:** elapsed time from first visit to first report, reported as median/p90; intentional clicks, field submissions, and navigation actions per completed task. Report abandonments and time-to-abandon separately.
- **Required source / baseline:** E timing where implemented; H stopwatch/action log for the full task; **U-C**, with **S-13** as the pre-change structural burden proxy.
- **Target / failure threshold:** median ≤5 minutes and ≤8 intentional actions; median >10 minutes or >12 actions after 5 participants triggers simplification.
- **Guardrail / validation:** no removed safety confirmation solely to reduce clicks; no excluding slow users or provider waits from elapsed time. Human action count, with page load/setup timings stated.
- **Owner / classification:** product/UX owner; **leading**.

### B3 — First real evidence activation

- **Definition / formula:** evaluation-ready teams that complete a non-synthetic run and have a domain owner identify one actionable finding or missing-evidence condition within seven days ÷ evaluation-ready teams starting the pilot.
- **Required source / baseline:** E target/run/report events plus R non-synthetic manifest and H comprehension/decision observation; **U-C**.
- **Target / failure threshold:** at least 4 of 5 teams; fewer than 3 of 5 triggers workflow/ICP review.
- **Guardrail / validation:** a `report_viewed` event is only a proxy; require the reviewer to explain an actual case and limitation. A passing verdict is unnecessary and cannot be manufactured by lowering gates.
- **Owner / classification:** product lead and partner domain owner; **leading**.

### B4 — Time to first real evidence

- **Definition / formula:** wall time and active operator time from evaluation-ready pilot start to B3 activation; report median and each stalled reason. Endpoint/data access delays before readiness are reported under A3.
- **Required source / baseline:** H observation and E project/target/run/report timestamps; **U-C**.
- **Target / failure threshold:** median active time ≤45 minutes and wall time ≤1 working day; active time >90 minutes or wall time >3 working days after 5 teams triggers intervention.
- **Guardrail / validation:** retain cancellations/noncompleters in the funnel; report assistance and dataset preparation separately. Do not relabel synthetic output as real value.
- **Owner / classification:** product/UX owner; **leading**.

## 3. Core workflow effectiveness

### C1 — Assistant connection success

- **Definition / formula:** teams whose intended HTTP assistant returns a schema-valid health-check response and at least one successful real test execution using documented setup ÷ teams attempting a compatible assistant connection.
- **Required source / baseline:** E `target_configured`, `target_health_checked`, `run_completed`; R adapter status; H assistance record; **U-C** and **V** for fixtures.
- **Target / failure threshold:** ≥80% without custom code, median setup ≤15 minutes; <60% or any undocumented mandatory step triggers an integration review.
- **Guardrail / validation:** unsupported protocols are reported as exclusions, not successes; fixture servers do not count as partner connections. Test missing/bad credentials, mappings, timeouts, and recoverability.
- **Owner / classification:** engineering lead; **leading**.

### C2 — Configuration and input recovery

- **Definition / formula:** task attempts with invalid/duplicate/unsupported inputs that the operator resolves to a usable project/dataset/target without restarting ÷ attempts encountering those states. Separately count accepted project-associated inputs ÷ attempted valid inputs.
- **Required source / baseline:** E `workflow_error`, document/dataset/target events; H task outcomes; T malformed/oversized/duplicate cases; **U-C** and **V**.
- **Target / failure threshold:** ≥90% recovery and 100% valid assets/runs project-associated; <80% recovery or any orphan/cross-project asset blocks affected workflow.
- **Guardrail / validation:** rejected unsafe inputs are correct behavior; do not weaken validation to improve acceptance. Verify field-level fixes preserve user work and duplicate notices do not duplicate data.
- **Owner / classification:** engineering/UX owner; **leading**.

### C3 — Decision comprehension

- **Definition / formula:** participants correctly explaining all five points—what failed, severity/reason, next change, evidence type, and missing evidence—÷ participants reviewing a report. For comparison tasks add whether a candidate improved on comparable cases.
- **Required source / baseline:** H neutral teach-back rubric; E `report_viewed`/`comparison_viewed` are exposure proxies only; **U-C**.
- **Target / failure threshold:** ≥4 of 5 correct unaided; any synthetic-as-real interpretation blocks that readiness claim, and <4 of 5 triggers report redesign.
- **Guardrail / validation:** no leading questions or success credit for reading a headline. Include execution-error-only, insufficient-calibration, critical-failure, and incompatible-comparison reports.
- **Owner / classification:** product/UX owner with domain reviewer; **leading**.

### C4 — Actionable decision capture

- **Definition / formula:** completed real-run review tasks ending with a coded decision and a concrete next action ÷ completed real-run review tasks. Count decision outcomes (fix/review/collect evidence/limited rollout), not only approvals.
- **Required source / baseline:** E `decision_recorded` and H confirmation of next action; R review state; **U-C**.
- **Target / failure threshold:** ≥80%; <60% after 10 review tasks means the report is not driving action.
- **Guardrail / validation:** no forced “approve” defaults or free-text customer content in analytics. Record a decision once per reviewed run/revision and verify the action addresses an observed case or evidence gap.
- **Owner / classification:** partner release owner; **leading**.

## 4. Evaluation integrity

### D1 — Evidence provenance completeness

- **Definition / formula:** reported candidates with resolvable prompt/model/target/dataset/document/retrieval/evaluator/gate versions and inspectable case results ÷ reported candidates.
- **Required source / baseline:** R manifests, evaluation evidence, and exports; T round-trip/reproducibility tests; **V**.
- **Target / failure threshold:** 100%; any readiness report lacking required provenance is a release blocker.
- **Guardrail / validation:** record “not applicable/unknown” honestly; source title alone is not claim support. Verify reports against immutable stored inputs and source references.
- **Owner / classification:** evaluation engineering owner; **leading**.

### D2 — Misleading verdict count

- **Definition / formula:** count of synthetic candidates receiving launch-readiness verdicts, critical contradictions being rescued by averages, or missing required calibration/coverage being presented as sufficient.
- **Required source / baseline:** R gate outputs plus T synthetic, contradiction, insufficient-evidence, UI/export/CLI cases; **V**.
- **Target / failure threshold:** 0; any instance blocks release.
- **Guardrail / validation:** no target for pass rate. Test UI, JSON/CSV/HTML, and CLI semantics, including negative fixtures and partial runs.
- **Owner / classification:** evaluation engineering owner; **leading**.

### D3 — Execution/quality separation violations

- **Definition / formula:** count of failed target executions receiving quality scores or improving candidate quality aggregates; also report scored successes ÷ successful executions expected to be scored.
- **Required source / baseline:** R execution/error/score joins and T authentication/rate-limit/timeout/provider/malformed-response tests; **V**.
- **Target / failure threshold:** 0 violations; any violation blocks release. Score coverage should be 100% of valid successes or show an explicit evaluator failure.
- **Guardrail / validation:** errors remain in the execution-error denominator and cannot disappear from the report. Recompute aggregates from raw status/score records without treating missing scores as zero or pass.
- **Owner / classification:** evaluation engineering owner; **leading**.

### D4 — Held-out evaluator validity

- **Definition / formula:** per required failure label, precision = TP/(TP+FP), recall = TP/(TP+FN), FPR = FP/(FP+TN), with sample counts; reviewed only on independent held-out human labels for the exact evaluator/threshold version.
- **Required source / baseline:** R calibration and H adjudicated labels; **U-C** for partner domains; T fixture outcomes are **V**, not human validity.
- **Target / failure threshold:** default observed precision ≥0.90, recall ≥0.80, FPR ≤0.05, ≥30 held-out cases and ≥5 positive/negative examples per label; any unmet configured requirement must yield insufficient calibration.
- **Guardrail / validation:** disclose small samples, annotator disagreement, and representativeness; development/tuning examples cannot count. Version changes invalidate applicability until reassessed. Do not call observed rates a population guarantee.
- **Owner / classification:** evaluation owner and independent domain reviewer; **lagging**.

### D5 — Comparison validity

- **Definition / formula:** displayed release comparisons that use stable matched case identities, compatible dataset/evaluator/gate and candidate scope, and explicit missing/incompatible-case handling ÷ displayed release comparisons.
- **Required source / baseline:** R manifests/comparison output; T changed dataset, target, threshold, missing-case, and candidate tests; **V**.
- **Target / failure threshold:** 100%; any unsupported “better/safer” claim blocks release.
- **Guardrail / validation:** a changed dataset is not automatically a quality gain; missing cases are not passes. Surface per-case regressions and serious failures alongside deltas; rerun uncertainty limits remain visible.
- **Owner / classification:** evaluation engineering owner; **leading**.

## 5. Reliability and performance

### E1 — Application run completion

- **Definition / formula:** accepted run jobs that reach a persisted terminal state with all attempted cases accounted for ÷ accepted jobs; target quality failures and properly recorded provider failures can still be terminal jobs.
- **Required source / baseline:** E `run_started`/`run_completed`, R job/manifest/execution state; **U-R**, T execution checks **V**.
- **Target / failure threshold:** ≥99% in the pilot window; <95%, a hung job without a recovery path, or unexplained missing cases triggers engineering review.
- **Guardrail / validation:** user cancellations are a separate terminal state, not silently discarded; failures of target execution remain E2. Reconcile started/terminal IDs, including process interruption.
- **Owner / classification:** engineering/operations owner; **lagging**.

### E2 — Target execution error rate

- **Definition / formula:** cases ending in infrastructure/authentication/timeout/rate-limit/invalid-response errors ÷ all attempted real cases, after the configured retry policy; also report attempt counts and error-category mix.
- **Required source / baseline:** R execution statuses and adapter timings; E run summary counts; **U-R**.
- **Target / failure threshold:** ≤5% for a healthy configured staging target; >10% across a run requires investigation, and the candidate's versioned gate remains authoritative for its verdict.
- **Guardrail / validation:** no provider-to-synthetic fallback, successful retries retain attempt cost, and cancellation is separate. Inject each error class and verify it is visible and unscored.
- **Owner / classification:** partner engineer with product engineering owner; **lagging**.

### E3 — Responsiveness and availability

- **Definition / formula:** p50/p95 local application action latency; sample run wall time for a fixed case count; healthy probes ÷ expected probes during an explicitly monitored serving window. External target latency is reported separately.
- **Required source / baseline:** T repeatable timing harness and O probes; E durations where implemented; **U-R** and **V**.
- **Target / failure threshold:** p95 ordinary navigation <2 seconds, 32-case synthetic sample <30 seconds on the documented machine, ≥99% availability in monitored pilot hours; >5 seconds navigation, >60 seconds sample, or <95% availability triggers investigation.
- **Guardrail / validation:** report hardware, case count, warm/cold state, period, and probe gaps; no uptime claim from a one-off health check. Slow/error cases stay in timing reports.
- **Owner / classification:** engineering/operations owner; **lagging**.

### E4 — Retry, resume, and resource control

- **Definition / formula:** injected retry/cancel/resume/idempotency scenarios preserving accounted cases and declared retry/call bounds ÷ such scenarios; resource overruns = runs exceeding documented call/concurrency/upload/storage limits.
- **Required source / baseline:** T failure injection and O bounded stress measurements; R idempotency/retry metadata; **V**.
- **Target / failure threshold:** 100% expected recovery behavior and 0 unbounded resource overruns; any duplicate execution outside documented guarantees or ignored bound blocks the affected path.
- **Guardrail / validation:** upstream HTTP services may not implement idempotency; document that limit rather than claim exactly-once external side effects. Measure memory/storage at configured maxima; keep test loads bounded.
- **Owner / classification:** engineering owner; **leading**.

## 6. Safety, privacy, and security

### F1 — Isolation and authorization violations

- **Definition / formula:** count of unauthorized cross-session, cross-workspace, cross-project, or role-forbidden reads/writes/exports/deletions in adversarial checks or observed operation.
- **Required source / baseline:** T two-session/two-workspace role matrix, backend repositories and export checks; O sanitized incidents; **V**, operating baseline **U-R**.
- **Target / failure threshold:** 0; any reproducible violation blocks release immediately.
- **Guardrail / validation:** hiding a UI control is not authorization; exercise APIs/repositories directly and separate fresh visitor sessions. Zero observed incidents alone is not proof; test applicable database/RLS identity paths.
- **Owner / classification:** security/engineering owner; **leading** tests, **lagging** incidents (reported separately).

### F2 — Privacy and external-call consent compliance

- **Definition / formula:** custom-data operations and real external calls preceded by enforced required privacy acknowledgment and explicit call confirmation ÷ such operations/calls; public-demo privileged/custom operations blocked ÷ attempted prohibited operations.
- **Required source / baseline:** T session-state and handler bypass tests; E coded consent/action states if implemented, R run manifests; **V**.
- **Target / failure threshold:** 100%; any custom persistence or external call bypassing its applicable guard blocks release.
- **Guardrail / validation:** acknowledge actual data flow and call count; no prechecked consent, hidden environment credential use, or provider calls during a supposedly local sample. Retest after target/model changes.
- **Owner / classification:** security/engineering owner; **leading**.

### F3 — Sensitive telemetry/export leakage

- **Definition / formula:** count of test secrets or sensitive fixture values detected in product events, logs, persisted target configuration, or redacted exports; product-event schema violations = accepted disallowed payload fields/values.
- **Required source / baseline:** T canary payload tests and static/serialized artifact inspection, E strict-schema rejection tests; **V**.
- **Target / failure threshold:** 0 leaks and 0 accepted forbidden fields; any credential leak or content in analytics blocks release.
- **Guardrail / validation:** absence of a regex match does not prove arbitrary text safe; telemetry uses an allowlist. Check nested/list/URL/exception paths and non-text report formats. Redaction remains a best-effort boundary for unstructured content.
- **Owner / classification:** security/engineering owner; **leading**.

### F4 — Unsafe input and destination rejection

- **Definition / formula:** blocked invalid/oversized/unsupported/archive-abuse/path-traversal/unsafe-endpoint test cases ÷ prohibited test cases; separately report false rejection of supported valid inputs.
- **Required source / baseline:** T upload/extraction and target-network matrix; E coded `workflow_error` counts; **V**.
- **Target / failure threshold:** 100% prohibited cases rejected before unsafe processing/calling, with actionable messages; any bypass blocks the affected release path.
- **Guardrail / validation:** reject redirects/private destinations according to network policy and preserve extraction warnings. Do not claim malware-free uploads from a local placeholder scanner; allowed formats and deployment boundary remain explicit.
- **Owner / classification:** security/engineering owner; **leading**.

### F5 — Destruction and retention compliance

- **Definition / formula:** authorized deletion/retention checks that require the documented confirmation and remove only in-scope eligible data while preserving the documented audit record ÷ deletion/retention checks; overdue data = eligible records older than the configured retention boundary.
- **Required source / baseline:** T destructive-control, cross-workspace, and purge tests; R retention/audit records; O scheduled-purge evidence where deployed; **V**, operating baseline **U-R**.
- **Target / failure threshold:** 100% scoped confirmed deletion behavior; 0 overdue records after the documented purge SLA. Any unintended data loss or false deletion guarantee blocks release.
- **Guardrail / validation:** browser close is not necessarily server-side erasure. State session/workspace expiry and audit retention separately; backups/managed schedules require independent operational verification.
- **Owner / classification:** security/operations owner; **leading** controls, **lagging** overdue records.

## 7. Engagement and retention

### G1 — Next-release repeat evaluation

- **Definition / formula:** activated teams completing another real run for a later actual assistant revision within 30 days ÷ activated teams with a later-release opportunity and a complete observation window. Report teams without an opportunity separately.
- **Required source / baseline:** R candidate/run versions, E `project_reopened`/run events, H release-opportunity confirmation; **U-C**.
- **Target / failure threshold:** ≥3 of first 5 eligible teams; ≤1 of 5 triggers an ICP/value reassessment.
- **Guardrail / validation:** exclude synthetic reruns, test traffic, duplicate retries, and researcher-run tasks. Do not track public anonymous sessions across browsers. A new project is not automatically a new release.
- **Owner / classification:** product lead; **lagging**.

### G2 — Baseline comparison adoption

- **Definition / formula:** repeat real-release evaluations with a reviewed, compatible baseline comparison ÷ repeat real-release evaluations that have a compatible prior baseline.
- **Required source / baseline:** E `comparison_viewed`, R comparison/version compatibility, H review acknowledgment; **U-C**.
- **Target / failure threshold:** ≥80%; <50% after 10 eligible repeat evaluations triggers comparison-workflow review.
- **Guardrail / validation:** incompatible baselines are counted separately, not forced into the numerator; a view is only a usage proxy until review is confirmed. Inspect per-case regressions rather than average gains alone.
- **Owner / classification:** product lead with partner engineer; **lagging**.

### G3 — Confirmed failure becomes regression coverage

- **Definition / formula:** confirmed actionable failures with a stable reviewed case included in a subsequent dataset/run ÷ confirmed actionable failures accepted for follow-up in the period.
- **Required source / baseline:** R stable case/version/review state and subsequent runs; H acceptance confirmation; **U-C**.
- **Target / failure threshold:** ≥80% within the next release cycle; <50% after 10 accepted failures means the learning loop is breaking.
- **Guardrail / validation:** deduplicate the same failure; do not reward dataset size or automatically label generated cases as representative. Verify that the case was actually executed later.
- **Owner / classification:** partner engineering/domain owner; **leading** for durable repeat value.

## 8. Commercial and customer outcomes

### H1 — Confirmed consequential regressions found

- **Definition / formula:** unique real regressions detected before a release and confirmed by the domain owner as requiring a fix or explicit risk acceptance; report counts and teams with ≥1 ÷ teams completing a review.
- **Required source / baseline:** R case/version comparison and H confirmation; **U-C**.
- **Target / failure threshold:** evidence of at least one consequential finding across the first 5 pilots; 0 triggers problem/value investigation, not relaxed scoring or a forced failure quota.
- **Guardrail / validation:** no credit for seeded fixtures, duplicates, false positives, or unsupported “avoided loss” claims. Count adjudicated false positives separately and retain cases with no regressions.
- **Owner / classification:** product lead and partner domain owner; **lagging**.

### H2 — Investigation time saved

- **Definition / formula:** paired active reviewer/engineer minutes for the same task using the previous workflow minus minutes using this product; report absolute difference and percentage of prior time, including setup and false-positive review.
- **Required source / baseline:** H timed, comparable tasks or explicitly labeled estimates; **U-C**.
- **Target / failure threshold:** median ≥30% reduction after 5 paired tasks; ≤0% or increased unresolved-error rate triggers workflow review.
- **Guardrail / validation:** do not compare expert-assisted product use with novice baseline use, omit setup, or monetize minutes without evidence. Report individual results and task differences.
- **Owner / classification:** product researcher/lead; **lagging**.

### H3 — Evidence changed the release decision

- **Definition / formula:** reviewed releases where the owner documents that a finding changed the fix priority, rollout scope, or evidence requirement ÷ reviewed real releases; changes may include delaying a release.
- **Required source / baseline:** H de-identified before/after decision record; E `decision_recorded` alone is insufficient; **U-C**.
- **Target / failure threshold:** ≥3 of 5 pilot owners identify a specific useful decision change; ≤1 of 5 triggers differentiation review.
- **Guardrail / validation:** no credit for a ceremonial report export or reproducing the predetermined decision without useful evidence. Ask for counterfactual behavior and note self-report limitations.
- **Owner / classification:** product lead and partner release owner; **lagging**.

### H4 — Design-partner continuation commitment

- **Definition / formula:** completed-pilot teams agreeing to a concrete next evaluation date, responsible role, data scope, and continuation terms ÷ completed-pilot teams asked. Report paid commitments, unpaid continuations, declined, and no response separately.
- **Required source / baseline:** H private commitment record summarized without personal data; **U-C**.
- **Target / failure threshold:** ≥3 of 5 explicit continuations, with at least one substantive willingness-to-pay conversation; ≤1 of 5 continuations triggers product/ICP review.
- **Guardrail / validation:** enthusiasm, introductions, downloads, and résumé praise are not commitments; a pricing conversation is not revenue. Signed/paid evidence is required before any revenue claim.
- **Owner / classification:** product/business owner; **lagging**.

## 9. Operability and maintainability

### I1 — Reproducible supported setup

- **Definition / formula:** clean documented installs that start the app and complete the fixed synthetic golden path on supported Python versions ÷ attempted supported-version installs.
- **Required source / baseline:** T clean Python 3.11/3.12 environment logs, dependency lock, documented commands; **V** (historical Python 3.9 compatibility harness is excluded).
- **Target / failure threshold:** 100% of supported-version checks; any unreproducible supported setup blocks a “reproducible” claim.
- **Guardrail / validation:** no weakening declared runtime or tests. Record exact Python/package versions and platform; distinguish local verification from CI configuration not actually executed.
- **Owner / classification:** engineering owner; **leading**.

### I2 — Required engineering check completeness

- **Definition / formula:** required tests/lint/format/type/dependency/diff checks executed and passing ÷ required checks; report branch-enabled total coverage and individual known exclusions separately.
- **Required source / baseline:** T pytest/coverage, Ruff, formatting, mypy, dependency consistency/vulnerability checks, Git diff checks; **V**.
- **Target / failure threshold:** 100% required local checks passing, reported branch-enabled coverage ≥repository threshold (70% at baseline), no unresolved critical/high vulnerability affecting the release path; any critical-path failure blocks release.
- **Guardrail / validation:** a skipped PostgreSQL test is not a pass; coverage does not substitute for security assertions. Retain justified exclusions and dependency findings with affected paths and remediation status.
- **Owner / classification:** engineering owner; **leading**.

### I3 — Diagnosis and recovery readiness

- **Definition / formula:** injected application/database/provider failures producing a sanitized diagnostic, an identifiable affected run, and a documented successful recovery ÷ rehearsed failure scenarios; also measure active minutes to diagnose/recover.
- **Required source / baseline:** T failure injection, O sanitized logs/health checks, recovery runbook; **V**, real incident timing **U-R**.
- **Target / failure threshold:** 100% covered critical scenarios; local recovery ≤15 minutes on the fixed fixture. Missing diagnostic, leaked content, or unrecoverable data requires release-path remediation.
- **Guardrail / validation:** use reason codes and entity IDs, not payload logging. Do not equate local recovery with durable-worker/backups guarantees; rehearse actual deployment infrastructure before making those claims.
- **Owner / classification:** engineering/operations owner; **leading**.

### I4 — Migration and maintenance burden

- **Definition / formula:** supported storage migrations preserving expected records/isolation ÷ migration rehearsals; unplanned operator maintenance minutes ÷ active partner-week, reported alongside support incidents.
- **Required source / baseline:** T fresh/upgrade/idempotent migration tests, H/O maintenance log with coded tasks; **V** for migrations, **U-R** for burden.
- **Target / failure threshold:** 100% migration invariants and ≤60 unplanned maintenance minutes per active partner-week; any data-loss migration blocks release, or >120 minutes for two weeks triggers architecture/scope review.
- **Guardrail / validation:** include manual work and support supplied by the creator; do not call it “zero maintenance” because unpaid. Exact managed database version, app role, identity, backup, and recovery paths need separate verification.
- **Owner / classification:** engineering/operations owner; **leading** migration readiness, **lagging** maintenance burden.

## Anti-metrics: what must never define success

| Tempting number | Why it can be gamed | Required companion evidence |
|---|---|---|
| Total visitors, stars, downloads | Not evidence of ICP reach, evaluation need, or use | A1–A3 qualified teams and real release triggers |
| Runs or tokens processed | Synthetic runs, retries, or needless calls inflate activity | Separate evidence types, unique candidate revisions, E2 error rate, bounded cost |
| Mean score / pass rate | Easy datasets, missing cases, or weaker gates can manufacture gains | D1–D5 provenance, critical failures, calibration, comparable-case coverage |
| “Ready” verdicts | Correctly blocking a release can be more valuable | H1/H3 confirmed decision utility; no quota for approvals |
| Fast time-to-value | Omitting privacy, setup, calibration, or failure review makes it falsely fast | B3 real comprehension, F2 safeguards, abandonment/assistance counts |
| Report views / exports | May be accidental or ceremonial | C3 teach-back, C4 next action, H3 decision change |
| Daily active users | Evaluation is release-triggered; daily use can indicate repeated failure | G1 next-release opportunity retention and G2 baseline use |
| Failures found | False positives, seeded tests, or duplicated cases inflate value | Domain adjudication, false-positive review time, H1 unique real regressions |
| “No incidents” | No users or no visibility can look safe | F1–F5 adversarial checks, observed exposure window, I3 diagnostics |
| Coverage percentage | Untested boundaries or shallow assertions can remain | Critical workflow/security matrix and meaningful negative assertions |
| Testimonials / willingness to pay | Unprompted praise is not a commitment | Permissioned dated customer evidence and H4 concrete continuation |
| Portfolio impressiveness | Incentivizes broad features without adoption | Honest discovery, prioritized changes, repeated real use, and measured outcomes |

## Review cadence and decision rights

Before each local release: engineering owns D/F/I invariant checks and the critical golden paths. At every partner run: engineer/domain owner reviews execution health, case failures, missing evidence, and compatibility; the partner retains the release decision. Weekly during pilots: product lead reviews A/B/C friction, G repeat opportunities, H confirmed value, and qualitative counterevidence. Monthly: revise ICP/targets with a dated change log, without rewriting prior denominators or results.

Until independent participants and a real approved endpoint are available, A/B/C/G/H customer targets remain **unmeasured external validation**, not “done.” Engineering results can justify a local reviewable beta; they cannot establish adoption or domain accuracy.
