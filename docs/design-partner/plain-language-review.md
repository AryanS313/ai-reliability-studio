# Plain-language interface review

**Delivery context (16 September 2026):** the integrated bounded beta is published. The [release review](release-review.md) records exact verification and delivery results; the [living product history](../PRODUCT_EVOLUTION.md) separates deployed, branch, main and proposed work. Dated baseline/focused results below retain their original scope. Customer and commercial outcomes remain unmeasured.

## Purpose and evidence

Audit date: 16 September 2026. Scope: the sample and custom workflows in `app.py`, plus `src/presentation.py` and `src/charts.py`. This is an implementation brief and acceptance checklist, not a claim that customer comprehension has been validated. Line references describe the source inspected before this interface revision; use the named render function when subsequent edits move them. Final implementation and verification results belong in [release review](release-review.md).

At the pre-revision audit, the decision summary was a useful starting point: it separates unusable calls from flagged answers, preserves synthetic limitations, and presents expected behavior beside the observed answer. The remaining problem at that snapshot was direct exposure of internal data structures. Hiding a JSON object in an expander still asks the user to interpret a data structure. The interface should answer a practical question in ordinary words; downloadable technical evidence can preserve the complete machine-readable record.

**Design rule:** first explain what happened, why it matters, and what to do. Show a meaningful number with its unit and evidence limits when helpful. Retain exact evidence and internal identifiers in storage and technical exports without making users decode them to operate the product.

No new capability is required merely to simplify these displays. Keep the existing access boundaries, consent, validation, evidence accounting, immutable provenance, and conservative verdicts.

## Historical findings and proposed changes

