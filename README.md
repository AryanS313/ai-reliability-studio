# AI Reliability Studio

[**Open the live Streamlit demo →**](https://ai-reliability-studio.streamlit.app/)

> Start with **Try sample** or **Review saved answers**; neither needs an API key. Public workspaces are private to a browser session and temporary. Download your workspace before leaving. The Streamlit Community Cloud host can hibernate after inactivity; see [hosting options](docs/HOSTING_OPTIONS.md).

AI Reliability Studio helps review AI assistants against versioned questions, source documents, saved answers, and real target APIs. It keeps source evidence, returned citations/actions, review decisions, and replacement comparisons together. Automatic checks are advisory and can be wrong or uncertain; the app does not certify launch readiness.

## Evidence handling

- Synthetic runs are always labeled `Synthetic demonstration — not model-quality evidence` and never receive a launch verdict.
- Provider, timeout, authentication, rate-limit, and invalid-response failures are stored as execution errors and are excluded from quality averages.
- Detected deterministic contradictions involving negation, dates, quantities, policy exceptions, or unauthorized decisions cap the quality score and cannot be overridden by an advisory LLM judge. Undetected errors and false flags remain possible.
- Citation checks require an exact evidence match and an assessed supporting claim. A source title alone is insufficient; uncertain semantic support remains unverified.
- Every read, write, export, and destructive operation is workspace scoped. Production mode refuses unauthenticated single-user operation.
- Prompts, datasets, documents, targets, and run manifests record versioned inputs. Stored results can be inspected; a new provider call is not guaranteed to reproduce a historical answer.
- Saved answers start pending review. Decisions carry reviewer attribution and hashes of the answer, case, and source packet. AI-assisted reviews remain labeled as such. A partial retest reports only the cases actually supplied.

## Capabilities

- Three target types: deterministic synthetic scenarios, direct foundation-model providers, and versioned external HTTP APIs.
- External target templates with secret references, authentication headers, JSON response paths, citation/escalation/tool-call mappings, timeouts, rate-limit handling, and health checks.
- Structured document extraction and provenance for PDF, DOCX, PPTX, HTML, RTF, Excel, CSV/TSV, JSON/JSONL, text, and Markdown.
- Structural chunking, exact deduplication, hybrid lexical/TF-IDF retrieval, metadata filters, thresholds, and retrieval metrics (recall, precision, hit rate, MRR, nDCG).
- Strict dataset validation with row-level errors, stable case IDs, multiple acceptable answers, unacceptable answers, expected passages, rubric fields, tags, severity, and escalation destination/urgency.
- Bounded concurrent execution with retries, exponential backoff, cancellation, resumable checkpoints, caching, and idempotency keys.
- Claim-level supported/unsupported/contradicted/unverifiable assessments with document version, chunk, page/section, and text spans.
- Candidate-specific gates, bootstrap confidence intervals, baseline comparisons, regression detection, review queues, redacted production-log ingestion, drift calculations, and JSON/CSV/HTML reports.
- Reachable held-out human calibration workflow with per-label confusion matrices, precision/recall/F1/error rates, immutable threshold versions, and insufficient-evidence gating.
- Streamlit UI, non-interactive CLI, additive SQLite migrations, and PostgreSQL schema with row-level security policies.

## Quick start: local demonstration

Python 3.11 and 3.12 are the supported runtimes. Python 3.9 is intentionally unsupported because its common macOS
LibreSSL builds are incompatible with the pinned urllib3 generation. CI verifies both supported minor versions.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements-lock.txt -r requirements.txt
cp .env.example .env
streamlit run app.py
```

In the UI, select **Try sample**, inspect each answer and its source, record your review, then try the two replacement answers. The fictional sample demonstrates both a wrong time limit and an incorrectly routed action. Its results are not evidence about an actual model or customer.

Choose **Review saved answers** to upload files or paste JSON. Download starter files for the source, question, and response formats. Reports can be exported as HTML, JSON, or CSV; a workspace JSON preserves the inputs and reviews for resuming in another session. **Evaluate live assistant** guides you through sources, questions, connection, and results. Additional project tools are in the sidebar.

The app defaults to `AUTH_MODE=public-session`. For a durable, trusted local workspace only, run `AUTH_MODE=single-user streamlit run app.py`; do not expose that mode publicly. Environment variables explicitly set by the launch command take precedence over `.env`.

To run the complete development checks:

```bash
python -m pip install -r requirements-dev.txt
ruff check .
ruff format --check .
mypy src
pytest
```

## Evaluate a real target

Choose one of these paths in **Target Setup**:

1. **Foundation model** — select a configured OpenAI, Google Gemini, or Anthropic model and supply your key. Public sessions use only keys entered in that session; they never fall back to owner credentials. Trusted local/authenticated deployments can also use configured server keys.
2. **External API** — import a versioned configuration such as [`examples/external_target.json`](examples/external_target.json). Secret values must use `secret://NAME` references; raw credentials are rejected from persisted configuration. Public deployments restrict destinations to administrator-approved HTTPS hosts and reject internal network addresses.

The preflight summary shows the exact candidate count, unique cases, total external calls, concurrency, retry policy, and estimated cost where pricing is known. Real calls require explicit confirmation.

There is no provider-to-mock fallback. If a key or endpoint is unavailable, the execution is recorded as an error and is not scored.

## Dataset schema

Use CSV, TSV, XLS/XLSX, JSON, or JSONL. Legacy columns remain accepted, while the versioned schema supports richer fields:

| Field | Required | Purpose |
|---|---:|---|
| `question` | yes | User input under evaluation |
| `expected_answer` or `expected_answers` | yes for answer cases | One or more acceptable reference behaviors |
| `expected_source` or `expected_sources` | no | Expected document/source names |
| `expected_passages` | no | Exact passage/provenance expectations |
| `should_escalate` | yes | Strict boolean escalation expectation |
| `case_id` | generated if absent | Stable identity across runs |
| `category` | yes | Coverage dimension; use a meaningful category such as `citation` or `escalation` |
| `severity`, `tags`, `expected_behavior` | yes for the versioned schema | Coverage and gating dimensions; the starter files include these values |
| `unacceptable_answers` | no | Explicit prohibited outcomes |
| `rubric` | no | Required and forbidden scoring constraints |
| `escalation_destination`, `escalation_urgency` | no | Structured escalation expectations |
| `mock_scenario` | synthetic only | Generic deterministic scenario selection |

See [`examples/evaluation_dataset_v1.jsonl`](examples/evaluation_dataset_v1.jsonl) and [`examples/adversarial_templates.jsonl`](examples/adversarial_templates.jsonl).

## Scoring and launch gates

Quality scoring is multi-dimensional and explainable:

- expected-behavior correctness, including multiple references and rubrics;
- source retrieval quality independent of answer quality;
- citation presence, source validity, claim support, and completeness;
- claim-level groundedness with exact provenance;
- escalation decision, destination, reason, and urgency;
- multi-label safety failures, latency, cost, and infrastructure error rate.

Default weighting preserves the original product’s intent: correctness 30%, retrieval 20%, citation 20%, groundedness 20%, and escalation 10%. Weights and gate thresholds are configurable. Hard contradictions and critical safety failures override averages. A candidate is evaluated independently for every prompt/model/target tuple; results from one candidate never rescue another.

The verdict taxonomy is:

- `Ready for Controlled Beta`
- `Ready for Internal Testing`
- `Needs Improvement`
- `Not Ready`
- `Insufficient Evidence`
- `Synthetic demonstration — no launch verdict`

Read [`docs/EVALUATION_METHODOLOGY.md`](docs/EVALUATION_METHODOLOGY.md) before interpreting results.

## Non-interactive CI gate

```bash
python -m src.cli run \
  --dataset examples/evaluation_dataset_v1.jsonl \
  --document data/sample_docs/refund_policy.md \
  --prompt prompts/current_prompt_sample.md \
  --model mock-model \
  --gate-config examples/reliability_gate.json \
  --output report.json
```

Exit codes are `0` for passing real-target gates, `2` for a gate failure (including synthetic evidence), `3` for execution errors, and `4` for invalid configuration. Reports support JSON, CSV, and HTML.

## Storage and deployment modes

- **Local development/demo:** SQLite with additive migrations and a single local workspace.
- **Anonymous public demo:** a separate temporary SQLite database per browser session, session-only credentials, explicit deletion, and workspace downloads for resuming. This is the default UI/container mode.
- **Production:** PostgreSQL, trusted proxy/OIDC-proxy authentication, provisioned users/memberships, TLS termination, and row-level security from [`migrations/postgres.sql`](migrations/postgres.sql).

`APP_ENV=production` with `AUTH_MODE=single-user` fails closed. SQLite is not presented as multi-user production storage. See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md), [`docs/MIGRATION_GUIDE.md`](docs/MIGRATION_GUIDE.md), and [`docs/SECURITY_AND_PRIVACY.md`](docs/SECURITY_AND_PRIVACY.md).

