# Core workflow baseline and verification

**Delivery context (16 September 2026):** the integrated bounded beta is published. The [release review](release-review.md) records exact verification and delivery results; the [living product history](../PRODUCT_EVOLUTION.md) separates deployed, branch, main and proposed work. Dated baseline/focused results below retain their original scope. Customer and commercial outcomes remain unmeasured.

Baseline inspection: 2026-09-16, commit `d2fb73e`, before the core fixes described below. The branch was initially clean. This is an engineering audit, not customer research or measured adoption. The release review records subsequent integrated and published-browser observations; this baseline table is historical.

## Observed baseline

| Workflow | Existing capability and evidence | Friction or integrity gap |
|---|---|---|
| First visit / sample | `app.py` overview and `load_demo`, five bundled policy documents, sample cases, deterministic mock target; UI smoke and integration tests | Thirteen destinations and hidden setup order; synthetic fixture answers do not evaluate prompt quality. Parent owns guided journey and UI testing. |
| Custom project | Project form and workspace repository association | Assets/run APIs permit missing project; parent/security audit owns prerequisite enforcement. |
| Upload / extraction | `document_loader`, `security.validate_upload`, chunking; document loader/retrieval tests | Unsupported/duplicate/empty/malformed/oversized handling needs visible UI feedback; OCR and malware scanning are explicitly adapter limitations. |
| Retrieval | Hybrid retriever, source/passages, metadata filters and per-case metrics; retrieval tests | Lexical fallback must remain visible; retrieval relevance is not answer correctness. |
| Prompt editing | Immutable prompt versions, comparison run candidates | Synthetic scenarios ignore prompt text; no synthetic prompt winner is supportable. |
| Dataset | CSV/JSON/JSONL parsing, strict booleans, case IDs, schema validation and risk coverage; dataset tests | Coverage and held-out declarations are self-reported evidence, not proof of representativeness. |
| Synthetic run | Deterministic answers and failure fixtures; independent synthetic verdict | Workflow demonstration only; report keeps launch blocked. |
| Direct provider | Provider selection, secret resolver, safe error classification; mocked provider integration tests | Real authenticated call requires account/credential; no paid API calls performed by this audit. |
| External assistant | HTTPS endpoint, JSON templates/mappings, health check, bounded responses and classified HTTP failures; adapter tests | At baseline, setup required low-level JSON; the integrated native app now provides a simple form. Real assistant endpoint/credential remains an external validation dependency. |
| Calibration | Held-out metrics and immutable thresholds; calibration tests | **P0 trust gap:** a qualifying single-label calibration was attached as though every evaluator was calibrated; evaluator version was not checked. |
| Run interpretation | Candidate-specific gates, deterministic critical labels, separate infrastructure failures | **P1:** sample-size gate counted failed attempts; critical failure verdict could be hidden by missing calibration; unknown cost could pass budget gate as zero. |
| Failure analysis | Evidence, citations, reason codes, next-action suggestions, uncertainty and human-review warnings | Explanations are heuristic diagnoses; independent expert confirmation remains necessary. |
| Baseline comparison | Metric deltas, failure changes, gates, infrastructure and versions | **P1:** no ranking guard for changed datasets/evaluators, synthetic fixtures, absent versions, multiple candidates, or incomplete case sets. Failed cases could look resolved merely by disappearing. |
| Run provenance / retries | Engine holds attempts, cache key and timestamps; immutable manifest contains versions | **P1:** evaluator omitted these from result rows; retry counts, export provenance and meaningful comparison lost them. Storage also hardcoded one attempt; security/storage owner notified. |
| Export | JSON/CSV/HTML, secret/PII redaction, spreadsheet formula escaping, row limits | **P1 privacy:** HTML candidate names escaped markup but did not redact PII/secrets. |
| Authorization / destructive controls | Repository workspace roles, scoped reads/writes, audit log; storage/auth tests | Parent/security audit owns public-session isolation, explicit consent and destructive-action UI. |

## Measurement limits

No instrumented user baseline exists. Time-to-first-value, completion rate, comprehension and error recovery must be reported as unmeasured until a consented target user performs the workflow. Automated execution times and an engineer's click count are usability proxies only. Source inspection cannot establish first-time comprehension, keyboard usability, contrast, responsiveness or a successful real-credential integration.

## Verification log

The entries below retain the sequence and focused results of the pre-integration audit; later full-suite and delivery evidence is maintained in the release review.

### Historical local core changes — before integration

The local `feature` baseline differs materially from the live application's newer history. Read-only inspection of local `origin/main` at `f113ce1` found already-solved evaluator issues. This work selectively reuses the repository's reviewed `deterministic-v7` scoring implementation and four regression modules, plus a compatible citation support-state field. No merge or remote mutation occurred during that bounded core subtask. The newer saved-response workflow was outside that subtask, then preserved in the subsequent integrated and published release.

