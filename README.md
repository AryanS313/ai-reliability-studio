# AI Reliability Studio

**Know what to fix before your next support-assistant release.**

A release-review product for small teams shipping assistants grounded in policies and knowledge articles. Run approved test cases against a staging assistant, inspect consequential failures and source evidence, then compare the next revision with its baseline.

[Open AI Reliability Studio](https://ai-reliability-studio.streamlit.app/) · [Product brief](docs/design-partner/product-brief.md) · [Product evolution and current state](docs/PRODUCT_EVOLUTION.md) · [Operator documentation](docs/DEPLOYMENT.md)

> **Hosted workflow correction in progress:** the previous primary deployment allowed only the sample. That restriction was an unapproved scope reduction. This branch restores custom work to the main-site journey; deployment and acceptance are tracked separately in the [release review](docs/design-partner/release-review.md). Synthetic demonstrations never establish model quality or launch readiness. A report supports a human release decision; it is not a production-safety certification.

## Use the main site

[Open AI Reliability Studio](https://ai-reliability-studio.streamlit.app/). The intended main-site journey is **try the sample**, **start your own review**, or **resume a downloaded project**, using forms, uploads and browser downloads. Visitors should not need a terminal, software installation, or a separate local workspace. The hosted correction must pass deployed acceptance before this requirement is marked complete.

The hosted beta uses a separate temporary workspace per visitor. Download your project before leaving and upload it to resume on the site; credentials must be entered again. This is not automatic cloud saving or an authenticated team account. Community Cloud may still hibernate after inactivity. A branded address and alternative hosting remain undecided; Cloudflare account creation is paused at the owner's request.

## Optional browser edition

The [browser edition](https://ai-reliability-studio.a3103.chatgpt.site/) remains available for approved tab-local custom work and saved-answer review. It is an alternative deployment, not a prerequisite for using the main-site workflow. A branded domain has not been purchased or configured.

This optional edition runs the Python application in your browser tab. Start with **Try the sample review** for 32 fictional cases. Under **Start → Review answers you already have**, choose the three-answer example or review answers exported from your own assistant. Custom work requires the data-handling acknowledgment and a saved project. Upload the question set, complete source packet and saved answers; inspect each answer, record a review, then compare replacement answers.

The saved-answer path makes no provider request. A review records its author, method, explanation and the exact answer/question/source versions. Automatic checks remain advisory. Uploaded identity, capture time and unobserved client retrieval, latency or cost are not independently verified. Restore a downloaded workspace to continue compatible reviews; changing an answer invalidates its previous review. Primary screens use forms, upload controls and readable findings; JSON is an optional file format for engineers, not a text-editing prerequisite.

**Download workspace to resume later** before closing or reloading the tab. Unexported browser work and session keys are temporary; returning after 24 hours of inactivity also clears them. Workspace downloads contain original sources, answers and notes and must stay private. Redacted reports are separate files. The browser can call supported model providers only with your entered key and explicit consent; arbitrary assistant endpoints use the main hosted site, or saved-answer import in this optional browser edition.

First startup downloads substantial runtime assets. The browser uses Stlite 0.76.0 / Streamlit 1.41.0 and Pyodide 0.26.4; its dependency bundle is distinct from the native environment. See [browser requirements and limitations](docs/browser-edition.md) and [deployment verification](docs/DEPLOYMENT.md#browser-distribution-and-hosting). The current release's final hosted checks are recorded separately from earlier runtime fixtures.

## Evaluate your own assistant

Start your own review on the site and acknowledge how your data is handled. Use approved, non-sensitive test material. The six destinations follow the release workflow:

| Step | What to do |
|---|---|
| **Start** | Try the example or start a project. |
| **Prepare** | Create/reopen a project, add source documents and expected-behavior cases, then save a prompt. Resolve validation warnings. |
| **Connect** | Save the staging assistant's endpoint, request field, response field, and session credential; explicitly authorize one connection check. |
| **Evaluate** | Review the candidate, cases, maximum attempts, retry settings and data flow; authorize real calls and run. |
| **Review** | Separate execution errors from answer failures; inspect evidence, missing calibration and next actions; record a decision and export redacted evidence. |
| **History** | Reopen prior evidence and compare a revision using compatible cases and evaluator settings. |

Evaluator calibration, retrieval testing, saved-answer review, detailed failure analysis, and workspace settings are available under **Advanced tools**. Select **Choose a tool** to close the advanced view and return to the selected primary step.

### A simple HTTPS connection: no configuration file required

Ask the assistant's engineer for a **read-only staging endpoint**. For an endpoint accepting `{"question":"When is a refund available?"}` and returning `{"answer":"Within 30 days, subject to the policy exceptions."}`, fill the Connect form as follows:

| Field | Example |
|---|---|
| Your assistant’s web address | `https://staging.example.com/answer` |
| Question field in your request | `question` |
| Answer field in the response | `$.answer` |
| Authentication | Bearer token, custom secret header, or no authentication, as agreed with its owner |
| Access token or API key | Enter the credential in the password field; it is not saved with the target |

Saving the connection makes no request. A configured health path supports **Check connection**; without one, **Send one test request** sends the displayed connectivity question only after consent. A successful check confirms connectivity/response shape, not answer quality.

Optional response mappings can expose citations, escalation, and the reported model. Citations need resolvable source or chunk provenance; naming a document is not proof that it supports an answer. Without your assistant's retrieval trace, Studio's reference-document retrieval is **not** a measurement of the assistant's internal retriever. An endpoint returning text only can still be inspected, but missing citation, retrieval, cost, or identity evidence stays missing.

For nested request formats or tool-call/usage mappings, your engineer can prepare the [external target example](examples/external_target.json). Import it under **Connection settings from your engineer**, review the form, then save the connection. Imported settings remain a draft until saved; credentials still belong in the session-only password field. Endpoints are subject to destination/header/size safeguards. Action-taking agents are outside this beta's supported scope.

Alternatively, choose **A model with my documents** in Connect. Enter your provider key in the password field to call the selected provider with Studio's retrieved context. Hosted visitors never inherit the site's owner credentials. This tests that model/prompt setup, not an existing application's own retrieval. Direct-provider adapters use official provider endpoints and ignore ambient base-URL/proxy routing. Never paste credentials into a prompt, dataset, or saved configuration.

## What makes the evidence reviewable

- Synthetic runs remain labeled and cannot receive a launch verdict.
- Failed target calls receive no quality score and remain visible in execution-error gates. A missing key or outage never falls back to a synthetic answer.
- Deterministic contradictions and critical safety failures override averages. Credential echoes are discarded and recorded as critical privacy evidence.
- Each candidate retains versioned prompts, cases, sources, target, retrieval, evaluator and gate configuration. Requested model settings are separate from provider-reported identity and effective sampling.
- Readiness requires applicable held-out human calibration for every required label. A small, incomplete, or unrepresentative dataset is not repaired by a high average score.
- Comparisons become inconclusive when versions/case sets are incompatible. A missing or failed candidate case cannot masquerade as a fixed regression.
- JSON, CSV and HTML reports redact detected personal data and secrets. Review exports before sharing: automated redaction cannot identify every confidential detail.

The primary review explains each release check, finding and comparison in plain language. Exact versions are saved automatically. **Export evidence → Download readable report** creates a report for team review; optional machine-readable files are under **Evidence files for your engineer**.

Quality dimensions include correctness, reference retrieval, citation support, groundedness, escalation, safety, latency and cost. Deterministic text scoring has semantic limits; inspect uncertain and severe cases with a domain owner. See the [evaluation methodology](docs/EVALUATION_METHODOLOGY.md).

## Bring representative cases

Use the question editor or downloadable template in **Prepare → Cases**. The editor presents ordinary question, answer, source, topic, impact and human-handoff fields; stable identifiers and advanced imported rules are preserved automatically. CSV, TSV, Excel, JSON and JSONL are supported, with row-level validation. Two import schemas are accepted:

- **Legacy:** `question`, `expected_answer`, `expected_source`, `category`, `should_escalate`.
- **Versioned:** `case_id`, `question`, `category`, `expected_behavior`, `severity`, `tags`, plus the reference answers and escalation expectations required for that behavior.

Additional fields support multiple acceptable answers/sources, prohibited answers, exact passages, rubrics, coverage rationale and held-out splits. See [versioned examples](examples/evaluation_dataset_v1.jsonl). Preserve stable case IDs across releases, include policy exceptions and previous incidents, and keep independent held-out cases for calibration. Sample cases are fictional and do not represent your users.

## Verification and CLI

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy src
.venv/bin/pytest
.venv/bin/python -m pip check
.venv/bin/python -m pip_audit --strict
```

The [release review](docs/design-partner/release-review.md) records the final test counts, coverage, dependency checks, browser observations and remaining limitations. A normal `pytest` run without `TEST_POSTGRES_URL` skips service tests; see [service-test instructions](docs/DEPLOYMENT.md#verification-and-ci). Local checks do not establish live-account connectivity, partner adoption, or enterprise infrastructure readiness.

For a synthetic CLI gate:

```bash
mkdir -p .local-verification
APP_ACCESS_MODE=local .venv/bin/python -m src.cli run \
  --dataset examples/evaluation_dataset_v1.jsonl \
  --document data/sample_docs/refund_policy.md \
  --prompt prompts/current_prompt_sample.md \
  --model mock-model \
  --gate-config examples/reliability_gate.json \
  --database .local-verification/cli-example.sqlite3 \
  --output .local-verification/report.json
```

A synthetic report intentionally exits **2** because it cannot pass a real launch gate. Exit codes are 0 for passing real gates, 2 for gate failure or a synthetic-only run, 3 for real execution errors (before evaluating the gate outcome), and 4 for handled configuration errors. For actual assistants use `--external-target`; for a provider use `--model` and `--api-key-env NAME`. Run these only against approved staging targets with narrowly scoped secrets. The CLI writes a private local database and does not implement a hosted tenant API.

## Release boundary

| Mode | Boundary |
|---|---|
| `hosted-session` — new native default | Separate temporary workspace per visitor; custom uploads, saved-answer review, explicit visitor provider keys and public HTTPS assistant endpoints. Bounded runs and uploads; no ambient owner keys or private-network access. Download and restore projects to resume. |
| `public-demo` — optional | Explicitly restricted sample-only installation; it is not the requested main-site product. |
| `browser` | Accepted only in the actual WebAssembly browser runtime; tab-local memory, approved custom inputs/saved reviews and visitor-supplied provider keys; no arbitrary assistant HTTP endpoints. Setting this value in native Python does not enable it. |
| `local` | Persistent SQLite on a trusted computer, loopback binding, one trusted operator, approved inputs and credentials. |
| `authenticated` | Shared hosting requires validated identity proxy/provisioning, managed PostgreSQL/RLS, secure ingress/egress and operational controls. Configuration alone does not establish readiness. |

The bundled queue, artifact store, schedule registry, malware scanner and OCR adapters are local/unavailable foundations. Durable workers, managed identity/database/storage, scanning, retention enforcement, monitoring, backups and recovery need deployment-specific implementation and validation. Image-only documents need an OCR extension; warnings are preserved rather than invented text. Public memory can be retained by process/OS mechanisms and must not be treated as confidential storage.

Product events stay in the authorized workspace audit log with fixed choices, counts and durations; there is no external analytics collector. Event payloads exclude prompts, document text, answers, credentials and personal/contact fields. The audit envelope retains authorization metadata and is not claimed to be anonymous. See [security review](docs/design-partner/security-review.md), [architecture](docs/ARCHITECTURE.md), and the [36-metric success framework](docs/design-partner/success-metrics.md).

## License

MIT. See [LICENSE](LICENSE).