| Priority | Surface and source location at audit | Current friction | Required replacement and acceptance |
|---|---|---|---|
| P0 | `render_results_dashboard`, `app.py:1482–1506`; `_threshold_gate`, `aggregation.py:672` | The review displays raw gate dictionaries, metrics/counts/candidate JSON, and explanations such as `0.6210 must be >= 0.8000`. | A release-check table/card with **Check · Result · Observed · Required · Why it matters / next action**. Express scores, rates, counts, times and money correctly. Distinguish **Not met** from **Not enough evidence**. Preserve every failed check and access to supporting cases. No JSON object is rendered. |
| P0 | `render_eval_dataset`, `app.py:799`; `normalize_dataset_frame`, `datasets.py:171` | The entire normalized dataset is a generic editor. Direct inspection confirmed 32 sample rows, 29 columns, and nine list/dictionary fields. | A small, labeled case table plus a selected-case form. Core fields are question, expected answer, source, topic, severity and expected human handoff. Lists use one-item-per-line inputs or multi-select controls. Preserve advanced fields by stable case identity on save. No nested object/array cells and no silent loss of case semantics. |
| P0 | `failure_presentation`, `presentation.py:75–131,152–185`; `render_failure_analysis`, `app.py:1675–1721` | Failure names are CamelCase; “Why” starts with labels/reason codes; raw evaluator output and technical metadata render as JSON. | Translate findings into meaningful sentences and distinguish a suspected issue from a demonstrated contradiction. Keep expected/observed behavior and the exact source passage. Show evaluator limitations beside the finding. Full technical detail remains a redacted download, not a raw UI block. |
| P0 | `render_run_history`, `app.py:1861–1869` | “Dataset and immutable version differences” shows hashes and arrays of versions. | **What changed between these evaluations?** Rows for cases, instructions, assistant/model, source documents, scoring rules and review evidence. States are **Same · Changed · Not recorded · Mixed**. Explain which differences prevent a fair comparison and how to fix them. Do not hide incompatibility while removing identifiers. |
| P1 | `render_eval_dataset`, `app.py:751–803` | Coverage JSON, raw schema column names, `field/code/message` errors, and a schema template containing JSON arrays. | Show covered/missing risk topics with counts, then row-specific repair instructions using visible field labels. A simple authoring template must not require JSON syntax; advanced import formats remain supported. Missing coverage is a test-set limitation, not proof of assistant failure. |
| P1 | `render_evaluator_calibration`, `app.py:810–955` | Evaluator/version hashes, raw label enums, JSON-array instructions, precision/recall jargon, confusion-matrix fields and metadata JSON. | Name the task **Check automated findings against human reviews**. Explain that independent cases must not have been used to tune the assistant/evaluator. Friendly finding labels and split choices; list inputs without JSON syntax. Per finding: reviewed cases, real problems found, false alarms, missed problems, and evidence sufficiency. Add precise definitions when exposing precision/recall. No hash or dictionary is needed in the UI. |
| P1 | `render_failure_analysis`, `app.py:1586–1662` | Raw error table fields (`safe_error`, `execution_status`, `target_type`), 17-column failure table, raw failure-label arrays, six simultaneous filters. | Compact problem list: question, issue, seriousness, next action. Separate connection problems with a readable cause and recovery. Only meaningful filters by default; additional filters on demand. Raw error codes remain in downloadable diagnostics. |
| P1 | `render_failure_analysis`, `app.py:1695–1715` | A prominent “Evaluator confidence: 83%” can be mistaken for the probability the finding is right; per-case scores have internal names and unformatted values. | Explain the evaluator's certainty as an automated signal with calibration status; do not call it an 83% probability of correctness. Name score dimensions in ordinary words, show units, and state that a text-based score is not a measured customer success rate. |
| P1 | `render_run_history`, `app.py:1755–1767` | Internal run ID, generated run name, raw status and target type identify runs. | Choose by project/release label, date/time, tested instructions or assistant, and a readable completion summary. Disambiguate otherwise identical choices without exposing opaque hashes. Saved backend IDs remain unchanged. |
| P1 | `render_run_history`, `app.py:1811–1859` | Raw metric/gate/new-failure/version dataframes, fractional rates, field names, and `pp` shorthand. | **What improved or worsened?** Show named measures, before/after values with units, clear direction and “percentage points” where applicable. New/resolved findings link to the question. Unknown measurements remain unknown. When comparison is inconclusive, numeric differences remain explicitly descriptive. |
| P1 | `render_target_setup`, `app.py:1010–1078` | Connection setup still asks for JSONPath and exposes custom request JSON, placeholders, HTTP methods and SSE terminology. | Plain form for the common question/answer contract; field names may be `question` and `answer`, with nested field notation explained if needed. For advanced contracts, use structured field mapping or an engineer-provided configuration import whose validated summary is readable. Preserve every saved advanced mapping. Hide irrelevant custom-header controls; explain streaming as “answer arrives in pieces.” |
| P1 | `render_run_evaluation`, `app.py:1211,1250–1261` | “Current Prompt vs Improved Prompt” presumes improvement; an assistant-ready message shows a hash; “Exact model identifier” leads with implementation vocabulary. | **Current instructions only / Compare current and candidate instructions**. Identify the selected assistant by its saved name and connection-check state. Provider/model selection stays accurate; present useful names without inventing model aliases or implying a check has run merely because configuration exists. |
| P1 | `render_knowledge_base`, `app.py:640–677` | Full repository document rows, chunk count, `chunk_id/chunk_index`, similarity decimals, TF-IDF/provider internals. | **Sources** inventory: document name/type, readable-text status, indexed passages, warnings. **Find relevant passages** displays source/page/section and text. Call chunks “passages.” Exact chunk IDs stay in provenance. Search score is a ranking signal, not confidence that a passage supports an answer. |
| P1 | `prompt_metric_table`, `charts.py:158–189` | Raw column names; all-unknown cost can become zero because the sum lacks a minimum valid count. Grouping by missing model can omit a candidate. | Label all columns and format units. Preserve unknown costs and missing model identity visibly; keep every candidate. A presentation change must not turn missing observations into free usage or drop unknown-model evidence. |
| P2 | Chart functions, `charts.py:90–154` | Plotly axis/hover defaults expose `prompt_name`, `overall_score`, `failure_type`, `estimated_cost`; legends repeat CamelCase findings. | Set explicit axis, legend and hover labels; translate finding/target names on a copy of the data. Name the score honestly. Count charts must separate completed-answer findings from connection failures and make denominators available. |
| P2 | `render_system_prompt`, `app.py:680–714` | “Immutable prompt versions saved”; headings still say System Prompt; candidate is stored as Improved Prompt. | **Assistant instructions** with Current/Candidate. “Instructions saved. Evaluate the candidate before using it.” Preserve stored version identities; a new friendly display name does not change historical evidence. |
| P2 | `render_run_evaluation`, `app.py:1231–1234,1267–1306,1369–1375` | `mock_scenario`, `top_k`, concurrency, transient retries, preflight/executions/checkpoints, millisecond gates. | **Example scenario**, **Passages per answer**, **Simultaneous requests**, **Extra attempts after temporary errors**, **Before you run**, **Completed X of Y checks**. Explain the maximum possible calls and cost uncertainty. Offer user-friendly seconds while converting correctly to stored milliseconds. |
| P2 | `render_results_dashboard`, `app.py:1484`; `candidate_identity`, `aggregation.py:63` | Candidate names may fall back to target enums or short version IDs when display labels collide. | Use saved assistant/instruction name with a readable run/date discriminator. Keep separate candidates separate; never collapse them to remove a duplicate label. Unknown reported model remains “Not reported.” |
| P2 | `render_results_dashboard`, `app.py:1510–1549` | “Fix the target,” “regression cases,” “workspace audit log,” and references to gate overrides are developer-oriented. | **Repair the assistant connection**, **Add cases for this problem**, and “Team decision saved with this evaluation.” Still explain that the team's decision does not erase findings or make insufficient evidence sufficient. |
| P2 | `render_settings_export`, `app.py:1886–1900`; `render_exports`, `app.py:1933–1954` | Allowlisted events, audit vocabulary, destructive-action terminology and three equally prominent file formats. | **Shareable report** first, **Spreadsheet** second, optional **Technical evidence file for engineers**. Explain local measurement in everyday terms. Keep exact deletion scope and irreversible confirmation explicit; do not soften the consequence. |
| P2 | `main`, `app.py:2009–2021`; page titles | Advanced navigation retains Knowledge Base, Evaluation Dataset, Evaluator Calibration, Failure Analysis. | Match destinations to their task: **Sources**, **Test cases**, **Check automated findings**, **Inspect findings**, **Compare instructions**, **Workspace settings**. Keep one vocabulary across navigation, page titles, buttons, help and errors. |

