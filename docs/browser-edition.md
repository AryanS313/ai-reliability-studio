# Browser edition

The browser edition runs Studio's Python application inside a browser worker using Stlite 0.76.0 and Pyodide 0.26.4. The web host serves the application and its dependencies; document parsing, saved-answer checks, explicit reviews, comparisons and report generation execute in the tab. A separate worker handles the permitted direct-provider requests. The native Python deployment remains available for its existing server-side integrations.

This architecture does not need a continuously running Streamlit server for each visitor. It does not guarantee permanent availability or uninterrupted tab execution: hosting outages, browser suspension, discarded tabs, device sleep and reloads can still interrupt work. A deployed URL's behavior must be checked separately from local runtime tests.

First startup downloads and prepares substantial Python, WebAssembly and package assets. The assembled browser asset set is approximately **113 MiB of shipped files**. That is the total artifact size, **not measured first-load network transfer**: compression, caching and which files the browser requests affect actual transfer. Initial loading takes time, especially on a slower connection or device. Earlier local observations varied and are not a startup-time guarantee. Browser caching of application files does not save a review workspace, and reopening the app without a network connection is not established.

Work lives in the tab's memory, including the temporary SQLite workspace. There is **no automatic save** to a server or durable browser storage. Closing or reloading the tab loses unexported work. The current temporary-session policy also clears the workspace when returning after 24 hours of inactivity. Choose **“Download workspace to resume later”** before leaving and restore that file through **“Resume a saved workspace.”** The workspace file contains sources, questions, answers and saved review notes; keep it private. HTML, JSON and CSV reports are separate exports and do not replace the resumable workspace file. Resetting or ending a session clears its in-memory work and entered provider keys; it does not delete files already downloaded to your device.

Restoring a workspace recalculates automatic checks with the current evaluator and then reapplies compatible reviews bound to the supplied case, answer and sources. Reviewer identity, review method, notes and timestamps remain explicit. Automatic checks are advisory; importing, restoring or obtaining a passing automatic score does not itself create a human review. See the [evaluation methodology](EVALUATION_METHODOLOGY.md) for label semantics, uncertainty and calibration limits.

Use desktop Chrome for the browser path covered by the current local tests. The provider bridge requires WebAssembly workers, `SharedArrayBuffer`, `Atomics.wait`, a secure context and cross-origin isolation. The host must serve the document and worker assets with the applicable policies, including:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Use HTTPS for a public deployment; the local development server can use localhost HTTP. Check that `crossOriginIsolated` is true in both the page and worker. Missing isolation must produce a startup error rather than silently enabling another transport. Opening the HTML directly as a local file is not the supported serving path. These requirements follow the browser's [shared-memory security model](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/SharedArrayBuffer#security_requirements). They do not establish that a particular hosting deployment supplies the required headers.

Saved-answer review and the fictional sample do not call a model provider. Direct model execution requires a key entered by the visitor and explicit authorization to send the selected questions, sources and prompt to the chosen provider. Charges belong to that connected provider account; Studio's cost estimate is not a spending cap. Retries and additional prompt candidates can cause additional requests. Key settings remain in session memory and are not written to SQLite or resumable workspace exports. The browser distribution must not contain an owner's key or inherit server credentials.

The browser transport permits these six configured model IDs:

| Provider | Configured models |
| --- | --- |
| OpenAI | `gpt-4o-mini`, `gpt-4.1-mini` |
| Anthropic | `claude-sonnet-5`, `claude-haiku-4-5` |
| Gemini | `gemini-3.5-flash`, `gemini-3.5-flash-lite` |

This list describes the application's allowlist. Authenticated requests with real keys, account-specific model access and provider acceptance from the eventual hosting origin remain unverified. Local browser tests used fictional responses. The app reports provider failures explicitly and does not replace them with synthetic answers.

Browser runs execute **one question at a time**. The adapter preserves the existing per-request retry and cache logic, and refuses native thread pools. Responses are nonstreaming, with a 30-second transport ceiling and 1 MiB request/response limits. The synchronous run interface does not provide an immediate Stop control for an in-flight provider request. The arbitrary external HTTP assistant connector is disabled in the browser, including when a server allowlist exists; this edition does not reproduce the native adapter's DNS/address-pinning controls.

The build uses the source and dependency pins checked into the repository. Start from the repository root with Python 3.11+ and Node/npm available for the web wrapper:

```sh
python browser_runtime/dependencies/build_dependencies.py --output browser_site/.build/browser-vendor --cache browser_runtime/dependencies/cache
cd browser_site
python scripts/assemble-runtime.py --source .. --vendor .build/browser-vendor
npm ci
npm run build
npm run start -- --port 8790
```

The dependency builder requires a fresh output directory; subsequent builds can reuse its verified cache. Add `--offline` to that builder command only after all pinned inputs are cached. From `browser_site`, the assembler's explicit `--source ..` selects the main Studio checkout; its default source is the wrapper's `studio_source` directory. The local start command uses `wrangler dev --config dist/server/wrangler.json`. Serve the built wrapper through that configured entry and verify its response headers and startup behavior. These are local build/serve steps, not a deployment or account-creation command.

The [dependency builder documentation](../browser_runtime/dependencies/README.md) and [pinned manifest](../browser_runtime/dependencies/dependencies.lock.json) record official URLs, versions, archive/member hashes and package selection. Generated vendor files stay outside Git. The assembler must package the reviewed source and production adapters, preserve their provenance, and exclude `.env`, credentials, databases, uploads and fixture transports. Reports should identify the evaluator and browser runtime/source build separately from the model or assistant being assessed.

Use provider bundle **v2**. It retains the tested provider code, removes the duplicate Protobuf 5.29.6 source, adds h11 0.16.0 and preserves upstream distribution metadata and notices. The tested browser set uses Pyodide Protobuf 4.24.4 with its matching Wasm backend, Pydantic 2.7.0/core 2.18.1 and cryptography 42.0.5. Preserve the documented import order. Rust/native jiter is not included; the nonstreaming import guard fails if its unavailable streaming parser is invoked. These browser dependencies differ from the native environment.

Upstream Stlite and Pyodide licenses, provider distribution notices and dependency attribution are included in the generated assets. Hash verification establishes which archives were used; it is not an upstream security audit or a complete legal review. An npm audit of the web wrapper does not cover the vendored Stlite, Pyodide or Python packages. Browser tests establish the exercised local workflows and fixture behavior; they do not establish production scoring accuracy, real-key connectivity, hosted availability or complete deployed feature parity.
