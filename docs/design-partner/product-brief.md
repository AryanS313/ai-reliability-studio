# Product brief: a release check for knowledge support assistants

**Acceptance correction (17 September 2026):** the owner discovered and rejected the primary site's sample-only restriction and the requirement to install locally for custom work. That restriction was an agent implementation decision motivated by safety, not an approved product boundary. The requested main-site journey remains a **technical alpha with an open hosted-workflow release blocker**; a separate bounded browser beta is published. Prior merge, CI and bounded deployment checks remain facts, not proof of complete product acceptance. The [release review](release-review.md) and [living product history](../PRODUCT_EVOLUTION.md) retain their scope. Customer and commercial outcomes remain unmeasured.

Research date: 16 September 2026. Status: **evidence-informed ICP hypothesis; customer demand is not yet validated**. No interviews, design partners, retention, willingness to pay, or customer outcomes are claimed by this document.

## Decision

**Primary ICP:** a small product team, usually 2–10 people building the AI feature inside a small or medium SaaS company, that owns a customer-support or internal-support assistant grounded in written policies and knowledge articles. It has a staging HTTPS API, an engineer able to supply its request/response mapping, a domain owner able to judge correct answers, and a prompt, model, retrieval, or knowledge change due within 30 days. It currently lacks a repeatable, shared release-evaluation workflow.

Team size and the 30-day window are recruitment filters to test, not market-size findings. Prioritize read-only answers and escalation suggestions. The initial fintech examples are useful demonstrations of policy exceptions, not a reason to sell regulated decision approval.

**Product thesis:** help the engineer and product/domain owner decide what to change before the next assistant release by running a small, versioned risk dataset against their actual staging assistant, inspecting the failed cases and source evidence, and comparing the revision against a recorded baseline.

**Positioning:** “Catch policy and answer regressions before your next support-assistant release.”

**Value proposition:** turn a staging endpoint, approved source material, and expected behaviors into a reviewable release evidence packet: execution failures separated from answer failures; serious exceptions surfaced before averages; exact candidate inputs recorded; missing evidence explicit.

**Required delivery experience:** a nontechnical visitor must be able to complete the guided custom journey online on the main site: create a project, provide approved sources and cases, connect an assistant through understandable fields, authorize evaluation, inspect and export evidence, and return to compare a revision. An engineer may supply the assistant's integration details; a repository checkout, local installation or raw JSON configuration must not be required to use the product. This is an owner requirement, not a validated customer outcome. The current main site remains sample-only; the hosted correction is in progress and not yet shipped or accepted. The Cloudflare decision is paused.

**Local progress, not deployment:** the hosted candidate includes project download/resume for temporary sessions. It preserves stored source passages and versioned inputs, along with explicitly unverified historical results and decisions. Original uploaded binaries are not included; credentials and qualifying calibration do not transfer. Local sample download/restore/review/export and focused automated checks passed, as scoped in the release review. This does not yet establish the full custom journey on the main site or a customer's repeat use.

The combined local candidate has since passed **1,203 tests with zero skips** and **87.53% source coverage**, including six PostgreSQL service checks. The [hosted workflow review](hosted-workflow-review.md) records the complete verification scope and partial actual-browser custom journey. New CI, deployment, complete final-origin acceptance and customer/commercial evidence remain pending or unmeasured; these engineering counts do not validate the ICP or adoption thesis.

## Why this audience

Two primary sources support a recurring reliability problem, although neither proves demand for this product:

