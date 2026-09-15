# Design-partner security review

**Delivery context (16 September 2026):** the integrated bounded beta is published. The [release review](release-review.md) records exact verification and delivery results; the [living product history](../PRODUCT_EVOLUTION.md) separates deployed, branch, main and proposed work. Dated baseline/focused results below retain their original scope. Customer and commercial outcomes remain unmeasured.

## Baseline recorded before security changes (16 September 2026)

Inspection of the older `d2fb73e` local baseline confirmed the following default-configuration risks. These are historical source findings, not an observed incident or a description of the newer browser deployment already present at inspection.

| Finding | Evidence | Priority |
|---|---|---|
| The baseline default would resolve anonymous requests to the same persistent SQLite workspace. | `app.init_state` → `database.current_context` → `repository.local_context`; default `AUTH_MODE=single-user`. | Release blocker |
| Authenticated workspace context was process-global and reused by calls without request headers. | `database._active_context`, called by database facade functions. | Release blocker |
| Public sessions could consume shared deployment API keys. | `app.effective_api_key` falls back to Streamlit secrets and environment. | Release blocker |
| Privacy acknowledgement was initialized but not enforced; custom assets/runs could have no project. | `app.init_state`; repository write paths used `allow_none=True`. | High |
| Health checks bypassed DNS safety and redirect validation. | `ExternalHTTPTarget.health_check`, unlike `execute`. | High |
| External header secrets could slip through heuristic detection; malformed mappings failed at execution. | `ExternalTargetConfig.__post_init__` validates values heuristically only. | High |
| Report metadata and candidate names bypassed report redaction. | `reporting.json_report`/`html_report` redact execution records only. | High |
| Repository authorization ignored disabled users; PostgreSQL admins could create owner memberships. | Both `authorize` methods queried memberships only; PostgreSQL `add_member` lacks owner check. | High |

Working protections found: workspace checks for repository reads/writes/exports, explicit destructive confirmation in UI/facade, revoked-membership checks, sanitized filenames and upload limits, archive expansion limits, fail-closed required malware scanner, secret references in target versions, no provider-failure fallback to synthetic output, infrastructure failures excluded from quality scoring, synthetic provenance, contradiction gates, and export escaping.

## Verification and release boundary

The focused records below describe the security implementation phase. The integrated beta is now published with observed live sample isolation/reset. Current build, test, branch and remote-check status is maintained in the release review and product history rather than duplicated here. No managed identity/infrastructure readiness follows from publication.

## Implemented controls and verification

| Baseline issue | Local change | Verification |
|---|---|---|
| Shared anonymous database / cached request identity | Default `APP_ACCESS_MODE=public-demo` binds a dedicated in-memory SQLite repository to every Streamlit session; `ContextVar` binds context per rerun. Persistent local access is explicit; authenticated mode rejects single-user auth. Failed auth discards earlier context. A changed proxy identity clears UI memory and requires a clean session. | Two sessions, interleaved threads, failed reauthentication, identity transitions, no persistent database creation, and cross-workspace read/write/export/reset tests. |
| Public credential use / network calls | Public demo accepts sample synthetic execution only. External execution and health-check adapters refuse before DNS/secret resolution. Provider transport has an equivalent guard. UI hides custom uploads, credentials, external setup, and custom execution until a private mode is selected. | `test_target_security.py` and provider transport/public UI regressions. |
| Health-check bypass / DNS rebinding | Health checks validate destinations, forbid redirects, and use standard root-relative path semantics. Actual HTTP transport pins a validated IP while retaining original TLS hostname verification and sends no requests through inherited proxies. Private/reserved/multicast/CGNAT destinations are blocked, except explicit local loopback development or operator-approved private networking. | Fake-network tests prove selected IP, original Host, no inherited proxy use, closed responses, DNS-blocked health checks, no socket to private hosts, unsafe URL/header inputs, and production redirect checks. |
| Incomplete credential validation | Raw credentials in known secret headers, request bodies, or endpoint query parameters are rejected; secret header values resolve only from supplied values by default. An environment-secret allowlist must be explicit in trusted code. Header controls reject injection and transport-header overrides. | 22 malformed/sensitive config cases; short API key/auth/cookie strings; arbitrary environment variable extraction rejected. |
| Token counts mistaken for secrets | Exact usage/configuration fields (`input_tokens`, `output_tokens`, `max_tokens`, etc.) retain their values. Credential fields remain redacted. This fixes valid provider target persistence and external usage mappings. | Foundation configuration and external mapping storage regression tests. |
| Disabled users / owner-role escalation | Every repository authorization checks disabled state. Both backends use actual stored role, preventing an admin with a forged owner context from granting owner or changing existing owners. | SQLite tests plus real PostgreSQL owner/escalation/disabled-user regression. |
| Duplicate result persistence / false completion totals | SQLite serializes result insertion in a transaction; PostgreSQL locks the run row. Retrying the same run/case/prompt/target returns the original result without duplicating scores/results or incrementing completion counts. Actual attempts and provider identity are persisted. | Eight concurrent writes produce one result/score and one completed execution, verified on both backends. |
| Project switch mixes assets | A scoped restoration method loads only the selected project's latest dataset and external target. Document retrieval already selected the latest document version; a new regression preserves old versions while proving retrieval returns only the current one. | Cross-project/cross-workspace restoration tests plus actual PostgreSQL restoration test. |
| Synthetic citation provenance mismatch | Synthetic success scenarios now derive citations after selecting the correct reference evidence chunk. | Existing synthetic expected-source test and revised scoring regressions. |
| Export summary bypass | Reporting owner expanded redaction to metadata, summary values, and candidate names/keys, preserving safe counts and evidence limitations. | Reporting/integrity suite; see final verification report. |
| Destructive PostgreSQL test fixture | Tests refuse schema reset unless `TEST_POSTGRES_ALLOW_RESET=true`; local CI declares it only for its disposable service. | Local disposable service execution and fixture guard. |