P0 means essential to this requested simplification and evidence integrity, not a newly discovered critical security defect. P1 removes substantial comprehension or workflow friction. P2 completes consistency across the interface.

## Case-editor contract: simplify without damaging evidence

The sample has nested `tags`, `expected_answers`, `expected_sources`, `expected_passages`, `unacceptable_answers`, `conversation_history`, `expected_tool_calls`, `variables` and `rubric`. A user-uploaded case set can contain more fields than the sample. Versioned and legacy schemas must continue to round-trip.

Recommended interaction:

1. List cases with a readable question, topic, seriousness and review status. Use a row selector or named case selector to open details.
2. Edit plain scalar fields directly. Edit acceptable answers, forbidden answers, expected sources and exact supporting passages as one entry per line, or use source selection controls when appropriate. Explain what these fields change in the check.
3. Let the user choose whether the assistant should answer, ask a follow-up, decline, or hand off only where the existing schema/scorer supports that choice. Do not invent new semantics by relabeling free-form expected behavior.
4. Provide human-handoff destination/urgency only when relevant. Explain independent-review versus development use; do not auto-mark newly created cases as held out.
5. Preserve the stable internal case identifier and every field outside the basic form. Merge edits into the original record; do not reconstruct the dataset from visible columns alone. Synchronize legacy singular and normalized plural answer/source fields deliberately.
6. For imported conversation/tool/variable/rubric structures without a supported visual editor, say which advanced settings are retained. Allow an engineer-provided file to replace those structures through the existing strict validation path. Never silently delete, flatten or stringify them into changed semantics.
7. Validate before saving a new snapshot. On an error, retain user edits and say which visible case/field needs repair. A save to one case must leave every other case unchanged; deleting a case must be explicit.

**Unacceptable shortcut:** removing list/dict columns from the generic editor and normalizing its returned frame alone. This would discard expectations, variables, conversations, rubrics, risk disclosure and comparison identity while making the screen appear cleaner.

## Release checks: useful explanation without false certainty

Every check should answer four questions:

- **What is being checked?** Use a task label, for example “Answers stay supported by the sources.”
- **What was observed?** “Support score: 71/100 across 29 usable answers.” Include the correct denominator where available. A heuristic score is not “71% of answers are correct.”
- **What is required and why?** “Configured minimum: 80/100. Inspect unsupported statements and missing source passages.” These are the team's configured acceptance rules, not a universal safety standard.
- **What can the team do next?** Name the affected cases, missing review evidence, connection repair or comparable rerun.