- The MAP study reports 20 interview case studies and a survey of practitioners behind 86 deployed systems across 26 domains. Reliability was its leading development challenge; 74% primarily used human evaluation. This favors a workflow that helps domain reviewers rather than claiming to replace them. The sample concerns deployed agents broadly, not specifically small support teams. [Measuring Agents in Production, version 4, June 2026](https://arxiv.org/abs/2512.04123v4).
- LangChain's survey page reports 1,340 responses collected in November–December 2025, published in June 2026. Customer service was the largest primary use case (26.5%); quality was the top production barrier, and offline evaluation adoption was 52.4%. The sample was self-selected, 63% technology-sector, and vendor-associated; these are directional signals, not population estimates or this product's acquisition forecasts. [State of Agent Engineering](https://www.langchain.com/state-of-agent-engineering).

The narrower choice is an inference from these signals and the repository's existing strengths: document provenance, policy contradictions, citations, escalation, candidate gates, and comparisons. A support assistant offers referenceable answers and recurrent changes that fit those strengths. An arbitrary autonomous agent would require action/trajectory and environment-outcome validation beyond this beta.

| Audience | Urgency / frequency hypothesis | Adoption friction hypothesis | Decision |
|---|---|---|---|
| Small team owning a support RAG assistant | Repeated releases can change policy answers, citations, and escalation behavior | One staging API and one domain reviewer can start; no replacement of production stack required | Primary |
| AI engineer / application developer | Must find regressions during implementation | Technically able to connect; may already prefer a code framework | Primary operator within that team, not a separate ICP |
| AI PM / technical PM | Must explain release risk and priorities | Needs engineer for integration and domain owner for labels | Primary outcome owner within that team |
| QA / model-risk function | Strong need for repeatable evidence | Enterprise access, assurance, integration, and procurement can dominate | Secondary; later managed deployment |
| Compliance / responsible-AI team | Potentially high consequence of failure | Requires broader controls and validation than an evaluation report | Reviewer only; not initial buyer |
| Agency / consultant | Repeats evaluations across client deployments | Client isolation, custody, reporting, and permissions add requirements | Secondary after isolated single-team pilots |
| Founder preparing a first AI launch | Immediate launch decision | Easy sponsorship, but recurrence may be absent | Qualify only with an actual endpoint and next release |

These rankings are hypotheses. Interview evidence should overturn them if a different group shows a more frequent problem, faster access, and stronger repeat use.

## Job, trigger, people, and trust

| Question | Product answer to validate |
|---|---|
| Job-to-be-done | “When we change our support assistant, help us find consequential regressions and explain what evidence supports a limited release, so we can fix the right cases and make the decision together.” |
| Trigger | Imminent prompt/model change, policy update, retrieval change, pilot launch, or a recently observed wrong answer |
| Cost of the problem | Repeated manual spot checks, delayed decisions, engineer/domain-reviewer investigation time, and harmful support answers; amounts must come from partner evidence |
| Operator | AI/application engineer connects the target, versions the candidate, runs and diagnoses tests |
| Outcome owner | PM, support-operations lead, or other domain owner chooses representative cases, reviews findings, and records the release decision |
| Sponsor / payer | Founder or engineering/product lead who can approve a bounded pilot; willingness and budget remain unknown |
| Required trust | Inspectable cases and source passages; immutable versions; honest calibration/coverage limits; serious failures that cannot be averaged away; visible timeouts and costs; controlled data custody |
| Return trigger | Another release or a confirmed incident becomes a new test case; compare the changed candidate with the prior reviewed baseline |

## Alternatives and the credible wedge

| Alternative | What is already available | Why a qualified team might still try this product |
|---|---|---|
| Spreadsheet, staging chat, scripts | Flexible human review using the team's domain knowledge; prevalence within our ICP is unvalidated | Hypothesis: assembling versions, evidence, and consistent comparisons manually costs more than running a focused review workflow |
| Promptfoo | HTTP request/response configuration and RAG evaluations are documented capabilities. [HTTP provider](https://www.promptfoo.dev/docs/providers/http/), [RAG evaluation](https://www.promptfoo.dev/docs/guides/evaluate-rag/) | Hypothesis: a domain reviewer benefits from a guided policy/source/escalation review; technical teams satisfied with their existing configuration should keep it |
| Langfuse / LangSmith | Datasets, offline evaluation, human/automated scoring, and comparison workflows are established alternatives. Langfuse explicitly recommends stable dataset/evaluator definitions and inspecting individual regressions. [Langfuse comparisons](https://langfuse.com/docs/evaluation/experiments/compare-experiments), [LangSmith evaluation](https://docs.langchain.com/langsmith/evaluation) | Hypothesis: some teams need a smaller release-review surface than a broader evaluation/observability platform |
| Braintrust | Experiments and structured human review already support systematic evaluation and validation of automated scores. [Evaluation](https://www.braintrust.dev/docs/evaluate), [Human review](https://www.braintrust.dev/docs/annotate/human-review) | Hypothesis: the opinionated support-assistant workflow has lower setup and interpretation effort for a specific team |
| Ragas | Documents metrics spanning context relevance, faithfulness, correctness, and agent/tool use. [Available metrics](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) | Hypothesis: a team values an integrated review packet more than assembling a workflow around metric primitives |

Versioning, HTTP support, dashboards, “RAG evals,” and human review are **not unique differentiators**. The testable wedge is less work to review policy exceptions, evidence support, escalation mistakes, and release-to-release regressions together. There is no claim that this product is more accurate, cheaper, or faster than alternatives without a measured comparison.

## Activation and repeat use

**Demo value:** a visitor loads the sample, runs synthetic cases, opens a concrete failure, and correctly explains why the demonstration says nothing about their assistant's quality.

**Real activation:** a qualified team connects its staging assistant, completes a versioned real run, and identifies one actionable finding or evidence gap with its domain owner. A passing launch verdict is not required; a correctly explained `Insufficient Evidence` result can be useful. A report view alone is only an activation proxy.

**Repeat-use loop:** review finding → fix prompt/knowledge/retrieval or expected behavior → preserve the reviewed baseline → run the new candidate on the same cases and evaluator → inspect regressions and improvements → add confirmed incidents to a versioned dataset → repeat on the next release. When datasets change, distinguish coverage changes from like-for-like improvements.

## Main workflow

1. Understand the outcome and try an isolated synthetic sample.
2. Create/select a project and acknowledge data handling before adding custom material.
3. Add approved documents and representative expected-behavior cases; resolve validation issues.
4. In private native mode, connect the staging assistant through the guided target form and check response mapping/credentials. In the browser, import saved assistant answers for source review, or explicitly connect a supported model provider; arbitrary assistant HTTP is unavailable.
5. For real generation, confirm exactly what will be sent and how many calls may run, then execute. For imported answers, preserve declared capture identity and review the supplied evidence without claiming a new target call.
6. Review execution status, major answer failures, source evidence, calibration, and missing coverage.
7. Compare a revision with its baseline and export a redacted evidence packet for the release owner.

## Non-goals and design-partner release boundary

**Required release scope:** the full hosted custom workflow above, with isolation, privacy consent, explicit credentials, bounded uploads and external calls, inspectable evidence and repeatable comparisons. Sample-only hosting plus local/private custom use does not satisfy this boundary. Safety controls must be implemented within the hosted journey rather than used to redefine the product as a demonstration.

**Currently delivered, narrower scope:** a tab-local browser beta for approved non-sensitive saved-answer review and explicit-key supported model calls; a sample-only native public site; and a trusted local/private workflow for read-only support answers. These capabilities remain useful but do not establish completion of the requested main-site product. The pilot owner supplies lawful-to-use test data, a staging endpoint and an independent reviewer. A local synthetic/reference server is a transport test, not a real customer integration or quality proof.

Out of scope: autonomous transaction/action approval, medical/credit/legal decision certification, universal agent benchmarks, replacing observability stacks, automatic fixes sent to production, continuous production monitoring promises, training models, or a generic analytics dashboard.

Enterprise requirements may remain explicit: managed identity and provisioning, validated PostgreSQL/RLS, durable jobs and storage, retention/backups, malware scanning/OCR, operational monitoring, load/recovery validation, and formal assurance. Do not accept sensitive partner data in a deployment whose applicable controls have not been verified. An evidence packet informs a human release decision; it does not certify production safety.

**Current evidence limit:** native, actual Wasm and observed published-browser checks establish their exercised behavior and bounded controls. They do not establish the missing online custom journey. Its implementation and actual hosted acceptance come before a completion claim. Independent first-time comprehension, adoption, real endpoint compatibility, evaluator adequacy in a customer's domain, recurring value and willingness to continue require design-partner participation. See [discovery plan](discovery-plan.md) and [success metrics](success-metrics.md).

## Published workflow versus the recruitment hypothesis

The primary 32-case synthetic review and the separate three-answer authored review are demonstrations, not customer quality evidence. The staging-endpoint qualification above remains the initial live-evaluation research cohort; saved-answer pilots are an additional adoption hypothesis to assess explicitly, with capture provenance and domain review recorded. Do not imply that importing answers measures the assistant's internal retrieval or independently authenticates its identity. Keep saved-review activation separate from the live-call metric denominators until the measurement contract is extended.

Browser users must download their complete workspace before closing/reloading the tab or returning after 24 hours of inactivity. That file contains original inputs and review notes and is different from a redacted report. Managed persistent team hosting, live-provider account acceptance and independent product comprehension remain separate validation work. The [living product history](../PRODUCT_EVOLUTION.md) records delivery and customer-evidence maturity without changing this ICP hypothesis into a validated market finding.