### Historical focused runs — before final integration

- Supported runtime: Python 3.12.14.
- Combined existing security, session, target, auth, integration focused suite: **82 passed** before final identity/document/health-path additions.
- Final dedicated session/target security suite: **40 passed**.
- Focused Ruff and mypy: passed for `database.py`, `security.py`, `storage.py`, and `targets.py` (repeat in full suite after integration).
- Actual PostgreSQL: **5 passed**, including the original four previously skipped service tests, on a disposable PostgreSQL 16.2 server available from the native `pgserver` test wheel. UTF-8 database, private Unix socket, no TCP listener, temporary cluster removed, server stopped. The first harness run exposed its SQL_ASCII default, corrected to UTF-8 without weakening application checks. Tooling and log are ignored local verification artifacts; PostgreSQL 16.2 is **not** a recommended deployment version.
- Full application lint, test coverage, browser verification and dependency results are recorded by the coordinating task after all changes are integrated.

## Explicit release boundary

**Native public demo:** anonymous, sample-only, per-session in-memory state. No shared workspace, user uploads, real provider credentials or external endpoints. State does not survive a new session/process restart. The operating system may retain process memory or swap; this is not an encrypted confidential-data environment. This stricter boundary intentionally prevents untrusted uploads and arbitrary paid calls on public infrastructure.

**Trusted local design-partner mode:** explicit local mode, bind Streamlit to `127.0.0.1`, trusted operator, persistent local SQLite, owner-provided credentials, approved non-sensitive or appropriately governed datasets. Network health and real assistant response mapping can be verified against a private assistant. API tests cover credentials/errors without exposing credentials; a real provider/assistant integration still requires the partner's endpoint and credential. Rule-based redaction is a protection, not a guarantee that all personal or proprietary data is detected; review exports before sharing.

**Published browser mode:** accepted only in actual WebAssembly, with tab-local in-memory state, approved custom uploads/saved reviews and visitor-entered provider keys. Arbitrary external assistant HTTP is unavailable. No host key fallback is permitted. Closing/reloading the tab or returning after the 24-hour inactivity limit clears unexported work. Downloaded workspaces retain original private content; report redaction and reset do not erase earlier downloads. Native processes cannot obtain this boundary by setting a browser flag.

**Shared authenticated hosting:** trusted proxy that strips spoofable auth headers, blocks direct ingress, issues fresh identities, and provisions memberships; current supported managed PostgreSQL, egress controls, TLS, external-host allowlist, secret manager, logging/monitoring, backups and restore drills, durable workers and storage, malware scanning and parser isolation, and retention enforcement. These need operator infrastructure validation. The local service tests demonstrate application queries and row-level security behavior, not an operational production certification.

**Live service:** the integrated browser beta is published; its sample, independent simultaneous tabs and session reset were observed at the published origin. Custom import/review paths were exercised in the same build locally. These finite checks do not certify every hosted path, real-provider CORS/account access or sustained operation. The original local baseline findings remain distinct from any claim of a live incident.

**Dependency scope:** native and wrapper audits passed at their recorded checks, but the reconstructed browser inventory retains advisory entries in four compiled packages. The [browser dependency review](browser-dependency-review.md) documents patched pure-Python versions, residual scope and eleven actual Wasm reachability tests; this is not a clean browser vulnerability scan.

Final review also added known-credential echo protection: external parsed response keys and values are checked against resolved runtime credentials (including the token without a Bearer prefix). A match discards the response as an invalid execution and never passes redacted content through as valid quality evidence. Dedicated final session/target checks reached **41 cases** after this addition and URL/corpus/identity follow-ups; final integrated counts belong in the release verification report.

### Final independent UI review

A final pass found that `custom_access` accepted a minimum-role parameter without enforcing it. Repository writes were protected, but a reviewer could reach a saved assistant's connection-test control. The guard now compares persisted role rank before rendering any editor control. Read-only users can reopen scoped projects after the privacy acknowledgement, so the correction does not strand them without access to existing evidence. Five AppTests cover reviewer/viewer connection/run/sample/delete denial, reviewer calibration access, and privacy-gated read-only reopening. Non-loopback private IP literals are also rejected at configuration time without waiting for a network attempt; operator-approved private networks and local loopback development retain their documented behavior. The combined focused UI/target regression set passed **80 tests** after these fixes. The final full-suite report supersedes intermediate counts.