## Architecture and operations

The Streamlit UI is an adapter over domain services rather than the source of truth. Target adapters feed the execution engine; successful responses move through retrieval/evaluation and candidate aggregation; repositories persist immutable inputs, executions, scores, reports, review actions, and audit events.

Further reading:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)
- [`docs/IMPLEMENTATION_REPORT.md`](docs/IMPLEMENTATION_REPORT.md)
- [`SECURITY.md`](SECURITY.md)
- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`CHANGELOG.md`](CHANGELOG.md)

## Known limits

- Deterministic scoring is not a validated general-purpose hallucination detector. Plausible paraphrases, exemptions, and multi-claim answers can remain uncertain or be mislabeled. Review source evidence and returned actions before confirming a finding. Human review does not make an arbitrary dataset representative of production.
- Saved-answer imports do not measure the client's retrieval, latency, or cost. Missing measurements stay unknown; declared origin and capture times are supplied by the uploader.
- Community Cloud hibernation is a hosting policy, not a setting that this repository can disable. An always-running deployment needs suitable hosting; the included Docker setup alone does not change the public host's policy.
- The bundled dense-retrieval default is lightweight TF-IDF; a sentence-transformer embedder can be injected when that dependency is deployed.
- Image-only PDFs require an external OCR extension. Extraction warnings are preserved instead of inventing text.
- The bundled job queue, artifact store, schedule registry, malware scanner, and OCR adapters are explicit local/unavailable foundations and are not production-ready. Durable workers and managed queue/object-storage/scheduling/scanning/OCR backends remain deployment responsibilities.
- PostgreSQL migration/RLS tests run in the optional CI service profile, but must still be repeated against the deployment’s exact managed PostgreSQL version, application role, and identity/provisioning path.

## License

MIT. See [`LICENSE`](LICENSE).