| Material fix | Acceptance evidence |
|---|---|
| Constraint-preserving scoring, exact citations and uncertainty | Reused independent constraint, citation-uncertainty, scoped-exemption and resource-threshold suites; actor swaps, omitted clauses, changed relations, wrong citation provenance, unfamiliar paraphrases, abstentions and zero limits are explicit cases. |
| Calibration scope/version integrity | Tests prove unversioned observations cannot qualify; one label cannot qualify all launch labels; full version-bound evidence can qualify; changed/stale evidence rejects; historical objects remain unmodified. |
| Gate denominator/critical precedence | Failed calls cannot fill the sample minimum; incomplete evidence cannot hide a critical failure; repeated executions do not inflate confidence sample; missing quality measurements block. |
| Unknown cost/latency and retry billing | Missing, negative and nonfinite observations fail resource gates; failed-call costs are included; retry total cost remains unknown because earlier attempts may be billable. |
| Comparable release evidence | Dataset/evaluator/threshold/configuration changes, absent versions, synthetic evidence and incomplete cases yield `inconclusive`; a failed candidate call cannot appear as a resolved quality failure. Both comparison surfaces share this rule. |
| Durable run evidence | Runtime results and persisted metadata carry run, dataset, KB, scoring/retrieval configuration, response identity, retry/cache and execution provenance. Integration tests rehydrate stored rows and verify redacted exports retain hashes and retry counts. |
| Report redaction | JSON/CSV/HTML tests include PII and secret references in candidate names, metadata keys and answer values; all report surfaces redact these. |
| Actionable interpretation | `Needs Review` asks a domain reviewer to verify exact passages; suggestions use the actual failure class instead of recommending more retrieval for every failure. |

### Verification outcomes

- Supported baseline: Python **3.12.14**, focused pre-change aggregation/calibration/integration suite **16 passed**.
- Post-change core, regression, integration, report and interpretation suite: **196 passed in 2.67s**; a subsequent missing-quality-measurement safeguard passed the **19-test aggregation suite**. The parent verification report records the final integrated full-suite result.
- Focused mypy: **9 source modules passed**. Focused Ruff lint and formatting passed; `git diff --check` passed. A transient TLS typing error in another agent's target work was reported and corrected by its owner.
- Real foundation-provider calls and a real customer endpoint were **not tested with credentials**. Provider and external-target behavior use offline adapter/SDK contract fixtures; no claim of live integration certification is made.
- Browser, accessibility, responsive layout, clean-session journey timing, PostgreSQL service execution and final complete coverage/dependency results belong to the parent integration verification. Source/test evidence alone cannot establish first-time comprehension.

### Outstanding design-partner validation

1. Independently review representative customer cases and calibrate every launch label for the exact evaluator/threshold version; repository fixtures are not customer calibration.
2. Connect one actual permitted HTTPS assistant with its credential locally; confirm response shape, citation provenance, timeout behavior and observed identity.
3. Run an unchanged baseline and a changed release on the same dataset/scoring configuration; examine critical and uncertain cases and record a human decision.
4. Measure real time-to-trustworthy-result and the operator's ability to explain the decision; no activation, adoption or retention claim is inferred from automated tests.

### Sample and final integrity follow-up

The first v7 sample rerun exposed 29 flagged answers and 3 execution errors. Diagnosis found valid structured citations failing because native chunks store `filename`/`document_hash`, plus a false contradiction between an assistant authority limit and a human-review requirement. Both received focused regressions and evaluator version `deterministic-v8`. Nine deterministic-success references now quote the actual bundled policy clauses; all 32 cases remain, including deliberate unsafe responses, citation failure, uncertainty and three execution failures. This fixture repair is explicitly synthetic, not evidence of improved model performance. Expected answers, behavior, sources and escalation expectations now survive result persistence.

Withheld runtime-credential echoes are recorded as critical privacy evidence without assigning quality scores. Even one such response below the ordinary execution-error-rate threshold blocks the candidate. HTTP client errors 400/401/403/404/422 no longer retry blindly; 408/429/500/503 retain bounded retry coverage. An all-failed comparison returns a recovery message without requiring absent quality columns.

### Final bounded-subtask verification

Final core/interpretation/calibration/scoring/report/execution-recovery suite: **212 passed in 3.48s** on Python 3.12.14. Ruff lint and format checks passed for 10 touched source modules; mypy passed for the same 10. Fresh sample: **32 logical executions, 29 quality-scored, 10 passes, 19 flagged answers (12 Needs Review, 3 Expected Answer Mismatch, 2 Unsupported Claim, 1 Citation Failure, 1 Privacy Violation), and 3 infrastructure errors**. Its verdict remains **Synthetic demonstration — no launch verdict**. All 32 retain expected behavior; only the 3 intentional infrastructure fixtures omit reference answers. Integrated full-suite/coverage/browser results are in the release review; this 212-test result remains a historical focused count.

## Integrated runtime preservation

The published integration preserves main's explicit saved-answer reviews, replacement comparisons, compatible restoration, source order/values/spans and extraction notices. Provider-native instructions, actual attempts/cache identity, bounded Retry-After handling and missing Gemini billing evidence remain distinct from requested configuration. The 32-case primary sample and three-answer authored review are separate fixtures. True Wasm browser mode supports saved imports and explicit-key provider calls; external assistant endpoints require trusted native mode. None of these engineering checks establish real account acceptance, independent comprehension or customer retention.
