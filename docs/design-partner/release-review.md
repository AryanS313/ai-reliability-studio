# Design-partner beta: release review

**Updated 17 September 2026 · Hosted correction merged and observed live · Historical baseline `feature` at `d2fb73e`**

## Decision and scope

**Acceptance correction and delivery update — 17 September 2026:** the owner rejected the agent’s unapproved sample-only/local-install restriction. The correction [merged through PR 13](https://github.com/AryanS313/ai-reliability-studio/pull/13) at `bcdd6103ca713cb7f58d8736bfa563c308cebd7f`; all five branch/PR/main jobs passed. The primary site shows native `2026.09.17.1` / evaluator v8. Custom preparation, consented public HTTPS transport, two synthetic runs with an inconclusive revision comparison, download controls, missing-key recovery and two-tab reset were observed online. **Classification: bounded hosted design-partner beta as engineering delivery; full owner definition of done unproven.** Approved real-assistant/account, independent usability/domain, actual downloaded-file/native-picker and accessibility acceptance remain missing. The earlier scope/completion mistake remains in the history; Cloudflare is paused.

**The owner has authorized committing, pushing, merging and updating the live application.** Integration combined the locally tested improvements with newer browser and saved-answer workflows from `origin/main` (integration source `3fc3e59`). Native tests, browser build and deployed-origin checks passed within sections 12–13's narrower recorded scope. That code was pushed and [merged into main](https://github.com/AryanS313/ai-reliability-studio/pull/12) at `026a3e7` after branch and PR checks passed. Those facts remain valid; they do not prove completion of the requested hosted custom journey. Those September 16 receipts are historical; the newer hosted merge and bounded live observations are recorded in section 14. The [living product history](../PRODUCT_EVOLUTION.md) preserves the full evolution and current delivery distinctions.

The earlier **573 passed / zero skipped / 85.71% coverage** result belongs to the pre-integration local candidate. Sections 2–11 preserve that phase's implementation, tests, browser observations and limitations; they are not a substitute for final verification of the combined browser/native release. Sections 12–13 record the integrated scope, completed release checks and remaining external acceptance. Independent design-partner adoption, domain validity and real-account connectivity remain unvalidated.

The obsolete Python 3.9 environment was preserved as `.venv-py39-backup`; the supported native environment is Python 3.12.14. Existing data and unrelated worktrees are preserved. The earlier integration checkout was `/Users/aryan/Desktop/Workspace/Projects/ai-reliability-studio-release`; the current working checkout is `/Users/aryan/Desktop/Workspace/Projects/ai-reliability-studio`. Verification fixtures, logs and disposable infrastructure stay outside committed application inputs.

**Baseline distinction:** the originally requested local `feature` branch was older than both main and the deployed browser app. Its historical shared-single-user default is not evidence that the newer live browser exposed visitors to one another. The integrated release preserves main's saved-answer provenance, private browser storage, provider-native instructions, source extraction and runtime boundaries while adding the guided 32-case review and stronger safeguards.

## 1. Primary ICP and product thesis

**Primary ICP:** a small team, typically 2–10 builders within a SaaS or similar company, shipping a read-only support/knowledge assistant grounded in written policies. It has a staging endpoint, an engineer and domain owner, and another release or policy change due within 30 days. These qualification filters are hypotheses to validate.

**Job:** find consequential answer, policy-exception, citation and escalation regressions before the next release, inspect the source evidence together, and decide what to fix next.

**Operator:** AI/application engineer. **Outcome owner:** PM or support/domain lead. **Sponsor:** founder or engineering/product lead. QA, agencies and risk/compliance reviewers are secondary audiences.

**Thesis:** reduce the work required to turn a staging assistant and representative cases into a repeatable release review. The wedge is a focused support-policy review with honest evidence limits; versioning, HTTP evaluation and dashboards are established competitor capabilities, not unique inventions.

**Activation:** a team completes a real versioned run and identifies an actionable finding or evidence gap with its domain owner. **Return loop:** preserve baseline → fix a confirmed issue → compare the revision on compatible cases/settings → add confirmed incidents as regression cases → repeat next release.

The [product brief](product-brief.md) covers the ten audience questions, alternatives, research citations, differentiation, non-goals and release boundary. The [discovery plan](discovery-plan.md) contains recruitment, unassisted tasks and a two-release pilot. There are no fabricated interviews, customers, savings, testimonials, usage or willingness-to-pay claims. The résumé was read solely for secondary ownership context; product choices were grounded in users, evidence and risk.

## 2. Before versus after — pre-integration local phase

The [25-gap matrix](gap-matrix.md) records every requested prioritization field: user need, baseline, evidence, severity, frequency hypothesis, trust impact, effort, priority, solution and acceptance criterion.

| Dimension | Before: requested local branch | After: locally verified candidate |
|---|---|---|
| Entry and navigation | Broad technical platform, 13 destinations | Support-release outcome, 6 primary steps; advanced tools disclosed separately |
| Sample path | 5 actions to results in a frozen-baseline AppTest | 1 action directly to a review; all 32 cases retained |
| Automated timing proxy | 2.7040 s after first render; 2.9759 s total | 0.7535 s after first render; 1.0064 s total |
| Public default | Anonymous persistent single-user workspace path | Sample-only ephemeral repository per session; no custom uploads or real calls |
| Custom prerequisites | Privacy value not enforced; implicit project association | Enforced acknowledgment, saved project, role check, scoped restoration |
| External connection | Low-level JSON required | Endpoint/question/answer/auth form, optional mappings, explicit connection check and call budget |
| Runtime | Existing `.venv` Python 3.9 | Rebuilt Python 3.12.14; safe reproducible bootstrap and constrained installs |
| Provider calls | SDK/HTTPX constructor incompatibility; ambiguous provenance | Tested real SDK transport construction; requested versus observed model; bounded retries/timeouts; safe failures |
| Verdicts and comparisons | Incomplete calibration/partial runs/incompatible versions could mislead | Required calibration scope/version, successful-case minimums, critical precedence and inconclusive incompatible comparisons |
| Interpretation | Technical pages and score-heavy output | Counts, first finding, expected/observed/source, severity, next action and missing evidence |
| Return workflow | Saved inputs difficult to restore | Reopen project, retain baseline, compare releases, record decision and export evidence |
| Analytics | No product event contract | Strict local event schema, no content or credentials; no external collector |
| Engineering checks | 145 pass, 4 PostgreSQL skips, 76.96% coverage | 573 pass, zero skips, 85.71% coverage after the plain-language follow-up; pre-integration result |

Timing is **one automated observation per path**, on the same local machine using supported Python and the current Streamlit runtime. It excludes installation, human thinking and partner integration. Frozen baseline AppTest was run from an archived pre-change tree. Neither 1/1 functional completion nor navigation count establishes human completion rate, comprehension or cognitive load. Independent baseline/after user measures remain unmeasured. Browser duplicate recovery and missing-key recovery were observed; human recovery time remains unmeasured.

## 3. MECE success scorecard

The complete [36-metric dictionary](success-metrics.md) supplies definition, formula, event/data source, baseline, target, guardrail, failure threshold, owner, validation method and leading/lagging classification for **every metric**. It also defines denominators, cohort exclusions and anti-metrics. Targets are pilot hypotheses; the baseline is retained rather than overwritten with improvements.

| Distinct category | Metrics | Current measured status |
|---|---|---|
| Acquisition and qualification | A1 qualified opportunities; A2 qualified reach share; A3 evaluation-ready qualification | Customer baseline unmeasured; no outreach performed |
| Activation and time-to-value | B1 unassisted sample completion; B2 sample time/actions; B3 real evidence activation; B4 real time-to-value | Functional one-click sample and timing proxy above; independent activation unmeasured |
| Core workflow effectiveness | C1 connection success; C2 input recovery; C3 decision comprehension; C4 actionable decision capture | Local browser/AppTest/transport checks pass; customer success/comprehension unmeasured |
| Evaluation integrity | D1 provenance; D2 misleading verdicts; D3 execution/quality separation; D4 held-out validity; D5 comparison validity | Covered invariants pass; real domain validity requires independent labels |
| Reliability and performance | E1 run completion; E2 target error rate; E3 response/availability; E4 retry/resume/resources | Fixture error/retry/recovery paths pass; no uptime, load or live-error-rate claim |
| Safety, privacy and security | F1 isolation/authorization; F2 consent; F3 leakage; F4 input/destination rejection; F5 destruction/retention | Local invariant suites pass; deployment ingress/retention/operations remain separate |
| Engagement and retention | G1 next-release repeat; G2 comparison adoption; G3 findings becoming regression coverage | Mechanisms implemented; customer behavior unmeasured |
| Commercial and customer outcomes | H1 confirmed regressions; H2 investigation time saved; H3 changed release decision; H4 continuation commitment | Unmeasured; synthetic failures and agent work are excluded |
| Operability and maintainability | I1 reproducible setup; I2 required checks; I3 diagnosis/recovery; I4 migration/maintenance | Supported environment, required checks and disposable migration tests verified; operating burden unmeasured |

**Anti-gaming rules:** do not count synthetic/internal runs as customer activation; do not count rerenders as intentional usage; do not maximize scores by removing hard cases; do not hide execution failures; do not report unknown costs as zero; do not infer retention from anonymous sessions; do not claim evaluator validity from code coverage; and do not claim saved time from estimates without labeling them.

Events are stored in the authorized workspace audit log with a random journey ID and allowlisted enums/counts/durations. They exclude document contents, prompts, answers, filenames, URLs, credentials, email/IP/user-agent fields and free text. The audit envelope retains authorization metadata; it is not fully anonymous analytics. Public sessions are not fingerprinted or joined. Acquisition, independent comprehension and outcomes use de-identified research totals; the product does not silently invent these data sources.

## 4. Material changes

### Security and custody

- Added explicit `public-demo` / `local` / `authenticated` modes; default public sample has its own anchored in-memory repository and cannot inherit host provider keys or execute real targets.
- Replaced process-global active identity/repository state with request-context binding and session initialization. Identity changes fail closed; stored membership/disabled-user state defeats forged roles.
- Enforced role ranks in custom workflows, including connection checks. Reviewers can calibrate/review; viewers can read; both can reopen permitted evidence after acknowledgment. Creation, ingestion and execution require editor access; destructive workspace controls require owner authorization and typed confirmation.
- Restricted secrets to explicit supplied values or approved environment references; kept session credentials out of stored target configuration. Added exact runtime-credential echo detection that discards unsafe responses and records critical privacy evidence.
- Hardened URL/header/template/health-path checks, destination validation, DNS pinning/TLS hostname behavior, redirect/proxy policy and resource limits. Explicit loopback HTTP remains supported in trusted local development for a local assistant; it is not general private-network access.
- Redacted complete JSON/CSV/HTML report structures, metadata and configuration fields; retained spreadsheet/HTML escaping and export audit checks. Confidential business text still needs human review before sharing.

### Product workflow

- Replaced first-level navigation and forced visual overrides with six workflow steps, native controls, readable theme, progress and actionable empty/error states.
- Built a one-click sample leading to a decision summary, without a provider key or external calls.
- Added privacy/project prerequisites, non-empty project creation and scoped project reopening that restores saved inputs and clears transient credentials.
- Made source ingestion additive, duplicates explicit and dataset upload ingestion idempotent across rerenders. Simplified coverage into counts and visible thin-category warnings with detailed checks under an expander.
- Added plain-language connection fields, optional advanced request/response mappings, preserved saved options and zero retries, and bound consent to the current inputs/target/call budget. Missing external session credentials now block preflight before network access.
- Preserved prompt editing and candidate proposals while removing unrequested fintech policy assumptions from generic drafts. A proposal is explicitly unproven until evaluated.
- Added a concise result summary with failures, severity, expected/observed behavior, source passages, next actions, gates and missing evidence; restored recorded reference-alignment reasons with human-review language.
- Preserved detailed failure inspection, calibration, charts, comparisons, exports and CLI. Added next-step decision events and a discoverable baseline/revision loop.

### Evaluation and execution integrity

- Corrected scoped policy/quantity/condition contradiction handling and citation provenance. Evaluator is `deterministic-v8`; native filename/document-hash aliases are accepted only without conflicting provenance. Uncertain paraphrases remain review cases.
- Aligned nine synthetic expected-reference fixtures with their actual existing source clauses; retained all 32 scenarios. Fixture repair is not a model-quality improvement.
- Preserved expected behaviors, versions, actual attempts, cache and model provenance through storage, history, charts and reports.
- Prevented execution errors and duplicate saves from inflating quality/sample counts. Serialized idempotent persistence in SQLite/PostgreSQL. Missing resources remain unknown, and critical privacy failures cannot be hidden behind insufficient-evidence status.
- Required complete, version-compatible held-out calibration and compatible case/configuration sets for comparisons; unqualified or mismatched evidence cannot imply readiness or improvement.
- Fixed pinned SDK transport compatibility, fixed official endpoints, explicit timeouts and retry ownership, refusal/empty-output semantics, reported-model identity, usage and model-specific sampling behavior.
- Fixed CLI error precedence and report/exit gate consistency. JSON/CSV/HTML schema 2.1 records the report-time gate configuration/hash; invalid gate config stops before database creation or execution. Historical scoring provenance is preserved.

### Operation and documentation

- Rebuilt supported Python, refreshed vulnerable dependencies/lock, added a non-destructive bootstrap and declared runtime version, updated CI checks and explicit disposable-PostgreSQL reset guard.
- Updated setup, security, architecture, evaluation and deployment documentation; added product brief, research/discovery plan, complete metrics and prioritized gap matrix.
- Preserved explicit non-production worker, queue, storage, scanner, OCR and scheduling boundaries.

## 5. Important bugs and verification

| Bug or trust defect | Fix and regression evidence |
|---|---|
| Anonymous visitors share default persistent state; context can leak between requests | Session repositories/ContextVar and identity reset tests; browser second visitor had empty history while first held a run |
| Forged role/disabled user and ignored minimum-role parameter | Stored membership checks and rank guard; `test_ui_role_boundaries.py`, SQLite and real PostgreSQL tests |
| Sample-to-real path bypasses acknowledgment | Post-target privacy guard; direct/API AppTests deny run controls until acknowledgment |
| Credentials inherited, saved raw or echoed by target | Public adapter blocks, explicit resolver, validated config and echo rejection; SDK/target/report canary tests |
| Unsafe destination/health/redirect/DNS/proxy behavior | Shared destination policy and pinned transport; `test_target_security.py` adversarial cases |
| Exports omit nested redaction | Whole-report redaction; `test_report_privacy_regressions.py` plus export callback/audit browser check |
| OpenAI/Anthropic SDK construction fails with HTTPX | Explicit compatible scoped transports; actual pinned SDKs with HTTPX MockTransport, no network |
| Retry/persistence duplicates and inaccurate provider/attempt counts | SQLite transaction/PostgreSQL lock and provenance tests; concurrent saves produce one authoritative result |
| Partial calibration grants unrelated/stale readiness | Required label/version/threshold/held-out coverage fixtures in calibration/integration tests |
| Errors fill sample minimum, missing costs become free, critical errors hidden | Aggregation/resource/critical credential regression tests; no quality score for failed calls |
| Changed cases/settings or synthetic runs ranked as improvements | Shared compatibility guards across comparison surfaces; synthetic/missing/incompatible cases are inconclusive |
| Native citations/conditions misclassified or uncertain text overclaimed | Citation uncertainty/scoped exemption/constraint suites; all 32 sample cases preserved |
| Project input restoration or target settings disappear/change | Scoped storage restoration and AppTests; zero retries/custom mappings preserved |
| Consent survives changed inputs and missing key permitted at preflight | Configuration fingerprint plus explicit secret preflight; UI tests check no network and disabled run |
| CLI missing key exits 2 instead of execution-error 3 | Real-error precedence with synthetic-only exception; subprocess verification: 32 errors, zero quality, exit 3 |
| CLI custom gate exit disagrees with report | Same validated gate object in exit/report, configuration/hash retained; tests across JSON/CSV/HTML, strict/permissive gates and early invalid-config rejection |
| Product journey identifier is scrubbed as an auth-session secret | Distinct journey schema key; strict event schema/correlation tests without weakening redaction |
| Dataset coverage hides warnings; reason lookup reads wrong schema path | Visible sparse-category warning, detailed expander and recorded reference-reason tests |

See the [security audit](security-review.md), [workflow audit](workflow-audit.md), [provider verification](provider-verification.md) and test files for focused findings. The pre-integration full run below supersedes focused counts from that phase; it does not cover the later combined release.

## 6. Historical verification — before integrating main

| Check | Result and practical limit |
|---|---|
| Supported runtime | Python 3.12.14; old 3.9 venv preserved. Python 3.11 dependency dry-run passes; its runtime suite was not executed locally. CI is configured for both, not yet run remotely. |
| Clean bootstrap | Copied only the bootstrap and three requirements files into an isolated ignored directory; created a fresh Python 3.12.14 environment and installed the locked dev dependencies successfully. `pip check` and Streamlit/provider imports pass; no `.env` created or existing environment modified. |
| Full suite including PostgreSQL | **573 passed, zero skipped, 4 upstream Google SDK/Pydantic deprecation warnings, 35.07 s** after the plain-language follow-up |
| Coverage | **85.71%** branch-enabled source coverage; repository 70% threshold retained. Streamlit UI has AppTest coverage but `app.py` is outside the source coverage denominator. |
| Ruff and formatting | Pass; **81 Python files** formatted/checkable |
| Mypy | Pass; **39 source files** |
| Dependencies | `pip check`: no broken requirements. `pip-audit --strict`: no known vulnerabilities at audit time. Initial audit had 130 advisory entries across six packages, including duplicate advisory IDs; these were not 130 distinct CVEs. |
| Git diff | `git diff --check` passed in the local-only phase; publication is now authorized and tracked separately |
| PostgreSQL | Disposable native PostgreSQL 16.2 through private Unix socket; five service tests, including formerly skipped migration/RLS/role tests; shutdown and cleanup successful. Actual managed deployment role/version remains unverified. |
| Fresh sample | AppTest one action; five documents, 30 chunks, 32 executions; **10 passes, 19 flagged answers, 3 execution errors**; synthetic launch verdict prohibited |
| Browser first visit/sample | Real in-app browser at 1280 × 720; public and private landing, one-click sample, synthetic disclaimer and inspectable result verified |
| Browser custom path | Acknowledgment → saved project → Markdown upload (1 document/6 chunks) → duplicate skip → retrieval query → 32-case JSONL import → prompt save → guided connection → synthetic evaluation → redacted JSON download → history |
| Browser connection | Explicitly authorized one POST to a clearly labeled local transport fixture succeeded; no scored run against that fixture. This is not a real customer assistant. Provider missing-key recovery observed. |
| Browser isolation/export | Separate public visitor had no historical runs; first visitor retained its own run. JSON export recorded both product/report audit events. Backend tests also cover forbidden cross-workspace reads, writes and exports. |
| Browser keyboard/layout | Arrow key changed Review view to Inspect failures with focus retained. Desktop has no document-level horizontal overflow. Declared theme contrast is 13.50:1 for body text/background and 4.88:1 for white/primary button color. Native control labels inspected. This is not a full state-by-state contrast or keyboard/assistive-technology audit. |
| Mobile | Viewport override requested 390 × 844 but tool continued reporting/rendering 1280 × 720. Override reset. Narrow/mobile layout is **unverified**, not marked passed. |
| Inputs and failure paths | Automated coverage includes empty/malformed/duplicate/unsupported/oversized inputs, bad JSON, missing keys, auth errors, 429, timeouts, provider failures, unsafe endpoints, partial runs, retries/resume, calibration limits and redacted exports. Browser did not repeat every adverse file/provider case. |
| Comparison/calibration | Automated compatible/incompatible baseline-candidate, critical gates and held-out calibration paths pass; browser single-baseline recovery inspected. Independent human accuracy and live-account calls remain unverified. |

Local evidence logs: `.local-verification/baseline-pytest.txt`, `baseline-golden-path.txt`, `final-golden-path.txt`, `final-full-verification.txt`, `final-dependency-audit.txt`, `python311-resolution.txt`, `cli-missing-key-recheck.json`, `review-desktop.png`, and `bootstrap-clean/verification.json`. These are ignored review artifacts, not customer telemetry or proposed commit content.

## 7. Remaining items

### Required acceptance evidence and release guardrails

The previous sample-only implementation blocker is resolved within the observed hosted engineering scope. No known failing critical security/integrity invariant remains in the exercised scope; this is not a blanket assurance. The **full owner definition of done remains unproven** because:

1. **Approved actual assistant and access:** a read-only staging endpoint or supported provider account, approved cases and scoped visitor credential are needed to verify actual authentication, answers, rate limits/failure recovery and a meaningful revision. None was supplied. The successful GitHub HTTPS GET and synthetic evaluations cannot substitute.
2. **Independent reviewers and first-time users:** qualified engineers/domain owners must adjudicate representative held-out labels and complete unassisted setup/result teach-back. Demand, evaluator validity, comprehension, recurrence and outcomes are not proved by the authoring agent.
3. **Manual import/export and accessibility:** live download controls were clicked; downloaded contents and native file-picker restore were not manually verified. Desktop control was denied and not bypassed. Automated restore/real-parser tests passed separately. Real mobile viewports, assistive technology and full keyboard interaction still require acceptance.
4. **Operating boundaries:** anonymous temporary sessions, host hibernation, finite local admission/resource controls and the older browser's scoped compiled-dependency exceptions remain explicit. Sustained operation and enterprise controls are separate work. Any new critical integrity/security failure stops rollout.

The actual primary-origin custom preparation, public HTTPS transport, synthetic baseline/revision comparison, missing-key guard and two-session reset were observed after deployment. Those receipts resolve the earlier initial-entry-only gap; they do not establish real assistant/account or independent customer acceptance. A local pilot cannot replace the owner’s required online experience.

### Design-partner follow-ups

- Run the discovery plan with 5–10 qualified teams; retain disconfirming evidence and reconsider ICP if recurring pain is weak.
- Observe at least two release opportunities per active pilot; measure confirmed findings, investigation effort, next-release reuse and willingness to continue.
- Calibrate false positives/negatives on real policy language, synonyms and languages; retain human review for uncertain claims.
- Complete mobile, keyboard and screen-reader assessment, especially editable tables, multi-select filters and dense evidence views.
- Review how much setup is needed for each assistant's retrieval/citation/cost trace; avoid claiming measurements unavailable from its API.
- Track upstream Google SDK deprecation cleanup separately from working behavior; update transport fixtures when changing SDKs.

### Enterprise-production requirements

Managed identity/provisioning/revocation and secure proxy ingress; deployed PostgreSQL role/RLS/TLS validation; durable workers/queues/artifacts/scheduling; parser isolation and malware scanning; optional OCR; host egress/rate limits; load/resource testing; centralized payload-safe monitoring/alerts; enforced retention; backups, restore and incident drills; deployment-specific independent assurance. The shipped local/unavailable adapters do not provide these services.

## 8. Exact local review commands

The primary customer journey is online at [AI Reliability Studio](https://ai-reliability-studio.streamlit.app/); visitors do not need these commands. For developer/operator review, use the current checkout and a supported environment. The earlier `ai-reliability-studio-release` directory was an integration worktree, not the current run location. This preview exercises the same temporary hosted-session mode on loopback port 8503:

```bash
cd /Users/aryan/Desktop/Workspace/Projects/ai-reliability-studio
bash scripts/bootstrap.sh --dev
APP_ACCESS_MODE=hosted-session APP_ENV=hosted-beta .venv/bin/python -m streamlit run app.py \
  --server.address 127.0.0.1 --server.port 8503
```

For a separate sample-only preview with isolated visitor sessions:

```bash
APP_ACCESS_MODE=public-demo .venv/bin/python -m streamlit run app.py \
  --server.address 127.0.0.1 --server.port 8502
```

Inspect changes and rerun ordinary checks:

```bash
git status --short
git diff --stat
git diff --check
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy src
.venv/bin/pytest
.venv/bin/python -m pip check
.venv/bin/python -m pip_audit --strict
```

The original checkout's ignored verification wrapper starts/stops its own disposable PostgreSQL database. It is a local verification artifact, not a tracked setup dependency:

```bash
.venv/bin/python .local-verification/run_hosted_postgres_verification.py -q
```

For portable PostgreSQL verification, follow [deployment instructions](../DEPLOYMENT.md#verification-and-ci), using only a disposable test database and explicit reset flag. A normal pytest without the service URL intentionally skips PostgreSQL tests.

## 9. Candid ratings — pre-integration owner-review assessment

Subjective owner-review assessments on a 10-point scale, not customer ratings or measured outcomes.

| Dimension | Rating | Rationale |
|---|---:|---|
| Product value | 7 | A specific recurring job with useful evidence mechanics; willingness to use/pay unvalidated |
| Positioning | 8 | Clear support-release focus and honest differentiation; needs customer-language testing |
| Onboarding | 8 | One-click sample and guided prerequisites; real integrations still require an engineer |
| Usability | 7 | Clearer primary path and actionable findings; detailed tables/advanced tools remain dense; mobile not verified |
| Evaluation integrity | 8 | Stronger provenance, calibration, failure and comparison invariants; deterministic semantics require real domain validation |
| Reliability | 7 | Extensive failure/retry/service fixtures and reproducible runtime; no sustained load/availability or live provider verification |
| Security and privacy | 8 | Locally tested sample isolation and trusted-local controls; not a hosted enterprise assurance rating |
| Design-partner readiness | 7 | Ready for a bounded local pilot and owner review; actual partner acceptance evidence is still missing |
| Portfolio strength | 7 | Substantive prioritization, implementation, evidence discipline and ownership artifacts; customer discovery/adoption/outcomes remain the missing proof |

Do not raise portfolio claims using synthetic runs, test counts or this agent's activity. Stronger evidence will be real discovery decisions, confirmed partner findings, repeated releases and observed outcomes.

## 10. Commit grouping for the authorized release

Review and stage logical hunks; several concerns share `app.py` and tests. Do not stage ignored databases, verification logs, environments or secrets.

1. **Reproducible supported runtime:** dependency pins/lock, bootstrap, `.python-version`, safe Streamlit config and CI checks.
2. **Isolation and security:** modes/context/repository roles, secret and network controls, redaction and adversarial tests.
3. **Evidence and execution integrity:** SDK transports, scoring/provenance, calibration, aggregation/comparison, idempotency, CLI/report consistency and fixtures.
4. **Guided release workflow:** six-step UI, project/input restoration, connection/preflight, decision summary and browser/AppTest regressions.
5. **Product measurement and handoff:** privacy-safe event schema, ICP/research/discovery, metrics, gap matrix and documentation.

This was the suggested grouping before publication. Implementation and main integration are now committed; the complete release passed checks and merged. The publication receipt below records exact source and delivery evidence. No history rewrite or artificial regrouping was performed.

## 11. Plain-language follow-up — pre-integration history

The owner requested an intuitive sample and custom workflow without exposed JSON, opaque versions or technical evidence fields. The implementation now:

- Presents release checks as named results and wrapping explanations; missing observations remain unknown. Candidate labels use current/candidate wording without asserting improvement.
- Replaces raw metadata in review, failure analysis, history, calibration, sources and comparison with selected readable fields. Detailed original answers and source text remain inspectable without rewriting evidence.
- Gives question editing six familiar fields. Stable IDs, alternative answers, rubrics and other hidden rules survive edit/add/delete/reorder and save/reopen operations. A blank draft no longer crashes coverage reporting.
- Uses choice controls for human-review labels instead of JSON. Technical IDs are maintained automatically.
- Uses a connection form, with an optional validated engineer-supplied settings import. Import remains a draft until saved; saving makes no call, and credentials are not persisted in configuration.
- Makes a human-readable HTML report the primary download, with exact machine evidence available through optional engineer exports. Report metadata is escaped and non-executable; redaction tests remain enforced.
- Fixes an additional comparison defect: grouped rows now receive the verdict for the correct candidate, and unknown model/cost data cannot silently disappear or become zero.

Historical verification after this follow-up, before integrating main: **573 tests passed with no skips**, **85.71%** source branch coverage, Ruff/format/mypy/diff checks passed, `pip check` passed, and the pinned dependency audit found no known vulnerabilities. This supersedes the earlier 490-test local result; the original baseline remains unchanged. Tests include hidden-field round trips, actual editor submission/persistence, plain-language screen checks, missing measurements, candidate/verdict alignment, connection import safeguards and HTML policy/redaction integrity.

The fresh in-app browser sample still produces 32 fictional executions, 19 flagged answers and 3 execution errors with no launch verdict. A narrow browser panel exposed clipped release-check explanations; replacing that grid with wrapping text fixes the observed reading problem. This is a narrow-panel spot check, not a verified mobile-device or complete accessibility audit. Independent first-time-user comprehension, real partner connectivity and adoption remain unvalidated. At that observation point, changes were local and uncommitted; the owner subsequently authorized the integrated release.

Follow-up artifacts: [presentation audit and acceptance checklist](plain-language-review.md), ignored `.local-verification/plain-language-full-verification.txt`, `.local-verification/plain-language-review.png` and `.local-verification/plain-language-sample-report.html`.


## 12. Integrated browser/native release

### Preserved and combined behavior

- **Primary workflow:** Start, Prepare, Connect, Evaluate, Review and History; one action runs all 32 fictional cases and opens readable findings. The three-answer saved example remains under the Start expander and saved-answer review is an advanced tool.
- **Saved answers:** upload approved sources/questions/answers, record an explicit attributed review, compare replacement answers and download/restore the complete workspace. Primary screens use file inputs and forms, without raw JSON text editing. Automatic findings never substitute for a review; changed answer/question/source versions invalidate incompatible reviews.
- **Source fidelity:** source text, DOCX table/paragraph order, available location information and extraction warnings remain inspectable. A partially extracted file is not silently treated as complete evidence.
- **Runtime boundaries:** native `public-demo` is anonymous/sample-only; actual WebAssembly `browser` mode permits approved tab-local custom review and explicit session-key provider calls; trusted `local` persists on the operator's computer; shared `authenticated` hosting needs verified infrastructure. A forged native browser mode and unknown modes fail closed.
- **Provider integration:** preserve provider-native system instructions, normalized role trace, actual response identity/usage, Gemini thinking-token accounting, bounded Retry-After handling, official destinations/no ambient routing and credential-echo rejection. Browser transport remains sequential/nonstreaming through restricted workers; native HTTP uses its separate destination safeguards.
- **Lifecycle:** reset closes only the current in-memory repository and clears reviews/keys; another visitor remains intact. Local resets retain authorized identity/audit history. Browser reload/inactivity loss is disclosed, and resume files are explicitly private original-content downloads.
- **UI compatibility:** readable presentation and evidence semantics must work under both the native Streamlit version and the browser's embedded Streamlit 1.41.0. The retained distribution is Stlite 0.76.0 / Pyodide 0.26.4; native Python verification is 3.12.14.

### Observed integrated verification

| Boundary | Observed result and limit |
|---|---|
| Combined native unit/integration/UI and PostgreSQL suite | **1,061 passed, zero skipped**, 33 warnings, 96.95 seconds; **87.86% branch-enabled source coverage**. The 70% gate remains unchanged. `app.py` is exercised through UI tests but is outside the source coverage denominator. |
| Native static/dependency checks | Ruff, formatting, mypy, `pip check` and `pip-audit --strict` passed on Python 3.12.14. The native audit reported no known vulnerabilities at that check; it does not cover the browser bundle. |
| Web wrapper | npm lint, TypeScript checking, build and audit passed; npm audit reported **zero findings**. |
| Reconstructed browser Python inventory | Compatible pure-Python patches are included. Audit of **69 packages** retains **44 advisory entries** across cryptography (11), lxml (2), Pillow (29) and scikit-learn (2). These are advisory records, not a count of distinct CVEs or proven reachable defects. See the [scoped dependency review](browser-dependency-review.md); this is not a clean browser audit. |
| Actual WebAssembly dependency tests | **11 passed in 4.30 seconds**, one pandas/PyArrow deprecation warning, using Node 24.14.0 with the assembled Pyodide 0.26.4 / Python 3.12.1 runtime. `sys.platform` was `emscripten`; this was not native Python with a simulated platform. |
| Protobuf implementation | Loaded **5.29.6, pure-Python backend** from site-packages; no provider protobuf namespace or loaded `google._upb`. Protobuf Struct and Streamlit 1.41.0 ForwardMsg round trips passed. |
| Local browser UI | Browser boot and reload worked. The primary sample completed **32 fictional executions**, opened a readable decision view without exposed JSON, and retained its **three intended simulated infrastructure errors**. Those fixture errors are expected evidence, not failed application execution. The sample-only error copy now labels those failures as simulated and confirms no external calls; its focused regression passed after the full suite. Saved-answer review, review persistence, fictional replacements, project consent/creation, provider prerequisites, PDF/DOCX/PPTX upload/indexing, duplicate recovery and retrieval were also exercised in the actual local browser. |
| Publication and GitHub | Sites publication succeeded: public version 8 serves application release `2026.09.16.1`. GitHub initially rejected missing `workflow` scope; the owner authorized it. The full release then passed branch/PR checks and [merged into main](https://github.com/AryanS313/ai-reliability-studio/pull/12) at `026a3e7`. |
| Final hosted origin | Published source hash matches the reviewed build. The public root boots inside its iframe; all 32 sample cases render the synthetic-only verdict and simulated-error explanation, with no browser error logs. A second simultaneous live tab starts without the first tab’s project or results. Custom uploads/reviews were exercised in the same build locally; provider CORS/real-account acceptance still requires credentials. |
| Real assistant/account, independent domain labels, first-time-user comprehension and adoption | Remain unvalidated; no customer or real-provider outcomes are inferred from fixtures. |

The ignored `.local-verification/final-merged-*` logs record the combined native checks. The WebAssembly harness and exact inputs/results are under `.local-verification/wasm-reachability/`; it verified 50 runtime files byte-for-byte, recorded test/dependency hashes and made no network calls. Its test-module SHA-256 is `47ecdc96fe75f3f75c1b7d6e1d84f653d7e21f57a2c09416e45beb2fba959eee`. The [dependency review](browser-dependency-review.md#observed-webassembly-verification) records relevant application-module fingerprints. This evidence identifies the tested dependency paths and does **not** assert that a later final application source bundle has the same hash.

The presentation refinement passed its focused regression. Final hosted observations and source identifiers are recorded below. Successful builds and these scoped checks do not establish real-provider access, full mobile/accessibility acceptance, absence of all dependency vulnerabilities or enterprise production readiness.


## 13. Publication and GitHub completion receipt

- Primary public app, restored at the owner’s request: https://ai-reliability-studio.streamlit.app/ . Updated six-step native public mode, the 32-case synthetic result, an empty simultaneous second session and clean reset were observed there after merge, with no browser error logs. It is sample-only and may hibernate.
- Alternative browser app: https://ai-reliability-studio.a3103.chatgpt.site
- Application release: `2026.09.16.1`.
- Reviewed application commit: `b9d8131a7238c8d3abda03722f0f36294baf5ddf`; present in the original local checkout and integration checkout.
- Sites source commit: `42fbd99c1b3483b95ad1c182ef5de5ab39f2a30c`; pushed to the existing Site source repository.
- Sites version 8 published successfully to the existing public audience.
- Published application source manifest: `0ee0ca87c77811bcc52adc751ab8d70c03b24f6356993e6bdb04c05f912d460c`, fetched from the live origin and matched to the reviewed build.
- Live `/studio` returns HTTP 200 with COOP `same-origin`, COEP `require-corp`, CORP `same-origin`, a provider-restricted CSP and `nosniff`. The embedded public root boots to the guided start screen; its 32-case sample and a second independent tab were verified after publication. Ending the sample session returned to an empty start screen without the prior project/results. No browser runtime errors were recorded.
- GitHub release: [Ship guided support-assistant reviews with secure browser workspaces](https://github.com/AryanS313/ai-reliability-studio/pull/12) merged at `026a3e77399b22fedfe94744c872ddf7047a95e1` on 16 September IST. Both [branch](https://github.com/AryanS313/ai-reliability-studio/actions/runs/35035170967) and [PR](https://github.com/AryanS313/ai-reliability-studio/actions/runs/35035175653) check runs passed on `a603b79`. All five jobs also passed on the [merged main revision](https://github.com/AryanS313/ai-reliability-studio/actions/runs/35035791475). No workflow control was removed to bypass the earlier authorization denial or check failures.
- Remote Python 3.11 and 3.12 each passed **1,055 tests**, with **six PostgreSQL tests skipped in those jobs and passed in the dedicated service job**; both reported **85.66%** source coverage. Their audit/lint/format/type/bootstrap/dependency-builder/synthetic CLI checks passed. Container non-root identity, web health and saved-answer sample passed. These executions occurred on GitHub runners, not this Mac; local combined-service verification remains **1,061 passed / zero skipped / 87.86%**.
- Real provider credentials/account compatibility, domain calibration, independent first-time-user comprehension, adoption and customer outcomes remain unvalidated. The scoped browser dependency exceptions remain explicit in the security review.

### Historical candid ratings — 16 September assessment

These were agent engineering/product assessments, not owner acceptance or customer evidence. The owner’s 17 September correction invalidated their overall completion implication because the main site then lacked the required custom path. The later hosted correction and bounded live checks supersede that unavailable-path state; the current ratings in section 14 remain conditional on real-assistant and independent-user acceptance. Preserve the earlier ratings as history.

| Dimension | /10 | Practical limit |
|---|---:|---|
| Product value | 7 | Recurring release-review job; willingness to adopt/pay unvalidated |
| Positioning | 8 | Specific support-assistant audience; needs interview confirmation |
| Onboarding | 8 | Working one-action sample and explicit prerequisites; cold browser download is substantial |
| Usability | 7 | Plain-language primary path; advanced controls and document layouts still need independent usability testing |
| Evaluation integrity | 8 | Versioned evidence and conservative verdicts; real domain calibration remains necessary |
| Reliability | 7 | Broad automated and browser verification; sustained load and live-account behavior unverified |
| Security and privacy | 7 | Verified isolation and safeguards; scoped browser advisories remain, without blanket security certification |
| Design-partner readiness | 7 | Published and merged bounded beta with passing remote checks; partner acceptance not measured |
| Portfolio strength | 7 | Credible ownership artifacts; discovery, adoption, repeated use and customer outcomes still need real evidence |


### GitHub verification correction — Python 3.11 setup

The first remote run passed browser distribution, PostgreSQL and the public container startup/sample checks. Python 3.11 stopped before tests because its runner inherited setuptools 79.0.1, reported under PYSEC-2026-3447 (two duplicate advisory records, one affected package). Python 3.12 passed the audit. The native requirements and constraints now install setuptools 83.0.0 on Python 3.11 so manual installation, bootstrap and CI receive the same correction. The audit is unchanged; no finding is suppressed. The corrected remote checks passed and the release merged, as recorded above. The published Wasm runtime is unaffected by this native bootstrap dependency.

The Python 3.12 job subsequently passed its test suite but failed the standalone synthetic CLI smoke command: the workflow omitted `APP_ACCESS_MODE=local`, so the default public mode correctly rejected unbound persistent storage. The smoke step now explicitly selects local mode, as the documented CLI command does. Its required exit code 2 and synthetic no-launch report assertion are retained. This changes CI configuration, not public application privileges.

The corrected CLI smoke subsequently passed in both Python versions on both branch and PR checks. All other required jobs also passed before merge. The final documentation pass reconciled the eight supporting product/audit documents, retained historical baselines and validated local links and the 36 complete metric contracts. These changes affect release reporting; no new customer outcome or browser deployment is claimed.

### Public-address follow-up

The owner requested a branded domain without the hosting provider’s name, then selected the existing Streamlit address as the interim primary link while away. GitHub’s homepage and the README were updated accordingly. **The URL choice did not approve the sample-only restriction:** on 17 September the owner discovered and rejected it, requiring the full online custom journey. The existing host supports custom domains, but no hostname, DNS account or purchase has been selected; no new service or charge was created. The browser alternative stays available. The Cloudflare decision is paused. See [hosting and address plan](../HOSTING_OPTIONS.md) for prior hosting research; the hosted correction and bounded primary-origin workflow receipts are recorded below; real-assistant/independent-user acceptance remains open, and no migration is claimed.

## 14. Hosted correction — verification and delivery

Native release `2026.09.17.1` is included in PR 13 merge `bcdd6103ca713cb7f58d8736bfa563c308cebd7f`; final branch `528f918` includes the plain-language setup follow-up. The primary Streamlit origin displays that release/evaluator v8 and supports the bounded hosted custom journey verified below, without local installation. All branch/PR/main jobs passed. This supersedes current-state sample-only and initial-entry-only descriptions; real-assistant/account and independent-user/manual-picker acceptance remain unproven. Sites version 8/browser application `2026.09.16.1` is unchanged.

The private project download/resume format is JSON capped at 20 MiB, distinct from the hosted 2 MiB per-document upload limit. It carries stored source passages, locations and warnings; prompt/dataset/target versions; historical results/manifests; and coded decisions. It does not contain original uploaded binaries, grant trust to imported evidence or restore qualified calibration. Configured credential fields, secret/environment references, headers and URL credentials/query fragments are removed; new calls need fresh keys and consent. Arbitrary opaque secrets pasted into ordinary content cannot be universally detected, so this remains a private input-bearing file, not a public report.

Restore checks envelope/input hashes, supported shapes, case validity and current assistant configuration policy before changes. Repository transactions create a new project and roll back all its assets/audit writes on failure, preserving current work. A nonblocking process-wide admission guard allows only one decode/restore at a time and releases after errors. Restored live history is explicitly offline/unverified; synthetic history retains its synthetic-only verdict. Recorded source manifests and decisions remain attributed to the import rather than replayed as new observed activity.

| Local verification | Result and limit |
|---|---|
| Project portability plus storage/execution regressions | **136 passed in 10.02 seconds**, without running a competing coverage collector. Includes disk and ephemeral memory repositories, atomic rollback, authorization, malformed/oversized input, secret/reference removal, input checksums, source-identity changes after redaction, usage mappings and busy-restore recovery. |
| Independent project and hosted UI checks | **85 passed in 14.79 seconds**. The audit found and then verified fixes for malformed case records and request-mapping arrays that otherwise broke restored UI state. |
| Actual local UI resume journey | 32-case sample download → independent hosted session restore → Review → readable export completed without exceptions. All 32 rows, three simulated errors and the synthetic no-launch verdict remained. This is agent-run local evidence, not a real customer/assistant or final hosted acceptance. |
| Portability static checks | Ruff, formatting and mypy passed for `src/project_workspace.py`, its storage changes and focused tests as applicable. Whole-release results must be recorded separately. |

The usage-mapping regression also exposed a prior persistence bug: generic secret detection rejected legitimate `$.usage.input_tokens` and `$.usage.output_tokens` paths. SQLite/PostgreSQL persistence now exempts only values that satisfy the external response-path grammar, including disabled empty optional paths; all other credential checks remain. No new customer, commercial, paid-account or deployment outcome is inferred from these repairs.

### Complete local verification — 17 September

The combined hosted candidate passed **1,203 tests with zero skips** on Python **3.12.14**, including all **six disposable PostgreSQL 16.2 service checks**: **124.88 seconds**, **33 upstream SDK warnings**, **87.53% branch-enabled source coverage**. Ruff, formatting for **119 files**, mypy for **46 modules**, `pip check` and the native dependency audit passed. Final focused security verification passed **104 tests** with no blocking finding reported in that scope. Log: `.local-verification/hosted-full-suite-final.log`.

At this earlier local checkpoint, the actual browser acknowledged privacy, created the fictional **Hosted workflow verification** project, loaded five sample documents/30 passages, returned retrieval matches and loaded 32 cases. It had reached prompt/connection preparation; this did not claim a real provider call or a complete custom browser evaluation. The [hosted workflow review](hosted-workflow-review.md) now consolidates later CI/merge and bounded custom-origin receipts, while retaining real-assistant/independent-user/manual-picker acceptance gaps. The historical local results alone did not close that gate.

**Earlier local checkpoint, superseded by the merge receipt below:** code was committed at `555aa08` but not yet pushed at that time. A final uploader-cap correction added two regressions and passed 30 hosted/guided tests; the full suite was then rerunning against the frozen head in `.local-verification/hosted-release-final.log`. The 1,203-pass checkpoint remains distinct from its later result. A consented unauthenticated GET through the actual local Connect form to GitHub's public API also passed; it establishes HTTPS transport only, not AI quality or a real provider account.

Final uploader-cap rerun: **1,205 passed, zero skipped**, **87.53% coverage**, **125.90 seconds** on the same supported Python and disposable PostgreSQL setup. The main-site-only rule is now a standing requirement in `AGENTS.md`; `CHANGELOG.md` records the correction. See the hosted review for browser observations and the native file-picker testing limitation.


### Hosted merge and live-entry receipt — 17 September, 04:59 IST

- [Restore secure custom reviews on the main website](https://github.com/AryanS313/ai-reliability-studio/pull/13) merged at `bcdd6103ca713cb7f58d8736bfa563c308cebd7f`; final branch `528f918` includes the owner-feedback copy correction.
- All five jobs passed in both the [branch run](https://github.com/AryanS313/ai-reliability-studio/actions/runs/35161918478) and [PR run](https://github.com/AryanS313/ai-reliability-studio/actions/runs/35161921660). Each Python 3.11/3.12 job passed **1,199 tests**, with six PostgreSQL service tests skipped in those jobs and **all six passed** in the dedicated job; **85.58%** non-service coverage and 33 upstream SDK warnings. Linux container health/sample and hosted office-parser imports passed; browser build passed. All five jobs also passed in the [merged-main run](https://github.com/AryanS313/ai-reliability-studio/actions/runs/35162489389).
- Final local verification after the copy follow-up: **1,205 passed, zero skips, 87.53% coverage, 122.22 seconds**, including six disposable PostgreSQL checks. Log: `.local-verification/hosted-final-copy-suite.log`. The focused copy/UI run passed **48 tests**. Earlier durations/counts above retain their historical scope.
- Actual primary Settings shows **release `2026.09.17.1` / evaluator v8**. Fictional **Hosted release acceptance** project: privacy acknowledgment; five bundled documents parsed to 30 passages; empty-case validation with Apply disabled; 32 cases saved with coverage warnings; custom prompt saved. The friendly Connect form saved an unauthenticated GitHub public-repository HTTPS GET with explicit consent, then passed Connection check. This is transport-only, not an AI assistant or quality result.
- The custom baseline and edited-prompt revision each completed **32 unique executions / 29 scored / 3 excluded intentional simulated errors**. Review showed **19 flags**, inspectable source/evaluator reasons and no launch approval. History initially disabled same-run comparison and linked to evaluating a revision; after the second run, comparison was **inconclusive**, with **zero percentage-point change** and an explicit refusal to rank synthetic quality.
- A second simultaneous tab completed the independent sample (32 cases/19 flags/3 simulated errors/no-launch). Resetting it returned empty Start while the custom project retained its 30 passages, 32 cases and saved prompt. This bounded observation verifies that reset did not affect the other tab; it is not universal isolation or load assurance.
- Project and readable-report download buttons were clicked. Actual downloaded contents and manual file-picker restore remain unverified; AppTest second-session restore/review/export passed separately.
- The primary site's **A model with my documents** route showed an empty OpenAI password field/No API key; Evaluate displayed actionable missing-key guidance and kept Run evaluation disabled. No provider call or credential was used.
- The desktop Computer Use tool denied control of Codex, so native file-picker selection was not manually verified or bypassed. Automated upload/resume and real parser subprocess tests are separate evidence. Real assistant/provider account acceptance, independent comprehension/domain calibration, repeat use and commercial outcomes remain unvalidated.

### Current candid ratings — 17 September hosted engineering release

Subjective assessments on a 10-point scale, not customer ratings. These supersede earlier current-readiness interpretations while preserving the historical ratings above.

| Dimension | Rating | Evidence and remaining limit |
|---|---:|---|
| Product value | 7 | A concrete recurring release-review job with useful evidence mechanics; real customer benefit and willingness to use/pay remain unvalidated |
| Positioning | 8 | Narrow support-assistant release problem, explicit non-goals and evidence boundaries; customer-language testing remains absent |
| Onboarding | 6 | Main-site custom flow and sample work with clearer connection choices; owner confusion prompted fixes, and unassisted integration is unmeasured |
| Usability | 6 | Readable findings, missing-key recovery and revision path observed; independent comprehension, manual picker and full mobile/accessibility acceptance remain open |
| Evaluation integrity | 8 | Failures excluded, source reasons inspectable, synthetic/imported evidence constrained and comparison refuses unsupported improvement; real-domain calibration still missing |
| Reliability | 7 | Local 1,205-test suite, all remote jobs and bounded live journey pass; provider-account behavior, sustained host operation and load are unvalidated |
| Security and privacy | 7 | Isolated temporary sessions, explicit keys/consent and bounded parsing/restore; live reset isolation observed. No independent audit, OS parser sandbox or distributed-abuse assurance; older browser exceptions remain |
| Design-partner readiness | 6 | Bounded online engineering beta delivered; an approved real assistant, independent reviewer/user and remaining manual acceptance are needed to satisfy the full owner definition of done |
| Portfolio strength | 7 | Evidence-backed scope correction, ownership history, implementation and verification are substantial; no customer discovery, adoption, repeated use or commercial outcome can yet be claimed |
