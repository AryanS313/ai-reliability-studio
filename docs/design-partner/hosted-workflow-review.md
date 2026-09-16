# Hosted custom workflow correction

**Evidence date: 17 September 2026. Candidate: `2026.09.17.1`, branch `codex/hosted-custom-workflow`, locally committed at `555aa08` and not yet pushed at this snapshot. Status: locally implemented with verification below; new remote CI, merge, deployment and final-origin acceptance are pending.** The primary Streamlit site's last recorded behavior is still sample-only. This document does not claim the correction is live.

See the [product history](../PRODUCT_EVOLUTION.md) for the decision record, [release review](release-review.md#14-hosted-correction--local-implementation-not-deployed-acceptance) for the preceding receipts, and [product brief](product-brief.md) for the intended user and job. All earlier measured baselines retain their dates and scope.

## Why this correction is required

The owner discovered and rejected the main site's sample-only restriction and the requirement to install locally for custom evaluation. The agent introduced that restriction to reduce safety risk; the owner did not approve the resulting scope reduction. Selecting Streamlit as the temporary primary address did not authorize removal of the custom journey. Earlier product-completion/design-partner-acceptance claims were overstated even though the recorded code, CI and bounded deployments were real.

The required experience is a complete guided journey on the main site for nontechnical visitors: prepare approved inputs, connect their assistant, authorize a bounded evaluation, inspect failures and limitations, export evidence, and return to compare a revision. Engineers may supply connection details; a local runtime or raw JSON setup must not be required. The Cloudflare decision remains paused.

## Change and acceptance matrix

| Need / priority | Previous shortfall | Local change | Acceptance still needed |
|---|---|---|---|
| Complete the core online job / P1 | Primary site offered only fictional sample evaluation | Native `hosted-session` candidate enables custom project, source/case, prompt, connection, evaluation and review flows in the guided UI | Exercise the complete custom flow on the final primary origin; local tests do not establish that deployment |
| Keep sessions and credentials separate / P0 | Enabling custom work without boundaries would reintroduce shared-state/spend risk | Isolated temporary repositories, explicit visitor credentials, no ambient owner-key fallback, per-session cleanup, consented calls and bounded usage | Final-origin simultaneous custom sessions, reset/expiry, key isolation and recovery checks |
| Connect an assistant safely / P0–P1 | Browser alternative could not call arbitrary assistant endpoints; local installation was the escape hatch | Native HTTPS connection form and explicit test request; destination validation, DNS pinning, TLS hostname checks, redirect/proxy restrictions, bounded timeout/response handling | Authorized real assistant/provider account trial; validate actual authentication, rate limits and failure handling |
| Process approved inputs online / P0–P1 | A shared server requires resource controls beyond file extension checks | Hosted document/dataset parsing in a separate credential-stripped process, size/time/output limits, one parser admission slot and visible errors | Final-host parser/startup verification; this process is not an OS sandbox or malware scanner |
| Return for another release / P2 | Temporary work disappeared without a portable live-project route | Private project download/resume carries stored source passages, versions, history and decisions; restores a new project atomically | Final-origin download → fresh session → restore → review/export/comparison; actual customer repeat use remains unmeasured |
| Avoid invented trust on import / P0 | User-controlled historical scores could look like new live evidence | Input checksums and shape validation; imported live history is offline/unverified, synthetic history stays synthetic, calibration qualification never transfers, fresh credentials required | Keep no-launch and provenance invariants enforced in all deployed reports/comparisons |
| Recover from malformed files / P1 | Invalid restored cases/request mappings could break the next screen | Validate dataset and target policy before mutation; rollback all project/assets/audit writes; serialize decode/restore and reject busy requests safely | Hosted malformed/oversized/busy recovery without loss of the current project |

## Verified local evidence

| Check | Observed result | Scope / limit |
|---|---|---|
| Complete native suite checkpoint | **1,203 passed, zero skipped**, Python **3.12.14**, **124.88 seconds**, **33 upstream SDK warnings** | Includes all six disposable PostgreSQL service checks on 16.2. This test server is not a recommended managed-production version. Log: `.local-verification/hosted-full-suite-final.log`. A later uploader-cap correction added two regressions; its 30-test hosted/guided check passed, and the complete rerun passed 1,205 tests with zero skips and unchanged 87.53% coverage in `.local-verification/hosted-release-final.log` |
| Coverage | **87.53%** branch-enabled source coverage | Whole local suite; retain the prior 87.86% result as its earlier release snapshot. Neither percentage measures customer success or evaluator accuracy |
| Static and dependency checks | Ruff passed; **119 files** passed formatting; mypy passed for **46 modules**; `pip check` and native dependency audit passed | Native environment only. The separately published Wasm bundle retains its [scoped dependency exceptions](browser-dependency-review.md) |
| Final focused security verification | **104 passed**, no blocking finding reported within those exercised boundaries | Not an independent penetration audit, blanket security certification or managed-host assurance |
| Project/storage and independent UI checks | **136** focused project/storage tests passed; separate independent project/UI run **85 passed** | These overlap the full suite and are not additional tests to add to 1,203 |
| Local sample resume | Actual AppTest 32-case sample → download → second hosted session restore → Review → readable export completed | All 32 rows, three simulated infrastructure errors and the synthetic no-launch verdict remain; no real assistant quality is proved |
| Local browser custom journey, observed so far | Privacy acknowledgment; creation of fictional **Hosted workflow verification** project; five sample documents, 30 source passages; retrieval query returned matches; 32-case dataset loaded | Custom prompt saved and connection form exercised; the separate synthetic sample showed all 32 cases, three excluded simulated failures and readable export controls. A second tab started empty with its own privacy gate. No real AI-provider execution is claimed |
| Local browser HTTPS connection test | Consented GET through the actual Connect form to GitHub's public repository API succeeded without authentication | Transport-only check against a real public HTTPS endpoint; not an AI assistant response, account acceptance or answer-quality result |

Manual file-picker limitation: the desktop Computer Use tool denied control of the Codex application. File uploads/resume were exercised through Streamlit AppTest and real parser subprocesses; native picker selection was not manually verified. No access restriction was bypassed.

The project checks caught and fixed two restore crashes: schema-invalid case rows and list-shaped request mappings. They also exposed a persistence bug that treated valid token-usage response paths as secrets. Only validated JSON-path values, including disabled empty optional paths, are exempted; arbitrary credential values remain rejected. Transaction rollback, foreign-workspace denial, configured-secret removal, synthetic identity and busy-restore recovery have regressions.

## Security, custody and operating limits

- **Native hosted custody:** inputs and explicit session credentials are processed by the Streamlit server. This is different from the browser alternative's tab-local execution. Visitors must approve source/provider data flow; there is no claim that server operators are cryptographically unable to access runtime inputs.
- **Temporary sessions:** anonymous isolated workspaces are not managed accounts, shared team projects or durable storage. Download a private project to preserve work; reset/expiry and host restarts can end the temporary workspace. Copies already downloaded are outside the session's deletion boundary.
- **Bounded use:** hosted uploads are capped at 2 MiB per document, eight files per upload, 500 dataset rows and 250,000 extracted characters. An evaluation allows at most 100 answers, two concurrent calls, one retry and a 30-second call timeout. Per-process/session admission and call limits provide bounded resource protection, not distributed abuse prevention or an availability SLA.
- **Project restore:** JSON input is capped at 20 MiB and one decode/restore at a time per process. It contains stored passages/previews and private input material, not original upload binaries. Configured credentials/references/headers and URL credential/query components are omitted; arbitrary opaque secrets pasted into ordinary content cannot be universally detected. A project file is not a redacted report.
- **Imported evidence:** checksums detect corruption, not authorship or truth. Preserve recorded evidence for inspection; require fresh execution and independently qualifying calibration before a new live release claim. Restoring a file makes no assistant request.
- **Parsing and infrastructure:** credential-stripped worker processes and bounds are resource containment, not malware scanning, OCR or a complete operating-system sandbox. Enforced scanner requirements still fail closed when no scanner is configured. Managed identity, durable workers/storage, monitoring, backups, recovery/load assurance and formal security review remain separate requirements.

## Pending receipts and missing evidence

| Gate | Current state | Receipt required |
|---|---|---|
| Complete suite after final uploader-cap correction | **1,205 passed, zero skipped; 87.53% coverage** | Python 3.12.14 including all six PostgreSQL checks, 125.90 seconds, 33 upstream SDK warnings. `.local-verification/hosted-release-final.log`; earlier 1,203-pass checkpoint retained above |
| New branch/PR/main CI and integration | **Pending for this correction** | Exact revision, check URLs/results and merge identity; September 16 CI cannot substitute |
| Primary-site deployment | **Pending** | Candidate/source identity observed on the actual Streamlit origin; do not infer it from a local build or push |
| Final-origin custom workflow | **Pending** | Fresh visitor completes preparation, connection, authorized evaluation, interpretation, export and resume/comparison; separate-session isolation and reset/recovery also pass |
| Real assistant/account acceptance | **Unvalidated** | Approved staging endpoint or supported account, scoped visitor credential, real request/response and failure recovery; fixtures are separate evidence |
| Independent comprehension and domain validity | **Unmeasured** | Unassisted tasks, reviewer teach-back and representative held-out adjudication |
| Adoption and commercial outcomes | **Unmeasured** | Qualified teams, actual next-release reuse, confirmed decisions/findings, measured investigation effort and concrete continuation/payment evidence |

**Maturity at this snapshot:** technical alpha for the requested main-site journey, with substantially stronger local engineering evidence and a separately published bounded browser beta. The immediate milestone is verified deployment of the complete hosted custom path. The next product milestone is a qualified two-release pilot; a working hosted workflow would still not establish demand, retention or willingness to pay.
