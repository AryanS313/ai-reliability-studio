# Browser dependency review

## Decision and scope

The browser edition retains Stlite 0.76.0 / Pyodide 0.26.4 while replacing compatible pure-Python dependencies and verifying the limited interfaces used from compiled packages. This is a scoped reachability review, **not a clean vulnerability scan or a claim that the old runtime is fully patched**. Native Python checks do not certify the assembled WebAssembly application.

The baseline `browser_site/.build/browser-all-python-audit.json` contained 139 advisory entries across nine packages. Deduplicating by GHSA gives 74 advisories; duplicate CVE/PYSEC records must not be counted as separate vulnerabilities. The audit describes package versions. It does not establish whether an application exposes each vulnerable operation or audit bundled C libraries and the Python interpreter.

## Pure-Python remediation and observed versions

| Package | Baseline → observed release version | Advisory family and application reachability |
| --- | --- | --- |
| pypdf | 5.1.0 → 6.18.1 | 41 distinct advisories cover stream expansion, malformed cross-reference tables, fonts, inline images, object graphs, outlines, and related resource exhaustion. `extract_document_artifact()` calls `PdfReader` and `page.extract_text()` on uploaded PDFs. Parsing, stream and font cases are directly reachable **before** the extracted-text limit. The old version blocks PDF release. Examples: [FlateDecode exhaustion](https://github.com/py-pdf/pypdf/security/advisories/GHSA-7hfw-26vp-jp8m), [font-width expansion during extraction](https://github.com/py-pdf/pypdf/security/advisories/GHSA-fwg2-594c-jp42). |
| protobuf | 4.24.4 → 5.29.6, pure Python | [Recursive wire messages](https://github.com/advisories/GHSA-8qvm-5x2c-j2w7) and [JSON `Any` recursion](https://github.com/advisories/GHSA-7gcm-g887-7qv7). Streamlit depends on protobuf for its message boundary. The app does not expose arbitrary protobuf imports, but protocol parsing is material enough to patch. Bundled Streamlit 1.41.0 accepts `protobuf>=3.20,<6`. Replace the old package before Streamlit imports, use one namespace/implementation, and verify the actual loaded version and backend. A second wheel installed after import does not remediate the running module. |
| Jinja2 | 3.1.3 → 3.1.6 | GHSA-h75v-3vvj-5mfj, GHSA-q2x7-8rv6-6q7h, GHSA-gmj6-6f8f-6699, GHSA-cpwx-vrp4-4pq7 concern unsafe attributes and attacker-controlled templates/filenames. The product has no user-template execution interface; prompts are data. Apply the compatible patch regardless. [Sandbox advisory](https://github.com/pallets/jinja/security/advisories/GHSA-cpwx-vrp4-4pq7). |
| soupsieve | 2.5 → 2.8.4 | GHSA-836r-79rf-4m37 and GHSA-2wc2-fm75-p42x concern malicious CSS selectors. HTML extraction uses BeautifulSoup's `html.parser`, fixed tag names, and text traversal. Users cannot submit selector expressions. Apply the compatible patch. |
| python-dotenv | 1.0.1 → 1.2.2 | GHSA-mf9w-mj56-hr94 concerns symlinks during `set_key`/`unset_key` rewriting. Configuration calls `load_dotenv`; there is no `.env` editing/upload interface. Patch the package; do not add environment rewriting to browser flows. |

The rebuilt inventory and actual WebAssembly imports now confirm the patched versions above. The audit of **69 reconstructed browser Python packages** retains **44 advisory entries** in four compiled packages:

| Retained package | Version | Advisory entries |
|---|---|---:|
| cryptography | 42.0.5 | 11 |
| lxml | 5.2.1 | 2 |
| Pillow | 10.2.0 | 29 |
| scikit-learn | 1.4.2 | 2 |

The recorded audit is `browser_site/.build/browser-patched-audit.json` (ignored build evidence). These are raw advisory entries, which can contain multiple records for one issue; they are not 44 distinct CVEs or 44 demonstrated application paths. The scoped analysis below and regression tests bound the interfaces exercised by this product. They do not make the packages fully patched.

Native `pip-audit --strict` and the web wrapper's npm audit separately reported no known vulnerabilities at their recorded checks. Native Ruff, formatting, mypy and dependency consistency passed; the wrapper's lint, TypeScript and build checks passed. Those audit scopes must not be merged into a blanket clean-browser claim.

## Compiled packages: narrower evidence, retained limitations

### lxml 5.2.1 — external entities

[GHSA-vfmq-68hx-4jfw](https://github.com/lxml/lxml/security/advisories/GHSA-vfmq-68hx-4jfw) affects default `iterparse()` and `ETCompatXMLParser()` entity resolution; the upstream fix is 6.1.0. Inspection of the actual vendored application wheels found:

- DOCX 1.1.2: both `docx/oxml/parser.py` and `docx/opc/oxml.py` create `XMLParser(..., resolve_entities=False)`.
- PPTX 1.0.2: `pptx/oxml/__init__.py` explicitly disables entity resolution.
- openpyxl 3.1.5: lxml `fromstring` uses `XMLParser(resolve_entities=False)`; `iterparse` comes from stdlib ElementTree or defusedxml, not lxml's affected default.
- The application's `.xml` input path returns decoded text; it does not parse entities.

Tests inject local-file and HTTPS entities into actual DOCX/PPTX parts. A resolver tripwire must never run, a temporary sentinel file must never be substituted into output, and ordinary text must survive. A separate test checks literal `.xml` handling. These controls address this advisory's identified path; they do not certify every XML parser feature or libxml2 vulnerability.

### Pillow 10.2.0 — image, font, color, and PDF operations

The baseline has 15 distinct advisory IDs:

`GHSA-44wm-f244-xhp3`, `GHSA-wjx4-4jcj-g98j`, `GHSA-r73j-pqj5-w3x7`, `GHSA-8v84-f9pq-wr9x`, `GHSA-45hq-cxwh-f6vc`, `GHSA-4x4j-2g7c-83w6`, `GHSA-phj9-mv4w-65pm`, `GHSA-5x94-69rx-g8h2`, `GHSA-9hw9-ch79-4vh6`, `GHSA-6r8x-57c9-28j4`, `GHSA-62p4-gmf7-7g93`, `GHSA-xj96-63gp-2gmr`, `GHSA-fj7v-r99m-22gq`, `GHSA-jjj6-mw9f-p565`, `GHSA-vjc4-5qp5-m44j`.

They concern ImageCms memory safety, font/bitmap expansion, large coordinates and filters, mapped image buffers, TGA encoding, JPEG2000 decoding, Pillow PDF parsing, and Windows shell commands. Fixes span 10.3.0 through 12.3.0. The browser edition offers text extraction, not image extraction, font rendering, OCR, or image exports.

Vendored PPTX uses `PIL.Image.open` in lazy image-property access, which the application's text/table/notes traversal does not request. pypdf uses image decoders in its image-extraction helpers; page-text extraction does not request those images. XLSX reading uses pandas' read-only workbook path. The product does not call Pillow PDF parsing or Windows viewers.

Tests extract PDF/DOCX/PPTX fixtures that contain both text and embedded images while image opening, allocation, decoding, encoding, transforms, filters, and font loading raise immediately. ImageCms entry points are also guarded when that optional module exists. Test fixtures are created **before** installing the tripwires; fixture construction is not a product extraction path. This finite corpus is regression evidence, not proof for every malformed document. The actual Wasm tests below exercise these fixture paths; final hosted browser workflows remain a separate acceptance check. WebAssembly does not by itself prevent disclosure of another value in the same tab's memory if a vulnerable API becomes reachable.

### cryptography 42.0.5 / OpenSSL 1.1.1n — key and certificate processing

The baseline's seven distinct IDs are `GHSA-79v4-65xg-pq4g`, `GHSA-r6ph-v2qm-q3c2`, `GHSA-m959-cc7f-wv43`, `GHSA-jwv3-5hgf-82ww`, `GHSA-m2h6-j472-rp4c`, `GHSA-h4gh-qq45-vh27`, and `GHSA-537c-gmf6-5ccf`. They cover SECT subgroup validation, X.509 name constraints and chain construction, and OpenSSL versions in upstream binary wheels. Current upstream fixes extend through cryptography 49.0.0.

The actual Pyodide lock specifies a separately built OpenSSL 1.1.1n dependency. An advisory describing OpenSSL statically bundled in upstream PyPI wheels does not establish the exact status of this different build. It also does not establish that this older OpenSSL is safe.

The supported browser provider path is `BrowserFetchTransport` → the shipped Fetch worker → official provider HTTPS routes. Browser networking performs TLS. Arbitrary external HTTP is denied, inherited provider/cloud credentials are suppressed, and the UI does not import private keys, certificates, or certificate chains. PDF encryption, if exercised, uses symmetric cryptographic primitives rather than the cited SECT/X.509 operations; encrypted-file behavior still needs its own validation before claiming support.

The new negative-path test guards native socket/SSL operations and PEM/DER key/certificate loaders, then verifies browser external calls are denied and environment secrets cannot resolve. Existing provider transport tests cover official routes and credential selection. This does not replace the real worker/Fetch test or certify unused cryptography/OpenSSL interfaces.

### scikit-learn 1.4.2 — discarded vocabulary retention

[GHSA-jw8x-6495-233v](https://github.com/advisories/GHSA-jw8x-6495-233v) / CVE-2024-5206 concerns tokens retained in the `stop_words_` introspection attribute. `LocalTfidfEmbedder.fit_transform()` now removes that unused attribute immediately after fitting, without changing the returned matrix, fitted vocabulary, or inverse-document-frequency values. Tests compare fitted and query vectors to the unchanged scikit-learn implementation, verify retrieval order, and verify retrieval/report JSON does not contain the fitted object or the discarded-token marker. There is no product operation to export or pickle a fitted vectorizer. Source text and necessary vocabulary remain in the current session for retrieval; this change is not a promise that input text disappears while a session is active.

## Inspected wheel-member fingerprints

These hashes identify the source evidence inspected in the baseline vendor directory. Rebuilding or changing those files requires repeating the relevant inspection and tests.

| Wheel/member | SHA-256 |
| --- | --- |
| python_docx 1.1.2 / `docx/opc/oxml.py` | `c9156c9f9299becbf7559fc685d23cd34fcd350d6a30630af280dab493b63a76` |
| python_docx 1.1.2 / `docx/oxml/parser.py` | `666e771a85a8e8abc8608caaeb8b3c927cbf573528a33bc6aeae96b16513ab15` |
| python_pptx 1.0.2 / `pptx/oxml/__init__.py` | `357a2705a0384c8bbde4de17a115838443fe09b16a7ca822b9cb296983a3b02c` |
| python_pptx 1.0.2 / `pptx/parts/image.py` | `2986341c5535d1551cf601cb6b7febeb8347f86e9d70f6c992ec61a345decdf4` |
| openpyxl 3.1.5 / `openpyxl/xml/functions.py` | `8c1b5f6bcfffc388019443c61cb18202d26268d28fca28532ec7e68a0caadbf4` |

## Observed WebAssembly verification

`tests/test_browser_dependency_reachability.py` passed **11 tests in 4.30 seconds** inside the assembled Pyodide 0.26.4 runtime, hosted by Node 24.14.0. Python reported **3.12.1 / `emscripten`**. One warning concerned pandas' future PyArrow requirement. This run used actual compiled Wasm dependencies, not monkeypatched native imports.

| Loaded package | Observed version |
|---|---|
| Streamlit | 1.41.0 |
| Protobuf | 5.29.6, `python` implementation |
| pypdf / python-dotenv | 6.18.1 / 1.2.2 |
| Jinja2 / soupsieve | 3.1.6 / 2.8.4 |
| Pillow / lxml | 10.2.0 / 5.2.1 |
| cryptography / Pydantic | 42.0.5 / 2.7.0 |
| scikit-learn / NumPy / pandas | 1.4.2 / 1.26.4 / 2.2.0 |

The harness sets `PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python` before import, confirms Protobuf loads from site-packages with no competing provider namespace and no loaded `google._upb`, then round-trips Protobuf Struct and Streamlit ForwardMsg messages. All 50 copied runtime files matched the assembled inputs byte-for-byte. Node needed an ignored CommonJS package boundary around the unchanged runtime because the web wrapper is an ES-module package; no Site/runtime source was modified for this check.

The fixture run covered text extraction without image/font operations, DOCX/PPTX external-entity refusal, literal XML, TF-IDF retained-token cleanup with unchanged vectors/retrieval, and rejection of browser native HTTP/key/certificate paths. JavaScript fetch was forbidden and recorded **zero network attempts**. No credentials or model requests were used. Pytest and three pure-Python test-runner dependencies were added only under `/runner`; their hashes are recorded separately from the product packages.

The relevant tested source fingerprints are:

| Module | SHA-256 |
|---|---|
| `tests/test_browser_dependency_reachability.py` | `47ecdc96fe75f3f75c1b7d6e1d84f653d7e21f57a2c09416e45beb2fba959eee` |
| `src/embeddings.py` | `07fdb6c6131535eb2d71d56e59d98d631f26c7afd04d768134396c88a512d7cd` |
| `src/document_loader.py` | `9c32c5ec1083a4a803f5d00db28c6a33a966fb10bdde1efc7946619e2ae5d53f` |
| `src/targets.py` | `1e2c9e4c3eede19a27e44c95aa51c389ccb2d0a21330b56277915fdde17b8755` |
| `src/security.py` | `cfb2f28d6256e232d65be5d7ca9438997715c6881407743ee0c6db432a8703f1` |
| `src/vector_store.py` | `5c61a7747c868f919d5ecc4feb0f331c22797336e2b63beb98697668a8d2897c` |

Ignored reproducibility artifacts are `.local-verification/wasm-reachability/run.mjs`, `run.log`, `result.json`, `runtime-snapshot.json` and `README.md`. They retain the exact runtime lock/archive/test hashes for this observation. These module fingerprints do not assert that later UI refinements or the final deployed application bundle are byte-identical.

The separate combined native suite passed **1,061 tests with zero skips**, with **87.86% branch-enabled source coverage**. The local browser UI also booted, reloaded and completed its 32-case synthetic review with readable findings and the three intended simulated infrastructure errors. That UI observation and the Node-hosted Wasm tests are complementary evidence, not a final-origin deployment check.

## Remaining release gates and limits

Portable focused checks can be rerun with:

```sh
python -m pytest tests/test_browser_dependency_reachability.py tests/test_source_input_fidelity.py tests/test_retrieval_and_documents.py --no-cov -q
```

Before recording the hosted release as verified:

1. Record final source/dependency manifests after pending UI refinements; repeat relevant tests for changed source or dependency inputs.
2. Verify startup and the loaded single Protobuf implementation at the final hosted origin, preserving the fixed worker/Fetch boundary and no inherited credentials or native fallback.
3. Exercise clean-session sample/custom/upload/export/reset and saved-answer replacement/resume journeys at that origin, including independent sessions.
4. Record remote CI, publication and commit/deployment identifiers after those actions succeed; they are authorized but still pending at this handoff.
5. Keep residual advisories visible. If an affected API becomes reachable, patch/rebuild the compiled package or disable that new path before release.

Node-hosted Wasm does not verify page/worker isolation headers, final-origin CORS, actual provider acceptance or every malformed document. Optional ImageCms paths are guarded when available; the harness result does not inventory every optional native feature. The interpreter, C dependencies and unsupported image/OCR/cryptographic functions remain outside what these finite fixtures prove. A future runtime upgrade needs its own audit: the inspected Pyodide 314.0.6 inventory also contained cryptography 47.0.0 and Pillow 12.2.0, below some current fixes. There is no claim of a vulnerability-free browser bundle.
