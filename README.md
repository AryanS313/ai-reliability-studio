# AI Reliability Studio

[**Open the live Streamlit demo →**](https://ai-reliability-studio.streamlit.app/)

> The hosted demo uses synthetic scenarios for onboarding. Synthetic results demonstrate the workflow and are not model-quality or launch-readiness evidence.

AI Reliability Studio is a production-oriented evaluation platform for testing AI assistants against versioned datasets, source documents, prompts, models, and real target APIs. It separates model-quality evidence from infrastructure failures and will not convert a synthetic demo into a launch-readiness claim.

The platform answers a deliberately harder question than “does the chatbot look good?”:

> For this exact prompt, dataset, document snapshot, retrieval configuration, model, and target version, what evidence supports—or blocks—a controlled launch?

## Trust guarantees

- Synthetic runs are always labeled `Synthetic demonstration — not model-quality evidence` and never receive a launch verdict.
- Provider, timeout, authentication, rate-limit, and invalid-response failures are stored as execution errors and are excluded from quality averages.
- Deterministic contradictions involving negation, dates, quantities, policy exceptions, or unauthorized decisions cap the quality score and cannot be overridden by an advisory LLM judge.
- Citations earn support credit only when they resolve to retrieved evidence and support an assessed claim. A source title alone is insufficient.
- Every read, write, export, and destructive operation is workspace scoped. Production mode refuses unauthenticated single-user operation.
- Prompts, datasets, documents, targets, and run manifests are immutable/versioned inputs. Historical results remain reproducible.

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

In the UI, select **Load Sample Fintech Demo**, inspect **Target Setup**, and run the generic synthetic target. The result demonstrates the workflow only; the product deliberately blocks a readiness verdict. Use **Evaluator Calibration** to import/edit independent held-out human labels; until its configured requirements are met, real candidates remain insufficiently calibrated.

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

1. **Foundation model** — select a configured OpenAI, Google Gemini, or Anthropic model and provide its key through the environment, Streamlit secrets, or the current browser session.
2. **External API** — import a versioned configuration such as [`examples/external_target.json`](examples/external_target.json). Secret values must use `secret://NAME` references; raw credentials are rejected from persisted configuration.

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
| `category`, `severity`, `tags` | recommended | Coverage and gating dimensions |
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

- The bundled dense-retrieval default is lightweight TF-IDF; a sentence-transformer embedder can be injected when that dependency is deployed.
- Image-only PDFs require an external OCR extension. Extraction warnings are preserved instead of inventing text.
- The bundled job queue, artifact store, schedule registry, malware scanner, and OCR adapters are explicit local/unavailable foundations and are not production-ready. Durable workers and managed queue/object-storage/scheduling/scanning/OCR backends remain deployment responsibilities.
- PostgreSQL migration/RLS tests run in the optional CI service profile, but must still be repeated against the deployment’s exact managed PostgreSQL version, application role, and identity/provisioning path.

## License

MIT. See [`LICENSE`](LICENSE).
