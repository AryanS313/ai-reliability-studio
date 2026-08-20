# Implementation plan

Baseline inspected: 2026-08-20, commit `1fe6964` on branch `feature`.

## Current architecture and data flow

`app.py` owns presentation, session state, provider selection, destructive actions,
and most workflow orchestration. Documents are extracted by
`src/document_loader.py`, split by fixed word counts, indexed in an in-memory
TF-IDF store, passed to a provider or deterministic mock in `src/llm_client.py`,
scored by token overlap in `src/scoring.py`, then saved to global SQLite tables
and aggregated by `src/charts.py`.

The baseline test suite contained 17 tests. With the repository dependencies not
installed in the host interpreter, 13 passed and 4 document-format tests failed
because `beautifulsoup4`, `python-docx`, `openpyxl`, and `python-pptx` were absent.
This is an environment failure, not a behavioral test failure.

## Compatibility surface

- Preserve the FinSure onboarding demo and sample data.
- Preserve TXT/Markdown/PDF/DOCX/RTF/CSV/TSV/XLS/XLSX/JSON/JSONL/HTML/PPTX uploads.
- Preserve local SQLite and no-key demo setup.
- Preserve direct OpenAI, Gemini, and Anthropic execution.
- Preserve CSV export and legacy score/result columns while adding richer fields.
- Migrate legacy SQLite data into a default local workspace without deleting it.

## P0 — trust and isolation

1. Add typed domain objects, version hashes, structured execution states, and
   multi-label safety results.
2. Replace overlap-only scoring with constraint, negation, quantity, exception,
   claim-support, citation-support, and structured escalation checks.
3. Make mock scenarios generic and prompt-independent, label every result as
   synthetic, and forbid launch verdicts for mock runs.
4. Remove all provider-to-mock fallback behavior. Persist sanitized infrastructure
   failures separately from quality scores.
5. Replace startup schema resets and global deletes with additive migrations,
   foreign keys, workspaces, memberships, scoped repositories, and audit logs.
6. Aggregate and gate each prompt/model/target candidate independently.

## P1 — real targets and reproducibility

1. Add versioned mock, direct-foundation-model, and external HTTP target adapters.
2. Add retry/backoff, timeouts, cancellation/checkpoints, caching, concurrency,
   resume, and explicit execution statuses.
3. Add strict, versioned datasets with row-level errors, snapshots, templates,
   coverage/splits, and adversarial examples.
4. Add structural/provenance-aware extraction and chunking, hybrid retrieval,
   configurable thresholds, duplicate detection, and retrieval-only metrics.
5. Store immutable run manifests for prompts, datasets, documents, targets,
   retrieval/evaluator/model settings, environment, application version, and Git.
6. Add candidate comparisons, confidence intervals, configurable launch gates,
   regression detection, JSON/CSV/HTML reports, CLI execution, and CI.

## P2 — operational foundations

1. Add review queues, assignments, comments, human judgments, disagreement and
   reviewer-quality measurement, with audit history.
2. Add scheduler, notification, production-log-ingestion, and error-monitoring
   interfaces that can be backed by production services.
3. Add structured logs, health checks, redaction, retention/deletion controls,
   operational metrics, and drift calculations.
4. Keep infrastructure-dependent extensions explicitly unavailable until their
   backend is configured; never fabricate successful behavior.

## Assumptions and tradeoffs

- The public Streamlit deployment remains an explicit single-user/demo surface.
  Production mode requires authenticated identity headers and PostgreSQL.
- Deterministic evaluation is authoritative for hard constraints. Optional
  LLM-as-judge output is advisory and cannot overturn a deterministic
  contradiction or critical safety failure.
- The local semantic layer remains lightweight. Deployments can inject a stronger
  embedder/reranker without changing the retrieval service contract.
- Background work is implemented through an executor interface with an in-process
  implementation. A durable worker implementation is an operational deployment
  choice, not something the Streamlit demo pretends to provide.