Use **Met**, **Not met**, **Not enough evidence**, and **Example only** as appropriate. Missing cost/latency/calibration is not zero or a passed check. Synthetic results cannot gain a real verdict through clearer wording. Do not truncate the list of blockers without a visible route to all of them.

Suggested translation examples (values are illustrative, not observed outcomes):

| Internal concept | User-facing explanation |
|---|---|
| `minimum_sample_size` | “Enough distinct cases were checked: 18 of the required 30 usable cases. Add representative cases and rerun.” |
| `maximum_execution_error_rate` | “The assistant returned usable answers for 29 of 32 calls. Three calls need a connection or provider repair.” |
| `maximum_severe_safety_failures` | “Critical safety findings: 1; allowed: 0. Inspect the flagged case before proceeding.” |
| `minimum_groundedness` | “Source-support score: 71/100; required: at least 80/100. Review statements that are unsupported or contradict the source.” |
| `minimum_citation_support` | “Citation-support score: 65/100; required: at least 80/100. Check whether each cited passage supports the statement.” |
| `minimum_escalation_accuracy` | “Human-handoff check: show the observed score and required minimum. Inspect cases that should have reached a person.” |
| qualifying calibration | “Automated findings have not yet met the required checks against independent human reviews. Complete that review before relying on a release assessment.” |
| 95% score interval | “Estimated range from the tested cases. This reflects case-sampling variation; it does not prove the evaluator is correct or cover untested users and situations.” |
| evaluator confidence | “An automated certainty signal, not a verified probability that this finding is right. Check its source evidence and human-review coverage.” |
| unknown reported model | “The assistant did not report which model answered. The configured model and observed model are separate evidence.” |

“Root cause” should become **Finding** or **Why it was flagged** unless causal attribution is actually established. For example, a citation failure proves a citation check failed; it does not alone identify whether the retriever, instructions or source document caused the problem.

## Version differences that matter to a user

The comparison display should derive friendly states from stored identities without exposing hashes:

| Evidence component | User meaning | Consequence |
|---|---|---|
| Test cases | Are the same questions and expected behaviors being checked? | Changed, missing or mixed cases make ranking inconclusive; rerun both revisions with the same cases. |
| Evaluation rules | Are both runs scored by the same evaluator and thresholds? | Changed, missing or mixed rules prevent a fair score ranking. |
| Retrieval/evaluation settings | Was the same evaluation procedure used? | Explain the relevant setting change; apply the existing compatibility decision. |
| Instructions | Which instructions were tested? | An intentional current-to-candidate change is expected; identify it without implying improvement. |
| Assistant/model | Which staging assistant or model answered? | Identify the intended revision; distinguish configured identity from reported identity and disclose unknown values. |
| Reference documents | Did source evidence change? | Explain the observed source-snapshot change. Apply existing compatibility rules; do not invent a “same evidence” claim from matching filenames. |
| Human-review evidence | Which automated findings were checked against independent reviewers? | Identify changed or missing qualifying evidence and its effect on the verdict. |

If a record has multiple identities, show **Mixed evidence** instead of selecting the first hash and calling it unchanged. If only filenames or display names match, do not infer that content matches. Internal hashes remain necessary for evidence integrity even though they are no longer displayed.

## Cross-interface language guide

| Prefer | Replace / clarify |
|---|---|
| Test cases | Evaluation dataset / eval rows |
| Sources; passages | Knowledge base; chunks |
| Assistant instructions; candidate instructions | System prompt; Improved Prompt before measured improvement |
| Assistant connection | Target / adapter |
| Checks that ran; usable answers | Executions; quality-scored executions |
| Connection or provider problems | Infrastructure errors, when explaining recovery |
| Answers needing review | Failure labels / failing rows |
| Release checks | Gates, unless briefly defined for technical documentation |
| Compare releases | Immutable version comparison |
| Time to answer; seconds | Latency, ms without units/context |
| Cost reported so far; total cost unknown | Zero cost when observations are missing |
| Problems caught; false alarms; missed problems | Precision/recall/confusion matrix without definitions |
| Saved with this evaluation | Persisted in immutable audit metadata |
| Technical evidence download | Raw JSON visible in product screens |

