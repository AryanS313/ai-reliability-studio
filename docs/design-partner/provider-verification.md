# Direct-provider transport verification

**Delivery context (16 September 2026):** the integrated bounded beta is published. The [release review](release-review.md) records exact verification and delivery results; the [living product history](../PRODUCT_EVOLUTION.md) separates deployed, branch, main and proposed work. Dated baseline/focused results below retain their original scope. Customer and commercial outcomes remain unmeasured.

Historical focused check: 16 September 2026, Python 3.12.14, before integration with the newer browser/main provider work. This verifies SDK serialization and application contracts using **offline HTTP fixtures**, not live model availability, credentials, response quality, or partner integration.

## Defects and fixes

| Defect found | Local fix | Verification |
|---|---|---|
| OpenAI 1.54.4 and Anthropic 0.39.0 default clients fail to construct with HTTPX 0.28.1 (`unexpected keyword argument 'proxies'`) | Supply explicitly configured, scoped HTTPX clients | Reproduced both default-construction failures without network; actual pinned SDKs then serialize and parse fixture requests successfully |
| SDK retries and broad/default timeouts could multiply the execution engine's retry policy and obscure call bounds | 30-second provider timeout, 10-second connect timeout, OpenAI/Anthropic SDK retries disabled; Gemini uses one scoped transport request | Timeout, 429, 500, and redirect tests assert exactly one SDK request and closed resources |
| Ambient provider base URLs, proxies, organization/project headers, Google Vertex/replay configuration, or additional auth tokens could affect destination or leak deployment metadata | Direct providers use official endpoints and explicit per-request keys; no inherited proxy/netrc or provider routing overrides | Host/path/headers/body inspected with deliberately conflicting fixture environment variables; no ambient-owner values are sent |
| Requested model name was reported as if observed, including failed and unreported responses | Preserve provider-reported model separately; absent identity remains unknown; request and pricing estimate provenance remain explicit | Actual SDK responses with and without model IDs, failure paths, and FoundationModelTarget mapping tests |
| Structured provider refusals could be discarded or treated as an empty transport response | Preserve refusal text/status, finish reasons, Gemini block/safety metadata; refusal remains a successful execution to evaluate against expected behavior | OpenAI, Anthropic, and Gemini refusal fixtures through their real SDK parsers |
| Empty answers lost observed model and usage/cost evidence | Empty non-refusal response is unscored invalid response, retaining observed metadata and usage | Empty OpenAI/Haiku and Sonnet thinking-only budget-exhaustion fixtures |
| Configured Sonnet 5 was sent non-default temperature and did not explain effective sampling/default thinking | Omit unsupported model-specific sampling parameters; record requested/effective settings and token-budget caveat; select text blocks by type | Strict request fixture rejects unsupported fields; mixed thinking/text, empty thinking-only, seed omission, and persisted manifest/provenance checks |
| Public-demo code paths could reach a real provider if credentials existed | Reject non-synthetic generation before SDK/client construction, including explicitly supplied keys | All configured fixture-provider families tested with and without supplied credentials; zero constructed clients or requests |
| A provider could echo an arbitrary runtime credential in its answer, bypassing pattern-only redaction | Compare returned data against exact known credentials and discard matches before scoring or persistence, recording a safe credential-disclosure reason | Five provider-family SDK fixtures echo a runtime key; each becomes an unscored invalid response with no key in its returned record |

Sonnet behavior was checked against the current [official migration guide](https://platform.claude.com/docs/en/models/sonnet-5/migration-guide): adaptive thinking defaults, sampling restrictions, output budget, and structured refusal handling are documented. This model-specific exception must not be inferred for unknown future models.

## Scope and commands

```bash
# From the supported environment in the checkout being verified
.venv/bin/pytest tests/test_provider_sdk_transport.py tests/test_targets_and_execution.py -q --no-cov
.venv/bin/ruff check src/llm_client.py tests/test_provider_sdk_transport.py tests/test_targets_and_execution.py
.venv/bin/ruff format --check src/llm_client.py tests/test_provider_sdk_transport.py tests/test_targets_and_execution.py
.venv/bin/mypy src/llm_client.py
git diff --check
```

Historical result: **105 focused tests passed in 1.48 seconds** (75 SDK transport cases plus 30 existing target/execution cases). Ruff and format checks and targeted mypy passed. SDK tests patch socket connections to fail, so no provider network calls can occur. Fixture model names include legacy protocol examples; their successful parsing is not an availability promise. The release review records the later combined result; this count is not the total integrated provider coverage.

Upstream `google-genai==1.0.0` Pydantic `dict()` deprecation warnings remain. The Gemini compatibility transport uses private SDK internals because that pinned SDK lacks an equivalent custom synchronous transport hook; upgrading it requires rerunning the actual-SDK serialization fixtures. This is an explicit maintenance limitation.

Direct model mode supports official provider destinations; ambient `OPENAI_BASE_URL`/`ANTHROPIC_BASE_URL`, proxy, organization, and project routing are deliberately ignored. Use the reviewed native external-assistant adapter for a custom HTTPS assistant endpoint; the browser has no arbitrary HTTP-target transport. Real provider verification still requires an owner-approved key/account and explicit call confirmation; no live provider result is claimed here.

## Integrated provider and browser evidence

The combined release preserves provider-native system instructions, a normalized role-separated trace, actual response identity, Gemini thinking-token accounting and safe Retry-After semantics alongside fixed destinations, no ambient routing, explicit credentials and fail-closed credential-echo handling. Unknown modes and a forged native browser mode cannot call providers. The actual browser uses its restricted sequential Fetch worker, not native sockets.

The integrated native SDK fixtures and browser worker checks exercise concrete request/error contracts. Eleven actual Wasm dependency-path tests additionally verified native-network/key/certificate exclusion and the single Protobuf 5.29.6 pure-Python backend with Streamlit message round trips. They made no model requests. See the [dependency review](browser-dependency-review.md) for exact versions and residual advisories, and the release review for full run results. Published sample success remains synthetic; authenticated provider acceptance, final-origin provider CORS and partner endpoint compatibility still require an approved real trial.
