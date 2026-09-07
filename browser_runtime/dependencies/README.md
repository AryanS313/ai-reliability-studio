# Reproducible browser dependencies

The release build needs **`build_dependencies.py` and `dependencies.lock.json`**. Both are plain source files suitable for GitHub. The lock pins 87 official archives/files (225,950,798 bytes before extraction), including the 0.76.0 Stlite npm distribution, Pyodide 0.26.4 runtime/package closure, all eleven tested document/UI wheels, provider pure-Python wheels, and upstream Stlite/Pyodide licenses. This directory also contains `test_build_dependencies.py`, this README, `reconstruction-report.json`, and `.gitignore` for review. No wheel, archive, runtime binary, cache or generated vendor directory needs to enter Git history.

Run the following commands from the repository root. Python 3.11+ and its standard library are sufficient. The build does not install or execute downloaded code and never runs pip/npm, consults application configuration, discovers credentials, or inherits environment proxy settings. URLs and hashes come from the committed manifest; it never asks a package resolver for current versions. The original manifest-authoring and forensic scripts remain in the separate validation workspace. They are not needed for a normal release build; the checked-in lock and reconstruction report preserve the selected inputs and verification results.

```sh
python browser_runtime/dependencies/build_dependencies.py --output browser_runtime/dependencies/build-vendor --cache browser_runtime/dependencies/cache
python -m unittest discover -s browser_runtime/dependencies -p test_build_dependencies.py -v
```

Use a fresh output directory for each run. Existing outputs are never overwritten. Every download and cached file is checked against its exact SHA256 and byte count; archives are unpacked without running their code. Interrupted downloads leave no accepted cache entry. A later retry can reuse verified cache entries. A cache-complete build can run without network access:

```sh
python browser_runtime/dependencies/build_dependencies.py --output browser_runtime/dependencies/build-check --cache browser_runtime/dependencies/cache --offline
```

The local `.gitignore` covers these build/cache paths; custom paths need corresponding ignore rules.

## Output and integration

- `stlite-browser/package/`: the unchanged npm package, plus the official Stlite 0.76.0 LICENSE omitted from its tarball. Load `build/stlite.js` and `build/style.css` beneath this directory.
- `runtime/`: pinned Pyodide core files and the complete selected Wasm/package dependency closure, plus its upstream LICENSE.
- `wheels/`: all eleven tested pure application wheels, unchanged with their original metadata/notices.
- `provider-packages-v1.zip`: exact member reconstruction of the earlier test bundle, retained as evidence.
- **`provider-packages-v2.zip`: coherent provider bundle for integration**, with duplicate Protobuf removed, h11 supplied, and original distribution metadata/notices retained.
- `runtime-packages.json`: explicit browser runtime version, prebuilt package list and application wheel paths for bootstrap wiring.
- `THIRD_PARTY_NOTICES.md` and `build-manifest.json`: source attribution and every generated file's hash/size.

Configure Stlite's `pyodideUrl` to the local `runtime/pyodide.mjs`, use the prebuilt package list in `runtime-packages.json`, and install the listed local app-wheel URLs. Load official Pyodide Pydantic 2.7.0/core 2.18.1 and cryptography 42.0.5/cffi 1.16.0 via that package list. Extract provider **v2** to a separate `/providers` directory and put it first on `sys.path` before importing provider SDKs. Do not extract v1 and v2 into the same runtime. Preserve the runtime's normal browser environment (including HOME); force the app's explicit public/browser mode without importing any host process environment or `.env`.

No jiter/Rust/native host binaries are packaged. Pinned OpenAI's streaming-only jiter import still needs the separately reviewed, failing nonstreaming guard in the browser bootstrap. The release's dedicated HTTPX transport and sequential executor are separate source inputs; this builder does not insert fixture transports or modify SDK request/response code. Production must point to its frozen same-origin worker, never a fixture worker.

## Exact reconstruction and the coherent revision