Plain language must not alter exact provider model identifiers in network calls, label codes in evidence, or historical version hashes. Display formatting should operate on a copy and leave the evaluation data unchanged.

## Acceptance checklist for implementation and verification

The checklist began open at audit time. Checked items below have concrete regression evidence in the integrated suite; they are engineering acceptance only. Broad visual consistency, complete accessibility and independent comprehension remain open where the evidence is incomplete. Checked items do not imply that every input or device has been tested.

### Sample journey

- [ ] A clean session can run the sample and understand what was checked, which answers need attention, which calls failed, and why it is example evidence only.
- [ ] Decision summary, detailed findings, advanced views and comparison contain no raw JSON widgets, dictionary/array cells, opaque version hashes, raw reason codes or underscore/CamelCase field labels.
- [ ] Synthetic “no launch verdict” wording remains visible on every applicable summary/comparison; changing the wording cannot promote a sample to real evidence.
- [ ] Each flagged case has a readable issue, seriousness, expected/observed behavior, supporting passage or explicit absence, next action and evidence limitation.

### Custom preparation and connection

- [x] Create/edit a case without JSON syntax. Lists and dictionaries are not edited as raw cells; uploaded advanced settings survive a basic edit unchanged.
- [x] Round-trip legacy and versioned datasets; multiple acceptable answers/sources, prohibited answers, passages, variables, rubric, conversation/tool settings, tags, splits and stable case IDs are preserved.
- [ ] Test add, edit, remove, reorder and reopen; no unrelated case changes, stale values or silent clearing of hidden fields. Validation retains unsaved edits and names the visible repair.
- [ ] Sources show readable file/passage metadata and actionable extraction warnings without internal database/hash columns.
- [ ] The normal HTTPS connection needs readable field inputs and a credential, not JSON authoring. Advanced configuration remains supported with a validated human-readable summary.
- [x] Save causes no network request; explicit check/run consent, credential secrecy, preserved mappings, retry limits and consent invalidation still pass existing tests.

### Review, calibration and repeat use

- [ ] Every release check has a meaningful label, status, actual/required value with units where available, and next action. Missing observations are never rendered as success or zero.
- [ ] Calibration uses understandable labels/inputs, preserves independent-review exclusions, and explains false alarms/missed problems. Raw identifiers are absent from the screen.
- [ ] “Confidence” is never presented as a measured probability of correctness; numerical score/interval explanations retain calibration and sample limits.
- [x] Current/candidate wording does not assert an improvement before a compatible real comparison. Unknown model identity does not remove a candidate from a chart or table.
- [ ] History identifies saved evaluations by meaningful labels and dates; explains changed/same/missing/mixed evidence without hashes.
- [ ] Incompatible/synthetic/partial comparisons remain inconclusive. Missing or failed cases never become “resolved.” New/resolved findings are understandable and inspectable.
- [ ] Plots, axes, legends, hovers, filters, tables, empty states, success messages and advanced views use the same vocabulary; technical field names do not leak through generic dataframe/chart defaults.
- [x] Shareable reports remain clear and redacted. Technical export remains available for reproducibility without appearing as the default reading experience.

### Verification and usability evidence

- [x] Automated tests exercise missing measurements, unknown model, all-error runs, critical findings, synthetic evidence, incompatible comparisons, and structured-case round trips.
- [x] Existing privacy/isolation/authorization/credential/upload/network and deletion tests remain unchanged in strength and pass.
- [ ] AppTest exercises the revised sample and custom paths; browser checks cover navigation, labels, focus and keyboard operation. Narrow layout is only marked verified when the actual viewport changed.
- [ ] At least one independent first-time target user can explain the next action and the evidence limits without verbal guidance. Until that study occurs, report comprehension as unvalidated.

## Verification boundaries

This audit used source inspection and a direct normalization check of the bundled 32-case dataset. It did not edit application code or change stored evidence. It did not run a new customer study, claim real-provider connectivity, or validate responsive behavior. The implementation owner should record revised focused tests, integrated checks and browser results in the release review rather than treating this checklist as proof of completion.

## Subsequent implementation handoff

After this audit, the implementation owner assigned chart presentation and the shareable HTML report to this reviewer. Those bounded changes are complete:

