# AI Reliability Studio: product evolution and PM handoff

**Last evidence update: 16 September 2026 (Asia/Kolkata).** This is the living product history, decision record and handoff. It complements the [technical changelog](../CHANGELOG.md), [release verification](design-partner/release-review.md), [product brief](design-partner/product-brief.md) and [success-metric dictionary](design-partner/success-metrics.md).

## Changes since the previous update

- The complete release branch, including the living product history, was pushed at `35fb348`. [The release PR](https://github.com/AryanS313/ai-reliability-studio/pull/12) is open; merge awaits passing checks.
- GitHub verified browser distribution, PostgreSQL and non-root container startup/sample execution. Python 3.11 stopped at its dependency audit: the runner inherited vulnerable setuptools 79.0.1. The fix pins patched setuptools 83.0.0 for Python 3.11 installation paths; no advisory is ignored. The corrected remote run remains to be observed.
- GitHub main still has the 8 September release. Sites version 8 continues serving the verified application `2026.09.16.1`; the dependency correction affects native Python 3.11 setup, not the published Wasm runtime.
- Customer interviews, unassisted comprehension, repeat use and commercial outcomes remain unmeasured. Software verification does not establish these outcomes.

For every later meaningful milestone, replace this short delta section, refresh the delivery snapshot, and append to the milestone ledger near the end. Preserve earlier evidence and corrections rather than rewriting the past to fit the latest positioning.

## 1. Executive summary and maturity

AI Reliability Studio began as a local-first evaluation dashboard with an explicit portfolio/recruiter demonstration path. It made a useful loop visible: provide documents, a prompt and expected answers; generate responses; inspect scores and failures; compare prompts; export results. Its synthetic comparison deliberately favored the proposed improved prompt. That made the demonstration understandable but could not establish real improvement.

The August rewrite made trustworthy release evidence a central engineering concern: versioned inputs, explicit execution failures, candidate-specific gates, source-aware checks, calibration, external targets and reproducible reports. September work repaired the human review journey, public session boundaries, provider behavior, source fidelity, workspace restoration and browser distribution. The current work narrows the intended customer to a small team releasing a support assistant grounded in written knowledge, and prioritizes understanding, a repeatable decision workflow and measurable adoption over additional platform breadth.

**Current classification: published, bounded design-partner beta; engineering validation is materially stronger than customer validation.** The app has a verified live demonstration and working review mechanics. It has no established customer cohort, independent first-use acceptance, measured retention, domain-specific evaluator error rates or commercial evidence. GitHub authorization and branch push are complete; remote checks and merge remain in progress. These limits prevent classifying it as a production candidate or generally available managed product. “Design-partner beta” describes the intended limited pilot boundary, not evidence that partners have already adopted it.

The next product proof is an engineer and domain owner reviewing their own assistant, understanding one finding or evidence gap, and returning at the next real release. Another internal sample run does not supply that proof.

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
| H09 | `e018414`, `42eba19`; [source/execution PR](https://github.com/AryanS313/ai-reliability-studio/pull/10), [restore-controls PR](https://github.com/AryanS313/ai-reliability-studio/pull/11); [source-review acceptance](SOURCE_REVIEW_ACCEPTANCE.md) | Source fidelity, execution accounting and restoration corrections; main's last verified merged state |
| H10 | Local `079459e`, `b9d8131`, `3ca82d4`, `b51aaa7`; [gap matrix](design-partner/gap-matrix.md), [workflow audit](design-partner/workflow-audit.md), [plain-language review](design-partner/plain-language-review.md), [release review](design-partner/release-review.md) | Current implementation, integration, verification and publication receipt; now pushed in the release branch, with merge tracked below |
| H11 | [Product brief](design-partner/product-brief.md), [discovery plan](design-partner/discovery-plan.md), [metrics](design-partner/success-metrics.md) | Research-informed ICP and validation hypotheses; not completed customer research |
| H12 | [Browser dependency review](design-partner/browser-dependency-review.md), native verification logs and actual Wasm harness results referenced there | Scoped engineering/security verification and unresolved dependency limits |

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
- **Limit:** this historical public mode could still use explicitly supplied provider keys and allowlisted external targets; it was not today's sample-only native mode. Fixture/SDK tests do not prove paid API access, reviewer correctness or independent onboarding. [H06]

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
- **Limit:** complex layouts, OCR, complete extraction and actual customer-provider compatibility remain unproven. Restored review hashes preserve identity, not truth. Main's last independently checked merge is `3fc3e59`. [H09]

### 16 September 2026 — focused design-partner workflow

- **Refs/type:** local `079459e`; analytical design-partner milestone. Package remains 1.0.0; evaluator becomes **`deterministic-v8`**, labels remain v3, report schema becomes **2.1**.
- **Before → change:** the requested August feature baseline has a broad technical surface, hidden prerequisites and JSON/configuration burden. Work narrows positioning to support/knowledge release reviews, reduces primary navigation from 13 to six steps, and makes the 32-case demonstration a one-action route to an understandable result.
- **Why/problem:** repository/browser audits and the owner's explicit request for an intuitive, plain-language experience are direct evidence. The sharper ICP, sponsor and repeat-use hypotheses are research-informed PM decisions; they are not validated interviews. JSON boxes and opaque versions obstructed interpretation, so exact evidence is retained behind readable labels and optional exports instead of deleted.
- **Result:** enforced privacy/project/role prerequisites, simpler connection forms, explicit external-call consent, safe credential/transport rules, decision capture, compatible baseline/revision comparison, conservative uncertainty/calibration gates, readable reports, and allowlisted local product events. Native public demo becomes sample-only; trusted local and authenticated modes have distinct boundaries.
- **Limit:** 573 passing tests/85.71% coverage described this **pre-integration local candidate**, not the final browser release. A fast agent-run sample and six navigation steps do not prove unassisted comprehension or reduced human task time. [H10–H11]

### 16 September 2026 — reconcile main, verify and publish the beta

- **Refs/type:** application integration `b9d8131`, documentation receipts `3ca82d4` and `b51aaa7`; application **`2026.09.16.1`**, Sites **version 8**. This is an actual publication plus a still-incomplete GitHub handoff, not a new declared package major version.
- **Before → change:** the local feature baseline lagged September main and the existing Site. Integration preserves saved-answer review/restoration/source fidelity/browser transport while adding the current guided workflow. Merely shipping the older branch would have lost working capabilities.
- **Why/problem:** verified branch divergence, Streamlit-version differences, actual browser concurrency requirements, older runtime advisories and the owner's authorization to ship. The 32-case sample needed explicit sequential execution in Wasm; its three intentional transport-error scenarios also needed wording that did not tell demo users to repair a real connection.
- **Result:** native Python 3.12, PostgreSQL, UI, dependency and actual Wasm checks pass within their stated scope. Compatible PDF/message/template/parser-selector dependencies are patched; unnecessary TF-IDF retained tokens are removed. Existing public Site is updated, and its source manifest, startup, synthetic sample, separate tabs and session clearing are verified.
- **Limit:** four compiled browser packages retain scoped advisory exceptions; neither native nor npm audit certifies that bundle. GitHub rejected the push for missing OAuth workflow scope, so no new GitHub merge/remote CI occurred. Real-account/provider acceptance and customer outcomes remain unverified. [H10, H12]

## 5. Product-management evolution

This table interprets the product, rather than renaming feature lists as strategy. Current recruitment/buyer/benefit statements are hypotheses unless marked otherwise.

| Dimension | May–July demonstration | August evidence platform | September/current direction |
|---|---|---|---|
| Vision | Show that assistant answers can be tested before launch | Make release evidence reproducible and less misleading | Help an engineer and domain owner decide what to fix before the next support-assistant release |
| Problem definition | Answer quality, grounding, escalation and trade-offs are hard to inspect | Scores can conceal synthetic data, failures, incompatible candidates or mutable inputs | Teams need an understandable, repeatable review that reaches an actionable decision |
| Market / ICP | Broad assistant-building teams plus explicit portfolio audience | Broad AI evaluation/platform audience; enterprise foundations | Small SaaS/product team with a policy-grounded read-only support assistant, approved data, staging access and a release due soon |
| Roles | Demonstrator or technical operator | Builder, reviewer and administrator in a scoped workspace | Engineer operates; PM/support/domain owner interprets and owns the release decision |
| Buyer / sponsor | Not established | Not established by architecture | Founder, engineering lead or product lead; budget and procurement assumptions unvalidated |
| Job to be done | Run cases and inspect a dashboard | Preserve trustworthy evidence about a candidate | Find consequential regressions, understand sources/limits, choose a next change and compare the revision |
| Activation | Load demo and reach results; no measured user criterion | Complete an evidence-bearing run | Demo teaches the loop; **real activation** requires a non-synthetic review plus an understood actionable finding/evidence gap |
| Core workflow | Upload → prompt/model → score → compare → CSV | Version inputs → execute target → gates/calibration → report | Start → Prepare → Connect → Evaluate → Review → History; saved-answer review is an alternative when endpoint access is unavailable |
| Return trigger | Improved-prompt comparison exists; return behavior unmeasured | Saved baselines and regression comparisons become possible | Next prompt/model/retrieval/policy revision or confirmed incident; preserve cases and review the same risks again |
| Value proposition | Visible QA beyond a chatbot demo | Reproducible, candidate-specific release evidence | Less work translating a support-assistant failure into a reviewed decision; time saved remains unmeasured |
| Differentiation | All-in-one demonstrable workflow | Evidence mechanics and conservative gates | Focused policy/source review and plain-language handoff; versioning/HTTP evaluation are not unique inventions |
| Metrics | Answer/retrieval/citation/grounding/escalation, latency/cost and aggregate readiness | Candidate gates, execution counts, provenance, confidence and calibration | Preserve evidence metrics; add the nine-category adoption/operating scorecard and anti-gaming rules |
| Non-goals | Enterprise/team integrations largely roadmap items | Production services explicitly left behind adapter boundaries | No safety certification, universal agent evaluation, automatic deployment or managed observability claim |
| Main risk | A convincing demo being mistaken for real quality | Platform breadth and engineering assurance mistaken for customer pull | Usability, integration effort, evaluator false decisions, runtime debt and insufficient repeat-use evidence |
| Priority | Demonstrability and compatibility | Integrity, isolation, reproducibility, execution | Security/integrity → critical workflow → activation/interpretation → repeated use → accessibility/polish; features only for a supported need |

Current team size of roughly 2–10 builders and a next-change window of 30 days are qualification filters to test, not measured market facts. FinSure is an example of referenceable policy exceptions, not evidence that regulated financial decision approval is the right market. QA, agencies and risk/compliance reviewers remain secondary; they are not simultaneous primary ICPs. [H11]

## 6. Before-and-after transformations

| Earlier state | Corrected/current direction | Why it matters and remaining boundary |
|---|---|---|
| Portfolio demonstration | Bounded design-partner product | A working demo is an entry point; a real team's repeated release decision is the intended outcome, still unmeasured |
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

**Snapshot verified on 16 September 2026.** Refresh this section after any commit/merge/deployment or meaningful validation; do not infer delivery from the presence of code.

### Delivery states

| State | Exact evidence / scope | What can be claimed |
|---|---|---|
| **Deployed** | [Public app](https://ai-reliability-studio.a3103.chatgpt.site/), Sites version 8; hosting source commit `42fbd99c1b3483b95ad1c182ef5de5ab39f2a30c` | Browser application release `2026.09.16.1` is published; it is a source snapshot, not a hosted native server |
| **Published source verified** | Live source manifest `0ee0ca87c77811bcc52adc751ab8d70c03b24f6356993e6bdb04c05f912d460c` matched reviewed application `b9d8131a7238c8d3abda03722f0f36294baf5ddf` | The inspected live app corresponds to the integrated application, despite GitHub main lagging |
| **Merged into GitHub main** | Read-only API and remote-ref check returned `3fc3e5900f9f1926f85090c34caf13ee1130a1cf`, merged 8 September | Main has the earlier browser/saved-review/source/restore work, application `2026.09.08.2`, evaluator v7; it does not yet contain current design-partner integration |
| **Other committed local branches** | `codex/design-partner-release` in the integration worktree; `codex/design-partner-beta` in the requested checkout. Application `b9d8131`; later release-report receipts `3ca82d4`, `b51aaa7` | Current code and verification history are committed locally. The initial rejected push did not publish it; authorization was restored and the complete branch was subsequently pushed at `35fb348` |
| **This documentation milestone** | `docs/PRODUCT_EVOLUTION.md`, standing repository instructions and documentation links; identify its revision with `git log -1 --format=%H -- docs/PRODUCT_EVOLUTION.md` | Committed and pushed at `35fb348`; not yet part of GitHub main or the already-published browser archive |
| **Uncommitted work / local artifacts** | Use `git status --short` at handoff. Ignored environments, fixture databases, dependency caches and verification logs remain local | Local artifacts are not customer evidence or shipped source. No uncommitted application behavior is required for the published beta |
| **Proposed, not implemented/validated** | Discovery/pilot plan, centrally operated services, customer measurement and future improvements below | A plan, interface, event schema or target metric is not an operating service or achieved outcome |

The original local branch named `main` can also be stale; it was still at the May development-container commit during history inspection. Use **GitHub `refs/heads/main` / `origin/main` after verification**, not a local branch's name, to determine what was merged remotely. The obsolete folder outside `Workspace/Projects` is not the working repository.

### Formal identifiers

| Identifier | Current local/published application | Last verified GitHub main | Meaning |
|---|---|---|---|
| Package version (`pyproject.toml`) | `1.0.0` | `1.0.0` | Declared package version; unchanged since August, so insufficient to identify current behavior |
| Application release (`src/config.py`) | `2026.09.16.1` | `2026.09.08.2` | Application revision marker |
| Evaluator (`src/scoring.py`) | `deterministic-v8` | `deterministic-v7` | Evaluation logic identity; not an accuracy rating |
| Label semantics | `failure-labels-v3` | `failure-labels-v3` | Meaning of result labels |
| Report schema (`src/reporting.py`) | `2.1` | `2.0` | Machine-readable report contract |
| Saved review / workspace | `saved-response-review-v1` / `saved-answer-workspace-v1` | Same schema names | Imported-response and resumable-workspace contracts |
| Browser execution adapter | `browser-sequential-v2` | Earlier adapter | Scheduling/recovery implementation, not model version |
| Hosting version | Sites `8` | Not determined by GitHub main | Deployment service version, separate from every identifier above |

No official v2/v3 product releases or tagged 1.0.0 release should be invented from these analytical stages. Version-label alignment is technical debt; source/evaluator/report identities must accompany consequential evidence.

### Current user journey and custody

1. **Understand and try:** the support-release landing explains the decision; one action runs 32 fictional cases and opens their summary. Three intentionally simulated execution errors demonstrate exclusion from quality averages.
2. **Prepare:** acknowledge data handling, create/reopen a project, add approved sources and expected behaviors, resolve validation/coverage issues and version the prompt.
3. **Connect or import:** a private native operator can configure a staging endpoint through fields and an explicit health check. The browser accepts saved answers or supported provider calls with an entered session key; it does not connect arbitrary assistant endpoints.
4. **Evaluate:** authorize real data flow and bounded attempts; capture actual executions separately from quality results and immutable input identities.
5. **Review:** inspect expected/observed/source evidence, severity, recommended action, uncertain findings, gates and missing calibration. Capture the release or source-review decision with honest attribution.
6. **Return:** preserve/export work, compare a compatible revision to its baseline, add confirmed incidents as regression cases and repeat at the next release. Browser work must be downloaded to survive closing/reloading or returning after 24 hours of inactivity; persistent private native projects follow their configured repository policy.

## 8. Capabilities and non-capabilities

### What the product can currently do

| Capability | Where present / delivery state | Independent engineering verification / boundary |
|---|---|---|
| Guided sample and readable decision summary | Published browser and current local app | 32-case live journey observed; synthetic-only verdict and separate execution errors verified |
| Version prompts, cases, documents, targets and manifests | Earlier foundations on main; current integration locally committed and used by published app where applicable | Storage/provenance regressions pass; manifests identify inputs, not source authenticity |
| Upload/extract/chunk and retrieve approved documents | Published browser/current local app; earlier formats on main | Local browser PDF/DOCX/PPTX indexing, duplicate recovery and retrieval observed; loader/source tests pass; no complete-layout/OCR guarantee |
| Create, edit, validate and assess dataset coverage | Current local/published app | Automated UI/schema coverage; representative coverage still requires domain judgment |
| Review supplied answers, attribute decisions, retest replacements, export/restore workspaces | Present on main and preserved in local/published integration | Hash/attribution/partial-retest/restore tests; actual local browser review persistence and fictional replacements observed; does not prove client retrieval or reviewer accuracy |
| Call supported foundation-model providers | Present on main/current local and browser transport | SDK/transport/error tests; browser route restrictions verified. No paid account/live credential acceptance established in this release |
| Call external staging assistants through a form | Current private native app; adapter foundations on main; **not arbitrary HTTP in public browser** | Network policy, request/response mapping, credentials and failure tests. A customer's endpoint still needs an authorized trial |
| Evaluate correctness constraints, citations, grounding, escalation, safety, resources and retrieval | Current evaluator v8 locally committed/published; main has v7 | Finite deterministic/regression evidence, uncertainty and scope constraints; no general semantic guarantee |
| Compare candidates, calibrate held-out judgments, gate and report | Current local/published app as applicable; earlier foundations on main | Version/case/calibration compatibility and critical precedence tested; real-domain calibration not collected |
| CLI/CI, SQLite/PostgreSQL repository contracts and role controls | Native repository code, not a managed browser service | Native suite and disposable PostgreSQL pass. Remote CI is running; PostgreSQL and container checks passed, while Python 3.11 setup required a patched inherited dependency |
| Record content-free product workflow events | Current integration; local authorized event sink | Allowlisted typed attributes, deduplication and rejection tests; no central analytics service, cross-device tracking or measured retention |

“Independent” here means checked against code/tests/runtime separately from a feature's existence. It does **not** mean a third-party security audit, independent human calibration or customer validation.

### What it cannot truthfully do

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

| Evidence category | What exists | What it does not establish / next proof |
|---|---|---|
| **Engineering** | 1,061 tests passed, zero skips including disposable PostgreSQL; 87.86% branch-enabled source coverage; Ruff/format/mypy/pip consistency passed. Copy-only sample refinement passed its focused regression; four subsequent release/sample checks passed. Four dependency-builder and nine Fetch-retry tests passed | Tests do not measure demand, human comprehension or general semantic accuracy. `app.py` is covered by UI tests but outside the `src` coverage denominator. Python 3.11 and container execution await remote CI |
| **Evaluation validity** | Constraint/citation/uncertainty/gate/comparison invariants and authored adversarial cases; human calibration machinery | No measured domain false-positive/false-negative rates or representative unseen customer benchmark; seeded failures are not customer regressions |
| **Security** | Role/session/secret/upload/destination/redaction tests, disposable PostgreSQL boundaries, separate live tabs/reset, scoped dependency review | No blanket security certification, penetration audit or managed ingress/retention assurance. Four compiled browser packages retain advisories with restricted tested paths |
| **Deployment** | Sites version 8 succeeded; live source hash matched; public root/studio and sample worked with required isolation headers; no browser runtime error logs in that check | Not a longitudinal availability, load, provider-CORS or live-account test. New GitHub push/PR/merge/CI remains pending; the initial authorization blocker is resolved |
| **Usability** | Agent-driven browser and AppTest journeys, readable no-JSON primary review, narrow-layout observations and error recovery | No independent first-time-user study, full keyboard/screen-reader audit or measured comprehension/completion/time-to-value |
| **Customer** | Evidence-informed brief, discovery plan and proposed two-release pilot | No interviews, qualified partner cohort, customer usage, retention or confirmed outcomes supplied/collected |
| **Commercial** | Sponsor/buyer hypotheses and continuation/willingness-to-pay questions | No contract, payment, conversion, pricing validation or continuation commitment established |

### Security and operating state

The supported native environment is Python **3.11 or 3.12**; local verification used **3.12.14**. The older 3.9 virtual environment was preserved, not used to weaken compatibility requirements. The browser uses **Stlite 0.76.0 / Streamlit 1.41.0 / Pyodide 0.26.4 / Python 3.12.1**, a separate dependency surface.

Native Python and wrapper npm audits reported no known findings at the recorded checks. The browser's 69-package inventory retained **44 advisory records across four packages** after compatible patches: cryptography 11, lxml 2, Pillow 29, scikit-learn 2. Records are not distinct-CVE counts or proof of reachable exploits. Eleven actual Wasm dependency-path tests passed, including entity/image/font tripwires, vectorizer cleanup and transport restrictions; Protobuf 5.29.6 pure-Python and Streamlit message round trips were verified. Those tests do not clear every vulnerable API, C dependency or interpreter issue. The [dependency review](design-partner/browser-dependency-review.md) is the authoritative scope and maintenance obligation.

Native `public-demo` is isolated and sample-only; true Wasm `browser` mode permits tab-local custom work and explicit-key supported provider calls; `local` is a trusted operator's persistent workspace; `authenticated` needs validated external identity/infrastructure. Setting a browser flag on ordinary Python does not grant browser privileges. Workspaces, exports, model calls and deletion retain distinct authorization/data-handling boundaries.

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
| Assume main, local feature and live app describe one state | Verified branch/deployment divergence; observed fact | Shipping the old baseline could remove September capabilities; audit claims could falsely accuse the newer live app | Integrate main, bind deployment to source, and maintain separate delivery rows; authorization is restored, while push/CI/merge completion still needs verification |
| Treat a build as hosted verification | Worker-header failure and subsequent fix; documented correction | Browser runtime depends on the final origin and isolation policy | Test the published source and startup; still no SLA or universal-browser claim |
| Prioritize plain-language decisions over exposed internals | Owner request plus UI audit; direct evidence, not customer study | Raw JSON/opaque versions demand implementation knowledge before value is apparent | Preserve exact backend evidence and optional engineering exports; independently test comprehension next |
| Keep unknown or unverified evidence unresolved | Constraint/source/calibration/review regressions; verified implementation | Aggressive automation can create false confidence or false accusations | Human review may take longer; conservative uncertainty is intentional and needs domain validation |
| Retain a scoped browser runtime while patching compatible dependencies | Dependency inventory, source reachability and actual Wasm tests; observed evidence | A native clean audit hides browser advisories; a wholesale upgrade is not automatically a complete fix | Document exceptions and restrict affected APIs; upgrade/rebuild or disable a path if an advisory becomes applicable |
| Do not remove CI files to evade denied GitHub permission | Actual OAuth push rejection; observed fact | Dropping controls would “finish” publication by weakening the requested release | Keep full reviewed code; require genuine GitHub account authorization before pushing/merging |

No row above invents an incident, user complaint, interview, prevented loss or customer's motivation. The plain-language request is owner feedback; it is not external customer validation.

## 11. Outstanding work and next milestone

### Delivery blockers

1. **GitHub release handoff:** the complete branch is pushed and the release PR is open. Finish remote checks after repairing Python 3.11’s inherited setuptools dependency; merge only after observed success. Authorization is restored and is no longer the blocker.
2. **Any new applicable critical integrity/security failure:** fail the release gate if verification uncovers one. The scoped compiled-dependency exceptions are visible maintenance risk, not blanket clearance. The published bounded browser beta is already live; this does not mean all enterprise gates passed.

### Highest-priority product milestone

Run a **qualified two-release design-partner pilot**, preceded by problem interviews and independent first-use tasks. An engineer and domain owner must bring approved reference material and a real staging assistant or authenticated saved-answer capture, understand one consequential finding/evidence gap, and return for their next actual revision. This tests the missing customer problem, integration, validity, comprehension and recurrence assumptions together. [H11]

Proposed learning rules are at least four of six interviewed teams showing a repeated review problem; at least four of five unassisted users completing and correctly explaining the sample; and at least three of five activated teams with a second-release opportunity returning to compare. These are small-sample decision rules, not existing conversion rates. No outreach is implied or sent by writing this plan.

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

The ICP and recurrence hypothesis, whether teams prefer saved-answer import or staging integration, who funds adoption, acceptable calibration/integration burden, browser-first versus managed-private delivery, and commercial packaging remain unresolved by customer evidence. Do not add pricing, certification, fully autonomous agents or central telemetry merely to make the product look complete.

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

Unsolicited short progress notes can remain concise. A final completion report must include this full PM evolution view alongside technical results and link this document. Classify the product as concept prototype, portfolio MVP, technical alpha, design-partner beta, production candidate, generally available, or a more accurate equivalent; explain the scope and missing evidence. Preserve the current distinction between a published bounded beta and unvalidated customer/commercial outcomes.

### Maintenance checklist

- Read the current snapshot before meaningful implementation; verify relevant Git and deployment state rather than inheriting an old label.
- Update the top delta, current state, timeline/ledger, capabilities, evidence maturity, risks and next milestone whenever product, UX, evaluation, security, architecture or readiness changes.
- Cite the exact revision and source/test/observation. Mark unavailable evidence and PM inference explicitly.
- Refresh application/evaluator/report/hosting identities separately. Keep source commits and deployed manifests traceable without secrets or private customer material.
- If a capability is removed/restricted, or a previous claim is no longer accurate, name the correction and reason.
- At handoff, inspect `git status`, remote main and deployment evidence; record only states actually achieved. Do not call a locally completed feature shipped without delivery evidence.