V1 contains **1,128 members**, all byte-for-byte equal to the original provider test bundle and to entries from official SHA-verified PyPI wheels. Its ZIP container deliberately differs: names/order, 1980 timestamps and permissions are fixed, and ZIP_STORED makes output independent of zlib versions. V1 SHA256 is `f4ed27c6b181d5c0a176d3c7871707118265b1de291149cddfaaea04f8d9e5fe`.

V2 contains **1,169 members**. It removes all 55 `google/protobuf` 5.29.6 files; adds h11 0.16.0 from the current native requirements lock; and retains all supplied distribution metadata except RECORD, plus **26 license/notice files**. RECORD is omitted because this is a selected-file archive rather than an installed whole wheel. Every original retained member is unchanged. V2 SHA256 is **`1ba7da379d2b70de43ff22fdf969812b2b4a61cd6171a3d0088c499342c10e74`**. Package notices remain with their distributions, while the complete manifest describes the exact selected members.

The selected provider package versions are in the lock. Main SDK pins remain OpenAI 1.54.4, Anthropic 0.39.0, google-genai 1.0.0 and HTTPX 0.28.1. These are distinct from the native environment's transitive dependency set. Use the shipped package manifest and runtime observations for provenance; a native requirements file does not identify browser imports. Some pure provider dependencies overlap Pyodide packages, so preserve the tested `/providers` import precedence and do not swap import order during integration.

## Verification and scope

Two final, cache-complete builds produced **219 identical output files**, with every file rehashed; the build manifests match exactly. The original Stlite tarball's 153 regular members remain byte-identical. Four focused builder tests pass: corrupt caches and missing offline inputs fail; path/URL escapes fail; repacking preserves bytes deterministically; altered provider-member hashes and native members fail. Ruff lint and formatting checks pass.

The independent actual Chrome/Pyodide run against the final v2 hash passed six configured model fixtures, seven error cases and 34 endpoint/cancellation/lifecycle checks. After SDK execution, Protobuf reported **4.24.4** in code and distribution metadata, loaded solely from `/lib/python3.12/site-packages/google/protobuf/`; its matching upb Wasm backend loaded from the same site-packages tree. There was no `/providers/google/protobuf` or `/providers/google/_upb`. Protobuf Struct and Streamlit **1.41.0** ForwardMsg round trips passed. h11 **0.16.0** loaded from `/providers/h11`, and HTTPcore **1.0.9** imported successfully. Evidence is preserved separately in `work/browser-provider-v2-validation`.

Those are fictional local provider responses and dependency coherence checks. They do not establish authenticated provider acceptance, final-origin CORS, hosted isolation headers, full deployed application parity, or production evaluation accuracy. This build performs no vulnerability audit; an npm audit of a hosting wrapper does **not** cover the vendored Stlite/Pyodide/Python dependencies.

## Upstream provenance

The npm tarball's original `dist.integrity` SHA512 was checked before its SHA256 was pinned. Every PyPI wheel was downloaded from the exact file URL in its versioned PyPI JSON and checked against that metadata's SHA256. Pyodide package hashes match its original 0.26.4 lock; core runtime files match their versioned official CDN downloads. Upstream licenses are fetched from tagged source and SHA-pinned. These checks establish archive identity from the recorded official sources, not a review of all upstream code or a publisher-signature audit.

- [Stlite 0.76.0 package metadata](https://registry.npmjs.org/@stlite%2fbrowser/0.76.0) and [tagged source/license](https://github.com/whitphx/stlite/tree/v0.76.0).
- [Pyodide 0.26.4 deployment documentation](https://pyodide.org/en/0.26.4/usage/quickstart.html), [original package lock](https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide-lock.json), and [tagged source/license](https://github.com/pyodide/pyodide/tree/0.26.4).
- Exact PyPI release JSON and file URLs, archive/member hashes, versions and byte sizes are recorded per input in `dependencies.lock.json`.

Final lock SHA256: `b27b64fa13112727e0d4ebaebd04ab6382c1e472163af0d2abee1f4b404fc19a`.
