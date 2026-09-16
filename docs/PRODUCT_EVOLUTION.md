# AI Reliability Studio: product evolution and PM handoff

**Last evidence update: 17 September 2026 (Asia/Kolkata).** This is the living product history, decision record and handoff. It complements the [technical changelog](../CHANGELOG.md), [release verification](design-partner/release-review.md), [product brief](design-partner/product-brief.md) and [success-metric dictionary](design-partner/success-metrics.md).

## Changes since the previous update

- **Hosted correction merged and all remote checks passed:** [PR 13](https://github.com/AryanS313/ai-reliability-studio/pull/13) merged at `bcdd6103ca713cb7f58d8736bfa563c308cebd7f` on 17 September at 04:59 IST; final branch `528f918`. All five jobs passed in the [branch run](https://github.com/AryanS313/ai-reliability-studio/actions/runs/35161918478), [PR run](https://github.com/AryanS313/ai-reliability-studio/actions/runs/35161921660) and [merged-main run](https://github.com/AryanS313/ai-reliability-studio/actions/runs/35162489389). The primary [Streamlit site](https://ai-reliability-studio.streamlit.app/) displays native release `2026.09.17.1` / evaluator v8.
- **Custom journey exercised on the main site:** privacy acknowledgment, a fictional custom project, five bundled documents/30 passages, case validation, 32 saved cases, a saved prompt and a consented HTTPS connection check all worked online. Two 32-case synthetic runs produced readable evidence and an explicitly inconclusive baseline/revision comparison. The GET to GitHub was transport-only; neither it nor synthetic runs establish real assistant quality.
- **Live boundaries and return path:** a separate sample tab reset to empty Start while the custom project retained its inputs. History disabled comparison with one run and enabled it after the revision. Private-project and readable-report download buttons were clicked; actual downloaded contents and native file-picker restore were not manually verified. Automated round-trip restore passed separately.
- **Verification retained with exact scope:** final local Python 3.12.14: **1,205 passed, zero skipped, 87.53% coverage, 122.22 seconds**, including six PostgreSQL checks; 48 focused UI checks passed. Remote Python 3.11/3.12 each: **1,199 passed**, six service skips covered by the separately passing six PostgreSQL tests, **85.58%** non-service coverage and 33 upstream SDK warnings. Browser build and Linux container checks passed. Older counts remain historical.
- **Maturity corrected without erasing the mistake:** the agent's unapproved sample-only scope reduction is superseded by a **bounded hosted design-partner beta as engineering delivery**. Full owner acceptance remains unproven pending an approved real-assistant/account trial, independent usability/domain validation and manual-picker/accessibility checks. No customer or commercial evidence is invented. The separate browser remains `2026.09.16.1`; Cloudflare/domain decisions remain paused/unselected.

For every later meaningful milestone, replace this short delta section, refresh the delivery snapshot, and append to the milestone ledger near the end. Preserve earlier evidence and corrections rather than rewriting the past to fit the latest positioning.

## 1. Executive summary and maturity

AI Reliability Studio began as a local-first evaluation dashboard with an explicit portfolio/recruiter demonstration path. It made a useful loop visible: provide documents, a prompt and expected answers; generate responses; inspect scores and failures; compare prompts; export results. Its synthetic comparison deliberately favored the proposed improved prompt. That made the demonstration understandable but could not establish real improvement.

The August rewrite made trustworthy release evidence a central engineering concern: versioned inputs, explicit execution failures, candidate-specific gates, source-aware checks, calibration, external targets and reproducible reports. September work repaired the human review journey, public session boundaries, provider behavior, source fidelity, workspace restoration and browser distribution. The current work narrows the intended customer to a small team releasing a support assistant grounded in written knowledge, and prioritizes understanding, a repeatable decision workflow and measurable adoption over additional platform breadth.

**Current classification: bounded hosted design-partner beta as engineering delivery; full owner definition of done remains unproven.** The primary site now supports online custom preparation, a consented HTTPS connection check, synthetic evaluation, readable evidence and revision comparison, with separate-session reset observed. This supersedes the unapproved sample-only restriction. A real assistant/account trial, independent first-use acceptance, complete manual import/export acceptance and representative domain calibration are still missing. The separate browser beta has different transport/custody limits. There is no established customer cohort, measured retention or commercial evidence, and no production/general-availability claim.

The next acceptance milestone is an approved real-assistant trial on the primary site, followed by an independent user explaining one finding or evidence gap and returning at the next real release. The completed internal synthetic comparison verifies the workflow and its limitations; it does not supply customer or real-answer-quality proof.

## 2. How to read the evidence

Each historical reason is identified as one of:

- **Documented intent:** a contemporaneous README, plan, acceptance record or commit states the purpose. This is evidence of intent, not proof of customer demand.
- **Verified implementation:** inspected source/diffs establish behavior or its correction. Tests inspected in old revisions are not described as historically executed tests.
- **Observed verification:** a dated test run, browser observation, repository API response or deployment response was actually recorded, with its scope.
- **PM inference:** a retrospective interpretation of the product problem or trade-off. It must not be presented as an interview finding or the author's undocumented motivation.
- **Hypothesis/proposal:** intended customer, target, benefit or future work that still requires evidence.

Dates below use India-local calendar dates unless another offset is specified. Git author and committer times can differ. Merge dates prove repository integration, not deployment. A version string is not a Git tag, a GitHub Release, a live deployment or a readiness certification.

### Evidence references

Historical files are reproducible with `git show <commit>:<path>`. These references deliberately identify the revision, not only today's mutable file.

| ID | Evidence | What it establishes |
|---|---|---|
| H01 | `38e97d9`: `README.md`, `app.py`, `src/llm_client.py`, `src/scoring.py`, `src/database.py`, `src/suggestions.py`, `data/eval_questions.csv`, tests | Earliest recorded scope, recruiter path, scoring, biased mock comparison, fallback and global SQLite behavior |
| H02 | `7540c3b:README.md`; `1b981a1`, `9e20658`, `386441a` diffs | Origin self-report and public presentation; later same-day styling, roadmap and development-container changes |
| H03 | `1fe6964` against its parent: loader, evaluator, client, config, app, requirements and tests; [merged compatibility PR](https://github.com/AryanS313/ai-reliability-studio/pull/1) | July format/provider expansion, not an evidence-integrity rewrite |
| H04 | `f826861`: `pyproject.toml`, implementation plan/report, aggregation, targets, scoring, storage, versioning, execution, auth, database; [August rewrite PR](https://github.com/AryanS313/ai-reliability-studio/pull/2) | Declared 1.0.0 and release-evidence foundations, including their remaining global facade |
| H05 | `d2fb73e:README.md`; [synthetic-disclaimer PR](https://github.com/AryanS313/ai-reliability-studio/pull/3) | Explicit sample limitation and the older feature-branch baseline used by the current audit |
| H06 | `1dce2ad`, `437c5b4`: public sessions, database, saved responses, scoring, client, security and regression tests; [public-workflow PR](https://github.com/AryanS313/ai-reliability-studio/pull/4) | September human review, public-session, provider and evaluator corrections |
| H07 | `ce7d7f3`, `e53d373`, `55d7361`; [browser edition PR](https://github.com/AryanS313/ai-reliability-studio/pull/5), [worker isolation PR](https://github.com/AryanS313/ai-reliability-studio/pull/6), [public entry-point PR](https://github.com/AryanS313/ai-reliability-studio/pull/7) | Browser distribution, transport limits, static-host startup correction and public route change |
| H08 | `2d3439f`, `571d8fa`; [cached configuration PR](https://github.com/AryanS313/ai-reliability-studio/pull/8), [provider/settings PR](https://github.com/AryanS313/ai-reliability-studio/pull/9) | Rerun/reload failures, zero-threshold preservation and evaluator v7 |
| H09 | `e018414`, `42eba19`; [source/execution PR](https://github.com/AryanS313/ai-reliability-studio/pull/10), [restore-controls PR](https://github.com/AryanS313/ai-reliability-studio/pull/11); [source-review acceptance](SOURCE_REVIEW_ACCEPTANCE.md) | Source fidelity, execution accounting and restoration corrections; the September 8 merged state |
| H10 | `079459e`, `b9d8131`, `3ca82d4`, `b51aaa7`; [gap matrix](design-partner/gap-matrix.md), [workflow audit](design-partner/workflow-audit.md), [plain-language review](design-partner/plain-language-review.md), [release review](design-partner/release-review.md) | Current implementation, integration, verification and publication receipt; merged through [the design-partner release](https://github.com/AryanS313/ai-reliability-studio/pull/12) at `026a3e7` |
| H11 | [Product brief](design-partner/product-brief.md), [discovery plan](design-partner/discovery-plan.md), [metrics](design-partner/success-metrics.md) | Research-informed ICP and validation hypotheses; not completed customer research |
| H12 | [Browser dependency review](design-partner/browser-dependency-review.md), native verification logs and actual Wasm harness results referenced there | Scoped engineering/security verification and unresolved dependency limits |
| H13 | Final branch `528f918`, [hosted correction PR 13](https://github.com/AryanS313/ai-reliability-studio/pull/13), merge `bcdd610`, [hosted workflow review](design-partner/hosted-workflow-review.md) | Owner-rejected scope reduction, restored online custom entry, local/remote verification and precisely bounded live acceptance observations |

GitHub PR titles, merge commits and dates were checked through its read-only API. No Git tags or GitHub Release entries were returned at this snapshot. The earliest commit already contains a substantial app; Git cannot recover uncommitted work or prove the idea's original conception date.

## 3. Product origin

### Why it was created

The earliest README describes teams struggling to test correctness, grounding, hallucination risk, escalation, latency and cost before launch. It asks whether an existing assistant is accurate, grounded, safe and reliable enough to ship. The next README revision says the author had encountered reliability questions while working on AI-assisted internal tools. That is **documented author self-report**, not independently verified customer discovery. Both versions explicitly position the app as a portfolio demonstration, including a recruiter walkthrough. [H01–H02]

### Original users, goals and success criteria

There were two audiences: teams building assistants in the problem statement, and recruiters/portfolio reviewers in the demonstration instructions. No narrowly qualified ICP, buyer, procurement model or willingness-to-pay evidence was documented. The immediate deliverable was a comprehensible end-to-end QA workflow that could be tried without credentials.

Original functional goals were to load a demonstration or custom inputs, execute cases, display reliability metrics and a readiness label, compare a proposed prompt, inspect failures and export results. The original readiness rule used average overall score ≥80%, citation score ≥80%, escalation ≥75% and high-risk share ≤10% for “Ready for Controlled Beta.” These were **implemented score thresholds**, not measured evaluator accuracy, customer acceptance or an independently justified release standard. No acquisition, retention or commercial success baseline was established. [H01, `launch_readiness_verdict`]

### Initial scope and deliverables

- Streamlit app with ten navigation destinations, local SQLite and CSV export.
- FinSure fictional policy demo: five documents and 56 expected-answer cases.
- Current system prompt, selectable model, rule-generated improved prompt and comparisons.
- TF-IDF retrieval, keyword-overlap expected-answer scoring, source/citation matching, groundedness and hallucination-risk heuristics, escalation checks, latency/cost tracking and failure suggestions.
- Optional OpenAI execution plus deterministic mock behavior when no usable live call was available.
- Eight test-function definitions in two test files. This is a source inventory, not a claim about a historical passing run.

**Upload nuance:** the first UI accepted TXT/Markdown; the underlying loader already had PDF/DOCX support. It would be inaccurate to describe every loader capability as a usable first-version upload workflow. [H01]

### Useful shortcuts and why they were insufficient

The credential-free example made the evaluation loop easy to demonstrate. Local SQLite and TF-IDF kept setup lightweight, and recognizable policy exceptions made failures concrete. Those are reasonable prototype benefits (**PM inference** from the workflow).

The mock recognized instructions emitted by the prompt improver, and the README explicitly said it was designed to make the improved prompt perform better. Provider exceptions also returned mock answers into the scoring path. Aggregate readiness labels had no synthetic exclusion. Overlap and source names could not establish semantic correctness or complete citation support. Global storage/deletion behavior had no tenant authorization; switching to custom mode could clear the database. These were real implementation limitations, not proof that a live visitor's information was exposed. [H01]

The demonstration could illustrate what an evaluation workflow might look like. It could not justify a production release, independent prompt improvement, general hallucination detection, secure shared hosting or customer value.

## 4. Chronological product and version timeline

Stage names below are **analytical product stages**, not invented official versions. The only declared package version found is 1.0.0, introduced in August. Date-based application release markers and evaluator versions are recorded separately.

### 31 May 2026 — portfolio-oriented local MVP

- **Refs/type:** root `38e97d9`; README `7540c3b`; analytical “portfolio MVP,” with no declared package version in the inspected files.
- **Before → change:** first recorded implementation of the document → answer → score → comparison → export loop; README adds the origin explanation and public-demo presentation.
- **Why/problem:** documented need to make assistant reliability inspectable before launch and demonstrate AI product work. A no-key sample lowered demonstration friction; that adoption interpretation is PM inference.
- **Result:** the capabilities and shortcuts in section 3. Same-day `1b981a1` fixes filter-chip styling; `9e20658` changes roadmap wording; `386441a` adds development-container setup. These do not establish a new product release.
- **Limit:** programmed prompt improvement, weak evidence semantics, no isolated shared service, no customer validation. A README live URL is not proof of historical deployment health or usage. [H01–H02]

### 10–11 July 2026 — broader compatibility

- **Refs/type:** `1fe6964`, merged as `e4f5b32`; analytical compatibility stage. Author time is 10 July Pacific; commit and merge are 11 July IST.
- **Before → change:** narrow visible uploads and OpenAI-only integration expand to common office, text and structured formats, richer document extraction, more dataset formats, Gemini and Anthropic alongside OpenAI, provider selection and session-key controls.
- **Why/problem:** documented compatibility work; PM inference is that teams should be able to use their existing policies and chosen provider rather than convert every input or switch models. No customer-request evidence was located.
- **Result:** per-file extraction error feedback, DOCX tables, workbook sheets and PPTX text/tables; CSV/TSV/XLS/XLSX/JSON/JSONL dataset loading. Nine new test definitions bring the source total to 17.
- **Limit:** legacy `.doc` and OCR remain unsupported; provider failures still fall back to mock, and shared-state/readiness semantics remain. Breadth grew before a specific buyer or repeat-use need was validated. [H03]

### 20 August 2026 — declared 1.0.0 release-evidence rewrite

- **Refs/type:** `f826861`, merged as `66091fc`; **declared package/changelog version 1.0.0**, evaluator `deterministic-v3`, label semantics `failure-labels-v1`, report schema `2.0`. No corresponding Git tag or GitHub Release was verified.
- **Before → change:** global scoring dashboard becomes a platform with workspace/RBAC repositories, additive migrations, immutable prompt/document/dataset/target versions, hashed manifests, external HTTP targets, execution states/retries/checkpoints, candidate gates, comparisons, calibration, reports and CLI/CI.
- **Why/problem:** the contemporaneous implementation plan explicitly prioritizes trust/isolation, real targets/reproducibility and operational foundations. Token overlap, provider fallback, synthetic verdicts, global deletes and pooled averages are named problems. These motives are documented, not inferred customer feedback.
- **Result:** provider/configuration failures remain explicit unscored execution failures; mocks become generic and prompt-independent; synthetic results are ineligible for launch verdicts; deterministic constraint/citation/claim checks and critical-failure precedence strengthen interpretation. Review and operational interfaces are introduced.
- **Limit:** scoped repositories do not by themselves isolate anonymous visitors: the database facade still caches global repository/active context. Local queue/artifact/scheduler/OCR/scanner implementations do not constitute managed infrastructure. Broad platform foundations precede customer pull; that sequencing concern is PM inference. [H04]

### 20 August 2026 — explicit demonstration disclaimer

- **Refs/type:** `d2fb73e`, merged as `6d071f5`; documentation refinement, not another formal version.
- **Before → change:** the README makes the live sample and synthetic-results limitation explicit.
- **Why/result:** aligns demonstration claims with the already implemented synthetic no-launch rule. It does not make synthetic results real evidence.
- **Current-task relevance:** the requested local `feature` branch remained here. Auditing it later exposed 13 navigation destinations and other gaps. That older checkout was not an accurate description of September's already-deployed browser product. [H05, H10]

### 7 September 2026 — public source review and evidence repair

- **Refs/type:** `1dce2ad`, then `437c5b4`, merged as `279b6cc`; analytical public-readiness stage. Evaluator becomes `deterministic-v6`, labels `failure-labels-v3`; `437c5b4` introduces application marker `2026.09.07.1`. Package stays 1.0.0.
- **Before → change:** explicit saved-answer import/review/export/resume, human versus AI-assisted attribution, source-bound review hashes, replacement comparisons and offline no-launch limits complement direct execution. Constraint, citation, uncertainty and missing-measurement rules are repaired.
- **Why/problem:** documented workflow repairs and regression cases address unanswered “what should I review next?” steps, conclusions attached to changed evidence, misleading certainty, public identity state and provider errors.
- **Result:** each public visitor receives a temporary **server-side** SQLite workspace with random identity, per-rerun initialization, expiry/reset and ContextVar binding. Owner/environment provider credentials are suppressed in public paths. Numeric token budgets stop being mistaken for secrets; live target persistence and Sonnet sampling/thinking-response handling are corrected.
- **Limit:** this historical public mode could still use explicitly supplied provider keys and allowlisted external targets; it differed from the sample-only native mode introduced on 16 September, before the owner's correction. Fixture/SDK tests do not prove paid API access, reviewer correctness or independent onboarding. [H06]

### 7 September 2026 — private browser distribution

- **Refs/type:** `ce7d7f3` → merge `ce25c5d`, application `2026.09.07.2`; subsequent `e53d373` → `eb92e19`, and `55d7361` → `edb80dc`. Analytical delivery stage; package remains 1.0.0.
- **Before → change:** public review no longer depends solely on a hosted Streamlit server. Stlite/Pyodide runs Python in the visitor's tab, with vendored/runtime provenance, bounded sequential execution and a dedicated Fetch worker restricted to supported provider routes/models/headers.
- **Why/problem:** documented browser-distribution and hosting work; easier public availability and tab-local custody are intended benefits. The static host omitted worker isolation headers, causing startup to require a subsequent Blob-worker/isolation correction. This was a real deployment-specific repair, not evidence that building locally proves hosting works.
- **Result:** browser becomes the public entry point; reset and tab lifecycle controls accompany the new runtime. Arbitrary assistant endpoints are excluded from browser transport; saved answers remain a way to review an external assistant.
- **Limit:** substantial first download, old compiled runtime dependencies, browser-origin/CORS constraints, sequential calls and temporary tab memory. Closing/reloading loses unexported work. This is not a managed persistent multi-user database or durable worker service. [H07]

### 7 September 2026 — rerun and configuration recovery

| Ref / integration | Before → correction and user problem | Result / remaining limit |
|---|---|---|
| `2d3439f` → `7e51b72` | Cached modules after a configuration update could break Streamlit startup; runtime checks are repaired | More reliable reload; not a general availability guarantee |
| `571d8fa` → `f113ce1` | Provider settings reruns and menu behavior could interrupt setup; falsey zero thresholds could become defaults | Input intent is preserved; evaluator becomes **`deterministic-v7` here**, before the next day's source work |

These are documented bug corrections, not separate market-validation milestones. [H08]

### 8 September 2026 — source fidelity, real execution semantics and restoration

- **Refs/type:** `e018414` → `920b1c0`, application `2026.09.08.1`; `42eba19` → `3fc3e59`, application `2026.09.08.2`. Evaluator stays v7, package 1.0.0 and report schema 2.0.
- **Before → change:** source text/order/IDs/spans and warnings could be altered or lost; system instructions, attempts, retries, cache behavior and billing evidence could be misrepresented; uploading a workspace could close its own restore controls.
- **Why/problem:** documented acceptance failures include moved DOCX tables, altered `001`/`NA` values, encoding guesses, mismatched case IDs, approximate quote offsets and discarded extraction notices. These can change what a human thinks was reviewed. Execution records must reflect what was sent and observed, not desired configuration.
- **Result:** original-text spans, structured source fidelity and warnings survive review; provider-native system instructions and external prompt-delivery rules are preserved; bounded Retry-After and actual attempts/cache evidence persist; incomplete Gemini billing remains unknown. Restore controls survive reruns and retain prior work until a valid replacement is accepted.
- **Limit:** complex layouts, OCR, complete extraction and actual customer-provider compatibility remain unproven. Restored review hashes preserve identity, not truth. This stage ended at merge `3fc3e59`; the current remote state is tracked in section 7. [H09]

### 16 September 2026 — focused design-partner workflow

- **Refs/type:** local `079459e`; analytical design-partner milestone. Package remains 1.0.0; evaluator becomes **`deterministic-v8`**, labels remain v3, report schema becomes **2.1**.
- **Before → change:** the requested August feature baseline has a broad technical surface, hidden prerequisites and JSON/configuration burden. Work narrows positioning to support/knowledge release reviews, reduces primary navigation from 13 to six steps, and makes the 32-case demonstration a one-action route to an understandable result.
- **Why/problem:** repository/browser audits and the owner's explicit request for an intuitive, plain-language experience are direct evidence. The sharper ICP, sponsor and repeat-use hypotheses are research-informed PM decisions; they are not validated interviews. JSON boxes and opaque versions obstructed interpretation, so exact evidence is retained behind readable labels and optional exports instead of deleted.
- **Result:** enforced privacy/project/role prerequisites, simpler connection forms, explicit external-call consent, safe credential/transport rules, decision capture, compatible baseline/revision comparison, conservative uncertainty/calibration gates, readable reports, and allowlisted local product events. Native public demo becomes sample-only; trusted local and authenticated modes have distinct boundaries.
- **Limit:** 573 passing tests/85.71% coverage described this **pre-integration local candidate**, not the final browser release. A fast agent-run sample and six navigation steps do not prove unassisted comprehension or reduced human task time. [H10–H11]

### 16 September 2026 — reconcile main, verify and publish the beta

- **Refs/type:** application integration `b9d8131`, documentation receipts `3ca82d4` and `b51aaa7`; application **`2026.09.16.1`**, Sites **version 8**. This is an actual publication; the subsequent GitHub integration is recorded below, not a new declared package major version.
- **Before → change:** the local feature baseline lagged September main and the existing Site. Integration preserves saved-answer review/restoration/source fidelity/browser transport while adding the current guided workflow. Merely shipping the older branch would have lost working capabilities.
- **Why/problem:** verified branch divergence, Streamlit-version differences, actual browser concurrency requirements, older runtime advisories and the owner's authorization to ship. The 32-case sample needed explicit sequential execution in Wasm; its three intentional transport-error scenarios also needed wording that did not tell demo users to repair a real connection.
- **Result:** native Python 3.12, PostgreSQL, UI, dependency and actual Wasm checks pass within their stated scope. Compatible PDF/message/template/parser-selector dependencies are patched; unnecessary TF-IDF retained tokens are removed. Existing public Site is updated, and its source manifest, startup, synthetic sample, separate tabs and session clearing are verified.
- **Limit:** four compiled browser packages retain scoped advisory exceptions; neither native nor npm audit certifies that bundle. GitHub initially rejected the push for missing OAuth workflow scope. At that milestone no new merge/remote CI had occurred; authorization and completed integration are recorded in the following stage. Real-account/provider acceptance and customer outcomes remain unverified. [H10, H12]

### 16 September 2026 — complete GitHub handoff and reproducibility corrections

- **Refs/type:** branch push `35fb348`; Python 3.11 dependency fix `5765f9c`; CLI CI fix `a603b79`; [release merge](https://github.com/AryanS313/ai-reliability-studio/pull/12) `026a3e77399b22fedfe94744c872ddf7047a95e1`. Delivery/reproducibility milestone; application/evaluator identities remain unchanged.
- **Before → change:** the live app was published while GitHub main was older. Missing OAuth scope first blocked the push. After authorization, remote checks exposed vulnerable inherited setuptools on Python 3.11 and a CLI smoke command using the safe public default without a visitor session.
- **Why/problem:** actual permission and CI failures, not inferred customer requests. Repeatable supported setup and retained safeguards are release requirements.
- **Result:** complete code/history pushed; patched conditional native dependency; explicit local mode only for the CLI smoke step. Both branch and PR checks passed for Python 3.11/3.12, browser build, PostgreSQL and the non-root container. The release merged into main. Supporting documentation is reconciled in the handoff revision.
- **Limit:** no security assertion was bypassed; no new browser behavior or deployment is claimed. Customer integration, comprehension, evaluator validity, adoption and commercial outcomes remain unmeasured.

### 17 September 2026 — owner rejects the unapproved hosted scope reduction

- **Evidence/type:** direct owner feedback after discovering the main site's sample-only restriction; a product-acceptance correction, not customer research or a new software release.
- **Before → correction:** the previous handoff treated an isolated public sample plus local/private custom workflows as a completed design-partner boundary. The owner requires the complete custom journey online on the main site for nontechnical visitors and rejects local installation as the escape hatch.
- **Why/problem:** the agent chose the public restriction to reduce safety risk, without obtaining approval for that product-scope reduction. Visitors could try fictional cases but could not finish the core job with their own assistant on the primary site. The owner's choice of public URL was incorrectly allowed to stand in for acceptance of its capability limit.
- **Result at this snapshot:** the requirement, maturity classification and blocker list are corrected. Hosted implementation is in progress, not deployed or accepted. The Cloudflare decision is paused; no new hosting choice, purchase or migration is established.
- **Preserved evidence/limit:** September 16 code, CI, deployment and bounded verification remain historical facts. They do not prove the newly explicit acceptance path. Customer and commercial evidence remains absent.

### 17 September 2026 — local hosted workflow and portable project implementation

- **Refs/type:** working branch `codex/hosted-custom-workflow`; local implementation milestone, not a published release. Application candidate marker `2026.09.17.1` must not be confused with the last verified deployed `2026.09.16.1` snapshot.
- **Before → change:** the correction provides a hosted custom-session path under verification and adds private project download/restore so temporary sessions can support another review. All stored document passages/locations/warnings, prompt/dataset/target versions, run evidence and coded release decisions can be carried in a bounded JSON envelope. Original uploaded binaries were not stored and are not reconstructed or promised.
- **Why/problem:** mandatory local installation fails the owner's required online experience; losing temporary work also breaks the next-release loop. Restoring a user-controlled file must not confer trust on its scores, credentials, claimed execution or calibration.
- **Verified scope:** the focused project/storage suite passed 136 tests in 10.02 seconds; independent project/UI verification passed 85 tests in 14.79 seconds. The local 32-case sample was downloaded, restored into a second hosted session, reviewed and exported without exceptions; its three simulated errors and synthetic no-launch verdict remained. Ruff, formatting and mypy passed for the portability changes. Whole-release and final-origin results are maintained separately in the release review.
- **Corrections during verification:** reject malformed cases and connection settings before mutation; roll back all created assets/audit rows on storage failure; reject foreign-workspace access; preserve valid token-usage JSON paths without allowing credential values; bound and serialize restore decoding. Imported real history is offline/unverified, and imported synthetic history remains synthetic. Credentials must be entered again.
- **Remaining limits:** this is not a deployed main-site fix, proof of a real account integration, a backup service or customer validation. Checksums detect corruption, not authorship; private downloads include user inputs and must be handled accordingly. Pattern redaction cannot recognize every opaque secret a user might put in arbitrary content. Final hosted verification and external acceptance remain open.

### 17 September 2026 — merge hosted correction and observe the updated primary site

- **Refs/type:** final branch `528f918`, [PR 13](https://github.com/AryanS313/ai-reliability-studio/pull/13), merge `bcdd6103ca713cb7f58d8736bfa563c308cebd7f` at 04:59 IST; native application `2026.09.17.1`. This is a verified GitHub integration and bounded live-entry observation; Sites remains version 8/application `2026.09.16.1` without a new publication.
- **Before → change:** the sample-only primary entry is replaced by hosted-session Start project and Resume. A later owner report of confusing assistant/model and connection terminology leads to plain-language choices and explanations before the final branch checks.
- **Evidence:** final local 1,205-test run, zero skips, 87.53% coverage in 122.22 seconds; 48 focused UI checks; all five branch and PR jobs passed. Remote Python 3.11/3.12 each passed 1,199 tests plus six separately passing PostgreSQL service tests. Container health/sample and hosted office imports, and browser build passed.
- **Live observation:** the primary Streamlit origin renders the corrected hosted entry without a local-install requirement; one tab reached the custom privacy gate while another independent tab stayed empty. This supersedes the earlier current-state statement that the main site is still sample-only.
- **Still open at this milestone:** merged-main CI is running; full final-origin custom workflow and real account/assistant acceptance remain in progress/unvalidated. A desktop-control denial prevented manual native file-picker verification; it was not bypassed. No new customer or commercial evidence follows from these engineering results.

### 17 September 2026 — complete bounded hosted-origin verification

- **Refs/type:** native `2026.09.17.1` / evaluator v8 observed in live Settings; all five merged-main jobs passed in [run 35162489389](https://github.com/AryanS313/ai-reliability-studio/actions/runs/35162489389). This is engineering delivery evidence, not independent product acceptance.
- **Before → change:** initial live entry verification extends to custom preparation, connection transport, two synthetic evaluations, report controls, history and revision comparison on the actual primary origin. The earlier sample-only blocker is superseded.
- **Observed custom path:** fictional **Hosted release acceptance** project; privacy acknowledgment; five bundled documents parsed into 30 passages; blank case rows rejected with Apply disabled; 32 cases saved with coverage warnings; custom prompt saved. A consented unauthenticated GET to GitHub's public repository API passed through the friendly connection form. This checks HTTPS transport, not AI quality.
- **Evaluation and return:** the baseline and edited-prompt revision each show 32 unique executions, 29 scored and three excluded intentional simulated errors. The review shows 19 flags and no launch approval; comparison is explicitly inconclusive with zero percentage-point change and no invented improvement. One-run History explained how to evaluate a revision and disabled same-run comparison; two runs enabled comparison. Project/report download controls were clicked.
- **Missing-key recovery:** the direct-model route showed an empty OpenAI password input/No API key; Evaluate provided actionable guidance and disabled execution. No provider call or credential was used.
- **Session boundary:** an independent tab ran the sample and reset to empty Start while the custom tab retained 30 passages, 32 cases and its saved prompt. This is a bounded two-session observation, not a general penetration or availability assurance.
- **Still unproven:** real assistant/account authentication and quality, independently judged domain validity, unassisted comprehension, native-picker restore/downloaded-file inspection, full mobile/accessibility, actual next-release retention and payment. A desktop-control denial was respected; automated parser/restore tests remain separate evidence. Classification is a bounded hosted beta for engineering delivery, not completion of every owner acceptance condition.

## 5. Product-management evolution

This table interprets the product, rather than renaming feature lists as strategy. Current recruitment/buyer/benefit statements are hypotheses unless marked otherwise.

| Dimension | May–July demonstration | August evidence platform | September/current direction |
|---|---|---|---|
| Vision | Show that assistant answers can be tested before launch | Make release evidence reproducible and less misleading | Help an engineer and domain owner decide what to fix before the next support-assistant release |
| Problem definition | Answer quality, grounding, escalation and trade-offs are hard to inspect | Scores can conceal synthetic data, failures, incompatible candidates or mutable inputs | Teams need an understandable, repeatable review that reaches an actionable decision |
| Market / ICP | Broad assistant-building teams plus explicit portfolio audience | Broad AI evaluation/platform audience; enterprise foundations | Small SaaS/product team with a policy-grounded read-only support assistant, approved data, staging access and a release due soon |
| Roles | Demonstrator or technical operator | Builder, reviewer and administrator in a scoped workspace | Engineer can supply integration details; PM/support/domain owner must be able to complete the guided hosted review without installing software |
| Buyer / sponsor | Not established | Not established by architecture | Founder, engineering lead or product lead; budget and procurement assumptions unvalidated |
| Job to be done | Run cases and inspect a dashboard | Preserve trustworthy evidence about a candidate | Find consequential regressions, understand sources/limits, choose a next change and compare the revision |
| Activation | Load demo and reach results; no measured user criterion | Complete an evidence-bearing run | Demo teaches the loop; **real activation** requires a non-synthetic review plus an understood actionable finding/evidence gap |
| Core workflow | Upload → prompt/model → score → compare → CSV | Version inputs → execute target → gates/calibration → report | Required on the main site: Start → Prepare → Connect → Evaluate → Review → History. Hosted preparation, public HTTPS transport and synthetic revision review are observed; real-assistant and independent-user acceptance remain open. A local install or alternate import route does not satisfy the requirement |
| Return trigger | Improved-prompt comparison exists; return behavior unmeasured | Saved baselines and regression comparisons become possible | Next prompt/model/retrieval/policy revision or confirmed incident; preserve cases and review the same risks again |
| Value proposition | Visible QA beyond a chatbot demo | Reproducible, candidate-specific release evidence | Less work translating a support-assistant failure into a reviewed decision; time saved remains unmeasured |
| Differentiation | All-in-one demonstrable workflow | Evidence mechanics and conservative gates | Focused policy/source review and plain-language handoff; versioning/HTTP evaluation are not unique inventions |
| Metrics | Answer/retrieval/citation/grounding/escalation, latency/cost and aggregate readiness | Candidate gates, execution counts, provenance, confidence and calibration | Preserve evidence metrics; add the nine-category adoption/operating scorecard and anti-gaming rules |
| Non-goals | Enterprise/team integrations largely roadmap items | Production services explicitly left behind adapter boundaries | No safety certification, universal agent evaluation, automatic deployment or managed observability claim |
| Main risk | A convincing demo being mistaken for real quality | Platform breadth and engineering assurance mistaken for customer pull | Treating a safe but reduced public sample as completion of the requested hosted product; then integration, usability, evaluator validity and repeat-use uncertainty |
| Priority | Demonstrability and compatibility | Integrity, isolation, reproducibility, execution | Security/integrity → critical workflow → activation/interpretation → repeated use → accessibility/polish; features only for a supported need |

Current team size of roughly 2–10 builders and a next-change window of 30 days are qualification filters to test, not measured market facts. FinSure is an example of referenceable policy exceptions, not evidence that regulated financial decision approval is the right market. QA, agencies and risk/compliance reviewers remain secondary; they are not simultaneous primary ICPs. [H11]

## 6. Before-and-after transformations

| Earlier state | Corrected/current direction | Why it matters and remaining boundary |
|---|---|---|
| Portfolio demonstration | Bounded hosted review workflow delivered; real assistant and customer acceptance unproven | The sample and agent-run custom workflow cannot establish a real team’s repeated release decision; that remains the intended, unmeasured outcome |
| Generic AI reliability platform | Support-assistant release review | Referenceable policies and recurring revisions make the first job more specific; ICP remains a hypothesis |
| Token-overlap/source-name scores | Constraint-, provenance- and evidence-aware checks with uncertainty | Avoid treating fluent overlap as correctness; finite deterministic grammar still misses or misclassifies unfamiliar language |
| Prompt-aware mock designed to improve | Prompt-independent authored scenarios | Removes circular improvement evidence; synthetic comparisons still establish no real prompt winner |
| Provider errors produce mock answers | Explicit execution failure and separate denominators | Failed infrastructure cannot inflate quality; actual provider behavior remains account-dependent |
| Synthetic aggregate readiness label | Synthetic demonstration with no launch verdict | Workflow completion cannot be sold as real assistant safety |
| Global storage and destructive reset | Scoped repositories, bound request context and ephemeral public sessions | Prevent shared identity/state from silently crossing visitors; private production identity/operations still require deployment validation |
| Mutable/weakly identified inputs | Versioned snapshots and manifests | Review an exact candidate, not an unknowable moving target; hashes do not prove authoritative or complete source material |
| Pooled averages | Candidate-specific gates and critical-failure precedence | A serious issue cannot disappear inside another candidate's average; gates remain configured decision aids |
| One-off result | Compatible baseline/revision comparison and regression cases | Makes a subsequent release review possible; compatibility and actual repeat use must be established |
| Technical dashboard and raw configuration | Guided forms, readable findings and optional engineering evidence | Reduces interpretation burden without discarding exact data; first-time users must still be tested |
| Automatic flag treated as completed review | Explicit source-bound human/AI-assisted review, pending states and decision capture | Separates machine output from accountable interpretation; an entered decision is not proof of expert correctness |
| Original-file convenience extraction | Source order, literal values, exact extracted-text spans and visible warnings | Prevents reviewing a distorted reference packet; complex/raster layouts remain limited |
| Nominal retries/configuration | Actual attempts, cache/call provenance and unknown missing measurements | Makes cost/latency/execution evidence more honest; unknown is not zero |
| Public server as sole delivery route | Browser-tab execution plus distinct native modes | Changes custody, persistence and connection limits; browser availability is not durable infrastructure |
| Feature count as apparent progress | Activation, comprehension, repeated releases and customer outcomes | Engineering completion is necessary but does not establish demand or commercial value |

## 7. Current delivery and version snapshot

**Delivery evidence updated on 17 September 2026.** The hosted correction is merged, all branch/PR/main checks passed, and the bounded custom journey was exercised on the primary site. Real-assistant, independent-user and manual-picker acceptance remain open. The browser alternative retains its September 16 publication identity. Refresh this section after meaningful delivery or validation; do not infer deployment from source alone.

### Delivery states

| State | Exact evidence / scope | What can be claimed |
|---|---|---|
| **Primary public address** | [Streamlit app](https://ai-reliability-studio.streamlit.app/); native `2026.09.17.1` / evaluator v8; custom preparation, HTTPS transport, synthetic run/revision, readable review and two-tab reset observed | Bounded hosted engineering beta; real-assistant/user acceptance remains unproven. Sessions are temporary and Community Cloud may hibernate |
| **Deployed browser alternative** | [Browser app](https://ai-reliability-studio.a3103.chatgpt.site/), Sites version 8; source commit `42fbd99c1b3483b95ad1c182ef5de5ab39f2a30c` | Browser application `2026.09.16.1` remains published; no new Sites deployment is claimed |
| **Browser source identity** | Manifest `0ee0ca87c77811bcc52adc751ab8d70c03b24f6356993e6bdb04c05f912d460c`, matching application source `b9d8131a7238c8d3abda03722f0f36294baf5ddf` | This is the browser archive identity, not a source hash for the updated native Streamlit service |
| **Merged into GitHub main** | [PR 13](https://github.com/AryanS313/ai-reliability-studio/pull/13), merge `bcdd6103ca713cb7f58d8736bfa563c308cebd7f`, 17 September 04:59 IST | Main contains native release `2026.09.17.1`, hosted custom sessions, portable projects and clearer connection choices. All five jobs passed on branch, PR and merged main |
| **Other branches / requested checkout** | `codex/hosted-custom-workflow`, final application branch revision `528f918`; earlier release history retained | Source is included by the merge. Use remote/main ancestry and `git status` for any later documentation or checkout changes |
| **This documentation milestone** | Product history and linked audit/release records reconcile the merge and live observations | Documentation does not turn an unobserved hosted workflow into acceptance |
| **Local artifacts** | Ignored environments, fixture databases, caches and verification logs | These are not customer evidence or deployed inputs |
| **Acceptance still required** | Approved real assistant/account, independent domain/user review, downloaded-file inspection and native-picker restore, mobile/accessibility | Synthetic custom comparison, download controls and two-session reset were observed; automated restore is separate evidence. No customer/commercial proof |
| **Proposed, not validated** | Discovery/two-release pilot, customer measurement, managed services and future improvements | Plans and event schemas are not achieved outcomes or operating services |

The original local branch named `main` can also be stale; it was still at the May development-container commit during history inspection. Use **GitHub `refs/heads/main` / `origin/main` after verification**, not a local branch's name, to determine what was merged remotely. The obsolete folder outside `Workspace/Projects` is not the working repository.

### Formal identifiers

| Identifier | Native merged release | Separately published browser | Meaning |
|---|---|---|---|
| Package version (`pyproject.toml`) | `1.0.0` | `1.0.0` | Declared package version; insufficient to identify behavior |
| Application release (`src/config.py`) | `2026.09.17.1` | `2026.09.16.1` | Distinct native correction and browser publication |
| Evaluator | `deterministic-v8` | `deterministic-v8` | Evaluation logic identity, not an accuracy rating |
| Label semantics | `failure-labels-v3` | `failure-labels-v3` | Meaning of result labels |
| Report schema | `2.1` | `2.1` | Machine-readable report contract |
| Saved review / workspace | `saved-response-review-v1` / `saved-answer-workspace-v1` | Same schema names | Imported-response review contracts |
| Full project resume | `project-workspace-v1` | Not claimed in the older deployed archive | Private portable inputs and unverified historical runs |
| Browser execution adapter | Browser source retained in repository | `browser-sequential-v2` | Browser scheduling, not a model identity |
| Hosting publication | Existing Streamlit service; bounded custom workflow observed | Sites `8` | Hosting identity is separate from source/version markers |

No official v2/v3 product releases or tagged 1.0.0 release should be invented from these analytical stages. Version-label alignment is technical debt; source/evaluator/report identities must accompany consequential evidence.

### Current user journey and custody

The main site now provides the corrected hosted-session journey. **The custom path was exercised with bundled fictional inputs and synthetic answers; HTTPS connectivity was tested against a non-AI public endpoint.** Those checks establish workflow behavior, not real assistant quality or independent user comprehension. Nontechnical visitors do not need a repository checkout, local runtime or JSON configuration. Engineers may still supply an assistant’s connection contract.

1. **Understand and try:** the support-release landing explains the decision; one action runs 32 fictional cases and opens their summary. Three intentionally simulated execution errors demonstrate exclusion from quality averages.
2. **Prepare:** acknowledge data handling, create/reopen a project, add approved sources and expected behaviors, resolve validation/coverage issues and version the prompt.
3. **Connect or import:** the native main site configures a staging endpoint through readable fields and an explicit consented test request. Public HTTPS transport was observed; an approved real-assistant/account trial remains required. The browser accepts saved answers or supported provider calls with an entered session key; it does not connect arbitrary assistant endpoints.
4. **Evaluate:** authorize real data flow and bounded attempts; capture actual executions separately from quality results and immutable input identities.
5. **Review:** inspect expected/observed/source evidence, severity, recommended action, uncertain findings, gates and missing calibration. Capture the release or source-review decision with honest attribution.
6. **Return:** preserve/export work, compare a compatible revision to its baseline, add confirmed incidents as regression cases and repeat at the next release. Browser work must be downloaded to survive closing/reloading or returning after 24 hours of inactivity; persistent private native projects follow their configured repository policy.

## 8. Capabilities and non-capabilities

### What the product can currently do

| Capability | Where present / delivery state | Independent engineering verification / boundary |
|---|---|---|
| Guided sample and readable decision summary | Published native main site and browser alternative | 32-case live journey observed; synthetic-only verdict and separate execution errors verified |
| Version prompts, cases, documents, targets and manifests | Integrated release on main and published browser where applicable | Storage/provenance regressions pass; manifests identify inputs, not source authenticity |
| Upload/extract/chunk and retrieve approved documents | Published native main site and browser alternative | Primary host processed five bundled documents/30 passages; local office indexing/retrieval and parser tests passed. Manual native picker unverified; no complete-layout/OCR guarantee |
| Create, edit, validate and assess dataset coverage | Current local/published app | Automated UI/schema coverage; representative coverage still requires domain judgment |
| Review supplied answers, attribute decisions, retest replacements, export/restore workspaces | Present on main and preserved in local/published integration | Hash/attribution/partial-retest/restore tests; actual local browser review persistence and fictional replacements observed; does not prove client retrieval or reviewer accuracy |
| Call supported foundation-model providers | Present on main/current local and browser transport | SDK/transport/error tests; browser route restrictions verified. No paid account/live credential acceptance established in this release |
| Call external staging assistants through a form | Published native hosted-session service; **arbitrary HTTP remains unavailable in the browser alternative** | Consented public HTTPS GET observed; network/mapping/credential/failure regressions pass. Actual authorized assistant/account trial remains open |
| Evaluate correctness constraints, citations, grounding, escalation, safety, resources and retrieval | Current evaluator v8 on main and published | Finite deterministic/regression evidence, uncertainty and scope constraints; no general semantic guarantee |
| Compare candidates, calibrate held-out judgments, gate and report | Current local/published app as applicable; earlier foundations on main | Version/case/calibration compatibility and critical precedence tested; real-domain calibration not collected |
| CLI/CI, SQLite/PostgreSQL repository contracts and role controls | Native repository code, not a managed browser service | Native suite and disposable PostgreSQL pass; remote Python 3.11/3.12, PostgreSQL and container checks also passed after the recorded setup corrections |
| Record content-free product workflow events | Current integration; local authorized event sink | Allowlisted typed attributes, deduplication and rejection tests; no central analytics service, cross-device tracking or measured retention |

“Independent” here means checked against code/tests/runtime separately from a feature's existence. It does **not** mean a third-party security audit, independent human calibration or customer validation.

### What it cannot truthfully do

- Claim real-assistant/account acceptance from the observed synthetic custom journey or public GitHub HTTPS check. The native main site is live, but authorized assistant access and independently judged real answers are still required.
- Certify safety, regulatory compliance or unrestricted production readiness.
- Replace a domain expert, policy owner or accountable human release decision-maker.
- Evaluate every autonomous-agent trajectory, action side effect or environment outcome.
- Guarantee general semantic correctness, complete hallucination detection or perfect citation support determination.
- Treat synthetic fixtures, a programmed prompt comparison or an imported answer file as proof of real model quality or deployed improvement.
- Guarantee evaluator accuracy without representative, independently reviewed held-out domain calibration.
- Automatically fix or deploy the assistant being evaluated; suggested prompt changes remain proposals.
- Provide managed continuous monitoring, durable workers, backups, incident response or an availability SLA by itself.
- Observe an external assistant's internal retrieval simply from its answer API. Missing internal evidence and reported metrics remain unknown/unverified.
- Turn local adapter interfaces, PostgreSQL/RBAC code or tab isolation into a managed multi-user enterprise service.
- Claim real account/provider compatibility from mocked transports, or full document fidelity from a finite fixture corpus.
- Guarantee that automated redaction removes every sensitive/business detail. Resumable workspace files contain original private material and are different from redacted reports.
- Promise persistence of an unexported browser workspace or secure erasure of every copy/audit record merely because a tab closes.
- Claim adoption, retention, investigation time saved, willingness to continue/pay, testimonials or customer regressions caught without real evidence.

## 9. Evidence maturity and verification condition

The table below preserves the September 16 evidence baseline. The newer hosted correction passed 1,205 local tests with zero skips and 87.53% coverage; remote Python jobs each passed 1,199 tests with six service tests passed separately and 85.58% non-service coverage. Section 4 and the hosted workflow review distinguish these checks and the observed bounded custom journey from missing real-assistant and independent-user acceptance.

| Evidence category | What exists | What it does not establish / next proof |
|---|---|---|
| **Engineering** | 1,061 tests passed, zero skips including disposable PostgreSQL; 87.86% branch-enabled source coverage; Ruff/format/mypy/pip consistency passed. Copy-only sample refinement passed its focused regression; four subsequent release/sample checks passed. Four dependency-builder and nine Fetch-retry tests passed | Tests do not measure demand, human comprehension or general semantic accuracy. `app.py` is covered by UI tests but outside the `src` coverage denominator. Remote Python 3.11/3.12 each passed 1,055 tests with six PostgreSQL tests separately passed; 85.66% coverage for non-service jobs. Container health, non-root identity and sample passed |
| **Evaluation validity** | Constraint/citation/uncertainty/gate/comparison invariants and authored adversarial cases; human calibration machinery | No measured domain false-positive/false-negative rates or representative unseen customer benchmark; seeded failures are not customer regressions |
| **Security** | Role/session/secret/upload/destination/redaction tests, disposable PostgreSQL boundaries, separate live tabs/reset, scoped dependency review | No blanket security certification, penetration audit or managed ingress/retention assurance. Four compiled browser packages retain advisories with restricted tested paths |
| **Deployment** | Sites version 8 succeeded; live source hash matched; public root/studio and sample worked with required isolation headers; no browser runtime error logs in that check | Not a longitudinal availability, load, provider-CORS or live-account test. GitHub branch and PR checks passed and the release merged into main; the initial authorization and check failures were resolved |
| **Usability and product acceptance — September 16 baseline** | Agent-driven browser and AppTest journeys, readable no-JSON review, narrow-layout observations and error recovery; owner rejected sample-only scope on September 17 | The then-missing hosted path was subsequently delivered as the bounded workflow in section 4. Independent first-use study, full accessibility and measured comprehension/time-to-value remain absent |
| **Customer** | Evidence-informed brief, discovery plan and proposed two-release pilot | No interviews, qualified partner cohort, customer usage, retention or confirmed outcomes supplied/collected |
| **Commercial** | Sponsor/buyer hypotheses and continuation/willingness-to-pay questions | No contract, payment, conversion, pricing validation or continuation commitment established |

### Security and operating state

The supported native environment is Python **3.11 or 3.12**; local verification used **3.12.14**. The older 3.9 virtual environment was preserved, not used to weaken compatibility requirements. The browser uses **Stlite 0.76.0 / Streamlit 1.41.0 / Pyodide 0.26.4 / Python 3.12.1**, a separate dependency surface.

Native Python and wrapper npm audits reported no known findings at the recorded checks. The browser's 69-package inventory retained **44 advisory records across four packages** after compatible patches: cryptography 11, lxml 2, Pillow 29, scikit-learn 2. Records are not distinct-CVE counts or proof of reachable exploits. Eleven actual Wasm dependency-path tests passed, including entity/image/font tripwires, vectorizer cleanup and transport restrictions; Protobuf 5.29.6 pure-Python and Streamlit message round trips were verified. Those tests do not clear every vulnerable API, C dependency or interpreter issue. The [dependency review](design-partner/browser-dependency-review.md) is the authoritative scope and maintenance obligation.

Native `public-demo` is isolated and sample-only; true Wasm `browser` mode permits tab-local custom work and explicit-key supported provider calls; `local` is a trusted operator's persistent workspace; `authenticated` needs validated external identity/infrastructure. Setting a browser flag on ordinary Python does not grant browser privileges. Workspaces, exports, model calls and deletion retain distinct authorization/data-handling boundaries.

The merged correction adds `hosted-session` for isolated, temporary online custom work with bounded operations and fresh visitor credentials. Custom preparation, consented public HTTPS transport, synthetic revision comparison and two-session reset were observed on the primary site; approved real-account and independent usability acceptance remain separate gates.

Operational debt includes the large browser startup download, an aging compiled runtime, synchronous/sequential browser runs, a large Streamlit orchestration file, dual native/browser UI compatibility, retained package-version ambiguity and non-production infrastructure adapters. Addressing these must follow user need or applicable risk; their existence is not a reason to resume unfocused feature expansion.

### Unmeasured outcomes

| Measure | Current baseline | Required evidence / owner |
|---|---|---|
| Customer interviews and repeated problem frequency | Unmeasured; no conducted interviews recorded | Recent-release artifact interviews with qualified teams / product lead |
| Unassisted sample completion | Unmeasured; agent completion is separate | At least five independent first-time tasks with assistance/abandonments recorded / product/UX |
| Time to first trustworthy real result | Unmeasured | Actual team start through understood non-synthetic finding, including setup/provider waits / product + partner engineer |
| Real endpoint/account compatibility | Unvalidated with partner credentials | Authorized staging run, real request/response evidence and failure recovery / partner engineer |
| Domain evaluator false positives/negatives | Unmeasured | Representative held-out cases, independent adjudication and confusion matrix / domain/evaluation owner |
| Decision comprehension | Unmeasured | Reviewer explains failure, severity, next action, evidence type and missing evidence without coaching / product + domain owner |
| Repeat use and baseline comparison | Unmeasured | Team-initiated next real release, opportunity denominator and comparable inputs / product lead |
| Investigation time saved | Unmeasured | Observed baseline versus tool-assisted investigation with methodology and sample size / product lead |
| Retention | Unmeasured | Eligible team cohorts over actual release opportunities, excluding internal/synthetic reruns / product lead |
| Willingness to continue or pay | Unmeasured | Concrete scoped continuation commitment; explicit refusal/no-answer accounting / sponsor + product lead |

Use the [36-metric dictionary](design-partner/success-metrics.md) for definitions, formulas, sources, retained baselines, targets, guardrails, thresholds, owners and validation. Its nine categories are acquisition/qualification, activation, workflow, integrity, reliability, security, retention, customer/commercial outcomes and operability. Targets are pilot hypotheses, not achieved results. A sample event is not real activation; anonymous sessions are not a retention cohort; unknown cost is not zero; higher scores from deleting hard cases are not progress. No external analytics collector is implemented.

## 10. Decisions, mistakes and corrections

| Decision or correction | Evidence / reason type | Risk or new understanding | Consequence and unresolved trade-off |
|---|---|---|---|
| Optimize the original walkthrough for demonstration | Original README and prompt-aware mock; documented fact | A persuasive improvement story was constructed by the mock itself | Preserve the useful sample, remove implied independent efficacy; portfolio value must come from real ownership/outcomes |
| Permit provider failure to become mock output | Original client and July behavior; verified implementation | Successful-looking scores could describe a substitute response rather than the requested model | August separates execution from quality; September/current preserve usage and provenance even on failure |
| Apply readiness labels to synthetic/pooled results | Original scoring function; verified implementation | Users could infer launch approval from fictional or mixed evidence | August no-launch and candidate-specific gates; current UI explains limits and missing evidence |
| Expand formats/providers before validating ICP | July diff and absence of customer records; fact plus PM inference | Compatibility improves, but added scope is not evidence of demand | Retain useful compatibility; test a narrow support-release job before adding new audiences/features |
| Build enterprise foundations before proving pull | August plan/source; sequencing assessment is PM inference | Interfaces and tests can be mistaken for a managed enterprise product | Keep boundaries explicit; managed identity, DB, workers, scanning, monitoring and backups remain deployment requirements |
| Treat repository scoping as sufficient public isolation | Global facade and later ContextVar/session repair; verified implementation | Separate repository methods alone do not bind a request to its visitor | Distinguish original risk from proven incident; require runtime/session verification and fail-closed access modes |
| Inherit owner keys or low-level configuration into public flows | Historical public/provider changes and current controls; verified implementation | Unintended spend, disclosure or confusing setup could block trust | Suppress ambient public credentials, require explicit session keys/consent, restrict destinations, and use readable forms |
| Assume main, local feature and live app describe one state | Verified branch/deployment divergence; observed fact | Shipping the old baseline could remove September capabilities; audit claims could falsely accuse the newer live app | Integrate main, bind deployment to source, and maintain separate delivery rows; authorization, push, checks and merge are now verified; preserve distinct source/deployment identities |
| Treat a build as hosted verification | Worker-header failure and subsequent fix; documented correction | Browser runtime depends on the final origin and isolation policy | Test the published source and startup; still no SLA or universal-browser claim |
| Prioritize plain-language decisions over exposed internals | Owner request plus UI audit; direct evidence, not customer study | Raw JSON/opaque versions demand implementation knowledge before value is apparent | Preserve exact backend evidence and optional engineering exports; independently test comprehension next |
| Keep unknown or unverified evidence unresolved | Constraint/source/calibration/review regressions; verified implementation | Aggressive automation can create false confidence or false accusations | Human review may take longer; conservative uncertainty is intentional and needs domain validation |
| Retain a scoped browser runtime while patching compatible dependencies | Dependency inventory, source reachability and actual Wasm tests; observed evidence | A native clean audit hides browser advisories; a wholesale upgrade is not automatically a complete fix | Document exceptions and restrict affected APIs; upgrade/rebuild or disable a path if an advisory becomes applicable |
| Do not remove CI files to evade denied GitHub permission | Actual OAuth push rejection; observed fact | Dropping controls would “finish” publication by weakening the requested release | Keep full reviewed code; require genuine GitHub account authorization before pushing/merging |
| Restrict the main site to samples and present local installation as the custom route | Agent implementation choice motivated by safety; owner discovered and rejected it on 17 September | An unapproved reduction removed the visitor's core online job while passing tests covered only the narrower mode | Preserve safeguards while implementing the complete hosted custom path. Reopen the release blocker and correct maturity/completion claims; URL selection was not approval of the restriction |

No row above invents an incident, interview, prevented loss or customer's motivation. The plain-language request and rejection of the hosted restriction are direct owner feedback; neither is external customer validation.

## 11. Outstanding work and next milestone

### Required acceptance and release guardrails

The previous **sample-only main-site implementation blocker is resolved within the observed engineering scope**. Native `2026.09.17.1` is live, all branch/PR/main jobs passed, and the custom synthetic baseline/revision journey plus a consented public HTTPS connection were exercised on the main origin. Full owner acceptance remains unproven for these reasons:

1. **Approved real assistant/account trial:** provide a staging endpoint or supported provider account, approved data and a scoped visitor credential. Verify authentication, actual answers, failure recovery and a meaningful revision on the hosted path. A public GitHub GET and synthetic cases cannot substitute.
2. **Independent user/domain acceptance:** observe unassisted setup and result teach-back, adjudicate representative held-out labels, and assess mobile/assistive-technology behavior. These require people and evidence independent of the authoring agent.
3. **Manual input/output acceptance:** automated parsers and project round-trip restore passed; native file-picker selection and actual downloaded-file contents were not manually verified because desktop control was denied. Do not report those actions as completed.
4. **Any new critical integrity/security failure:** stop rollout if one is found. The bounded tests and live isolation observation are not a blanket security certificate; the older browser's compiled-dependency exceptions remain explicit.

### Highest-priority product milestone

Run a **qualified two-release design-partner pilot on the main website**, beginning with the approved real-assistant trial and independent first-use tasks. An engineer and domain owner supply approved reference material and staging access, inspect one consequential finding or evidence gap, and return for their next actual revision. This tests integration, domain validity, comprehension and recurrence together. [H11]

Proposed learning rules remain at least four of six interviewed teams showing a repeated review problem; four of five unassisted users completing and correctly explaining the sample; and three of five activated teams with a second-release opportunity returning to compare. These are small-sample decision rules, not existing conversion rates. No outreach is implied or sent by this plan.

### Design-partner follow-ups

- Validate the ICP, buyer/sponsor, urgency, existing alternatives and reasons to switch; narrow or revise based on counterevidence.
- Observe unassisted onboarding, integration effort, accessible keyboard/mobile behavior and decision comprehension.
- Establish domain-specific held-out calibration and adjudicate false positives/negatives before trusting consequential findings.
- Test representative real endpoint/provider behavior, exports/restoration and multi-session boundaries under the intended pilot deployment.
- Measure confirmed regressions, investigation effort, decisions changed, repeat releases and continuation commitment without counting synthetic/internal activity.
- Prioritize browser load/runtime debt and the next usability changes using observed pilot friction and security applicability.

### Enterprise-production requirements

Managed identity and ingress, managed database and tenant controls, durable workers/artifact storage, malware scanning/OCR where promised, centralized monitoring/incident response, retention/legal-hold enforcement, backups/restore drills, capacity and availability testing, security assessment, provider/data agreements and operating ownership. Adapter interfaces are foundations for this work, not its completion.

### Open product decisions

**Branded address:** choose an owned/purchased hostname and provide DNS account access when ready. Custom-domain attachment is supported by the existing host, but a name, price and account have not been selected. No purchase or migration is claimed; Streamlit is the temporary primary link.

**Hosted implementation:** the complete main-site journey remains a requirement. The corrected online workflow is now delivered and bounded engineering verification passed; real-assistant, independent-user and manual-picker acceptance remain open. The Cloudflare decision is paused; no hosting migration or purchase is claimed.

The ICP and recurrence hypothesis, whether teams prefer saved-answer import or staging integration, who funds adoption, acceptable calibration/integration burden and commercial packaging remain unresolved by customer evidence. Do not add pricing, certification, fully autonomous agents or central telemetry merely to make the product look complete.

## 12. Living milestone ledger

Historical dates and implementation details are in section 4. Add a row after each subsequent meaningful change, including a correction to an earlier claim.

| Recorded milestone | Change / reason / user problem | Verified | Still unverified | Affected areas / superseded claim |
|---|---|---|---|---|
| 16 Sep — local design-partner candidate, `079459e` | Narrow ICP, guided/plain-language review, stronger prerequisites/evidence; reduce confusing setup and misleading decisions | Historical local 573-test result and bounded UI checks in release report | Customer comprehension, domain validity, current main integration | Positioning, UX, integrity, security; older 13-destination/JSON-first baseline no longer describes this candidate |
| 16 Sep — integrated application, `b9d8131` | Preserve newer main while incorporating candidate; handle browser scheduling and dependency differences | 1,061-test combined suite, audits/builds, actual Wasm and local browser paths | Remote CI, live account/customer behavior | Architecture, workflow, integrity, security; pre-integration 573 count is no longer the final application verification result |
| 16 Sep — Sites version 8, receipts `3ca82d4`/`b51aaa7` | Publish approved exact source, verify final origin and honest sample/reset | Deployment succeeded, source hash/headers, 32-case sample, separate tabs and reset | GitHub push/merge, remote CI, sustained operation and adoption | Deployment readiness; “local-only” is obsolete, but “merged into GitHub main” would still be false |
| 16 Sep — GitHub authorization restored | Owner completed device authorization after a missing-scope rejection; preserve the full CI change rather than dropping it | CLI authentication completed; `workflow` scope verified | Branch push, PR/merge and remote CI at this snapshot | Delivery; authorization-blocked is no longer current, but published-to-GitHub would still be premature |
| 16 Sep — product-history documentation milestone | Reconstruct and preserve evidence-backed product evolution; make future PM handoffs self-contained | Git blobs, version declarations, remote main/PR records and release receipts reconciled; document links/structure reviewed | Historical customer motives not documented, independent product demand and pending GitHub publication/CI | Reporting discipline; May sample counts, version-stage labels and August/September attribution corrected; no application behavior change |
| 16 Sep — complete branch push and first remote checks | Pushed `35fb348`, opened the release PR; repair runner-inherited setuptools 79.0.1 through a conditional 83.0.0 pin | Remote browser build, PostgreSQL and container startup/sample passed; Python 3.11 audit exposed the inherited tool before tests | Corrected Python checks and merge; customer evidence remains absent | Delivery/reproducibility; branch publication is verified, but merge is not yet complete; audit remains enforced |
| 16 Sep — CLI smoke configuration correction | The standalone CI command omitted explicit private-local mode after public mode became the safe default; set APP_ACCESS_MODE only on that smoke step | Python 3.12 suite passed before this separate smoke failure; exact corrected command checked locally | Corrected complete remote run and merge | Reproducibility/security; no public-session bypass or weaker synthetic assertion |
| 16 Sep — verified GitHub merge and completed documentation handoff | Resolve both remote-check failures, pass complete branch/PR checks, merge `026a3e7` and reconcile all supporting audit documents | [PR merge](https://github.com/AryanS313/ai-reliability-studio/pull/12), [passing CI](https://github.com/AryanS313/ai-reliability-studio/actions/runs/35035175653), exact source-hash match; local links and all 36 metric contracts checked | Real account/assistant, independent comprehension, domain validity, adoption and commercial outcomes | Delivery, reproducibility and reporting; “push/merge pending” and “Python 3.11/container unexecuted” are superseded; no new browser behavior |
| 16 Sep — temporary Streamlit primary address | Owner requested a normal branded address, then chose Streamlit as the interim entry while away; update primary links and preserve the browser alternative | Existing Streamlit origin renders updated guided app, completes 32-case review, keeps a second session empty and resets cleanly; GitHub homepage changed | Branded hostname selection, DNS/account access and new-origin validation | Positioning/distribution; the Sites address is no longer the primary CTA; no new hosting spend or domain claimed |
| 17 Sep — owner rejects sample-only main-site scope | Owner discovered the restriction and requires the complete online custom journey for nontechnical visitors; agent's safety-motivated scope reduction was not approved | Direct owner correction; existing primary deployment is still sample-only; prior merge/CI/sample receipts retain their limited scope | Hosted custom implementation, final-origin acceptance, real account/domain/user validation; Cloudflare decision paused | Strategy, onboarding, hosting and reporting; prior completion/design-partner acceptance overstated. Requested hosted product is technical alpha; separate bounded browser beta remains published. No new deployment or customer evidence |
| 17 Sep — local hosted-session and project-resume implementation | Implement the requested online path and a bounded, private download/restore route for repeat use; preserve safeguards and distrust imported evidence | Focused project/storage 136 tests; independent project/UI 85 tests; local 32-case sample download/second-session restore/review/export; portability Ruff/format/mypy | Whole-release checks, new deployment/final-origin custom acceptance, actual assistant credentials, independent customer outcomes | Workflow, persistence, security and integrity; code exists locally but main-site restriction is not yet claimed removed. Original binaries and trusted imported calibration are not promised |
| 17 Sep — complete local hosted-candidate verification | Verify the combined correction and retain an explicit separation from deployment/customer proof | Python 3.12.14: 1,203 passed, zero skips including six PostgreSQL checks; 87.53% coverage; Ruff/119-file format/46-module mypy/dependency checks; 104 focused security checks; actual local custom preparation/retrieval observed | New remote CI/merge, primary-origin deployment and complete custom acceptance, real account, domain/user/customer outcomes | Release evidence and reporting; whole local verification is complete, while the currently recorded primary site is still sample-only. See hosted workflow review |
| 17 Sep — frozen local verification and standing scope rule | Main-site-only customer workflow becomes a non-negotiable repository requirement; changelog updated alongside history | 1,205 tests, zero skipped, 87.53% coverage; local browser custom preparation, real public HTTPS connectivity and two separate sessions | New remote CI/merge/deployment; manual picker restriction; real assistant/account/customer acceptance | Workflow, security, reporting and readiness; this is local engineering evidence, not a new deployment or customer validation |
| 17 Sep — hosted correction merged and live entry observed | Restore the requested online scope and clarify setup after owner feedback | PR 13 merge `bcdd610`; branch/PR all five jobs passed; final local 1,205 tests/zero skips/87.53%; primary Start project/Resume and separate privacy gates observed | Merged-main CI running, complete final-origin custom/real-account acceptance, manual picker, independent domain/customer outcomes | Delivery and reporting; “not pushed/merged” and current “sample-only primary site” are superseded. Native `2026.09.17.1` differs from unchanged browser `2026.09.16.1` |
| 17 Sep — bounded hosted-origin verification complete | Check the owner’s online workflow and preserve the distinction from real-assistant/customer proof | All five merged-main jobs passed; live Settings `2026.09.17.1` / evaluator v8; custom preparation, HTTPS transport, two 32-case synthetic runs, inconclusive comparison, download controls and two-tab reset observed | Real assistant/account, manual downloaded-file/picker verification, independent domain/usability, actual recurrence/payment | Delivery, UX and reporting; initial-entry-only and main-CI-running descriptions are superseded. Bounded hosted beta engineering delivery; full owner definition of done unproven |

Every future row must identify the prior state, change, reason, evidence type, validation, remaining uncertainty and affected positioning/workflow/integrity/security/deployment claims. Record removals, restrictions, mistakes and contrary evidence as deliberately as additions. Do not overwrite an old measured baseline with a new result.


## 13. Standing project-update and completion contract

When the owner requests a project update—especially “give me the complete project update”—provide a **self-contained** report covering all of the following. Links support the answer; they do not replace requested explanations.

1. Executive summary.
2. How the project originally started, distinguishing the earliest record from undocumented inception.
3. Original goals and deliverables.
4. Complete product/version timeline, with analytical stages clearly labeled.
5. How and why the product changed, separating fact from PM inference.
6. Important strategic decisions, mistakes and corrections.
7. Changes since the previous recorded update.
8. What is deployed, merged/committed, on another branch, uncommitted and proposed.
9. What the product can do now, with runtime/delivery boundaries.
10. Who currently benefits and which audience assumptions remain hypotheses.
11. What still needs to change, prioritized by user/trust/release impact.
12. What the product still cannot truthfully do.
13. Current test, release, security, operating and deployment condition.
14. Customer and commercial evidence actually collected—or explicitly absent.
15. Evidence still missing and how it will be collected.
16. Highest-priority next milestone and why it resolves the most important uncertainty.
17. Honest maturity classification justified by evidence, not feature count.

Unsolicited short progress notes can remain concise. A final completion report must include this full PM evolution view alongside technical results and link this document. Classify the product as concept prototype, portfolio MVP, technical alpha, design-partner beta, production candidate, generally available, or a more accurate equivalent; explain the scope and missing evidence. Preserve the distinction between the bounded hosted engineering delivery, its unproven real-assistant/independent-user acceptance, the separately published browser beta and unvalidated customer/commercial outcomes. Engineering release success must not override an unfulfilled owner requirement.

### Maintenance checklist

- Read the current snapshot before meaningful implementation; verify relevant Git and deployment state rather than inheriting an old label.
- Update the top delta, current state, timeline/ledger, capabilities, evidence maturity, risks and next milestone whenever product, UX, evaluation, security, architecture or readiness changes.
- Cite the exact revision and source/test/observation. Mark unavailable evidence and PM inference explicitly.
- Refresh application/evaluator/report/hosting identities separately. Keep source commits and deployed manifests traceable without secrets or private customer material.
- If a capability is removed/restricted, or a previous claim is no longer accurate, name the correction and reason.
- At handoff, inspect `git status`, remote main and deployment evidence; record only states actually achieved. Do not call a locally completed feature shipped without delivery evidence.