- Charts use readable axes, legend values and hover labels. Current/candidate wording does not assert improvement. Formatting copies preserve original evidence and distinguish display-name collisions.
- Unreported models remain in grouped results; missing cost remains unmeasured. Known partial costs are explicitly subtotals. Known failed-call costs remain in complete cost accounting.
- The prompt comparison table maps each verdict to its own candidate rather than depending on unrelated group ordering. Multiple saved revisions do not receive a misleading single-candidate verdict.
- The HTML report presents readable counts, candidate checks, observations, limitations, and each question's expected answer, observed answer, source passage and next action. Opaque identifiers and serialized objects do not appear as visible report content.
- Exact report-time policy and identifiers remain in escaped, non-executable metadata for machine verification. JSON/CSV technical evidence formats remain unchanged. Tests check that untrusted content cannot close the metadata script and execute markup.

Focused verification: **40 passed in 1.66 seconds** across `test_chart_evidence_display.py`, `test_html_report_display.py` and `test_cli_gate_reports.py`. Ruff and formatting passed for all five touched Python files; mypy passed for the two changed modules; `git diff --check` passed. HTML tests retain exact policy/version assertions and also verify the readable threshold and safety/calibration status. No application-screen completion or customer-comprehension claim follows from these focused checks; the implementation owner's integrated tests and browser review remain authoritative.

## Historical plain-language verification — before main integration

The root implementation subsequently completed the screen, case-editor, connection and calibration changes. That pre-integration supported-Python suite, including disposable PostgreSQL, passed **573 tests with zero skips** and **85.71% branch-enabled source coverage**. Ruff, formatting, mypy, dependency consistency and diff checks passed. The fresh browser sample was exercised again: 32 fictional executions, 19 flagged answers and 3 execution errors, with an explicit prohibition on a launch verdict. The release-check explanation now wraps as ordinary text, verified in the narrow browser panel after a table had clipped it.

AppTest covers sample/custom pages without inline JSON, actual question-editor submission and persistence, coverage/validation recovery, connection import drafts, independent-review controls and preserved hidden evidence. Original answers and passages remain original evidence; their own citation syntax is not rewritten. Optional machine-readable exports remain supported for engineers. This checklist is a traceability aid, not a claim that every customer or mobile acceptance check is complete. See the [historical plain-language release review](release-review.md#11-plain-language-follow-up--pre-integration-history) for changes, verification artifacts and remaining external validation.

## Published integration and acceptance evidence

The integrated native suite passed 1,061 tests with zero skips and 87.86% branch-enabled source coverage; later focused copy checks are recorded separately. The published browser sample reaches the 32-case readable decision summary, preserves its three intended simulated infrastructure errors and synthetic no-launch verdict, and resets without retaining the prior session. Separate live tabs were exercised. Local browser custom source uploads, duplicate recovery, retrieval, saved-answer review/replacements and consent/project prerequisites were observed. Exact delivery/CI state remains in the [release review](release-review.md) and [product history](../PRODUCT_EVOLUTION.md).

Checked-item evidence:

| Acceptance item | Concrete regression source |
|---|---|
| Plain-language case editing and preserved advanced fields | `tests/test_case_editor.py` and `tests/test_ui_case_editor.py`: scalar editor fields, legacy/versioned inputs, hidden rules, identities and actual submission/persistence |
| No call on save; explicit and plan-bound consent | `tests/test_partner_workflows.py`, `tests/test_preflight_key_status_ui.py`: no-network setup, retained mappings/keys, browser/local preflight and invalidation after changed retry limits |
| Current/candidate labels and missing model groups | `tests/test_chart_evidence_display.py`: no asserted improvement, missing model retained, distinct candidate/verdict mapping |
| Readable, redacted primary report with exact optional evidence | `tests/test_html_report_display.py`, `tests/test_cli_gate_reports.py`, privacy regressions: visible findings/limits, non-executable metadata, preserved policy and redaction |
| Adverse evidence states and safeguards retained | Integrated scoring/aggregation/comparison/session/target/storage/role suites; actual Wasm dependency tests are separately scoped in the dependency review |

Open checklist items are not automatically unresolved implementation defects: some are broader acceptance claims than a finite regression suite establishes. Independent first-time comprehension is still unmeasured. Agent-driven narrow-panel and keyboard observations do not complete a mobile, focus-order or assistive-technology audit. Original answer/source text can contain its own technical syntax; presenting that evidence verbatim is distinct from exposing internal configuration widgets.
