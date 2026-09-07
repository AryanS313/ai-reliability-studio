# AI Reliability Studio browser edition

This Sites/Vinext wrapper serves the Python review workspace as static browser assets. The Python app runs in the visitor's tab through pinned Stlite and Pyodide. There is no Streamlit Community Cloud process to hibernate. Availability still depends on the host, connection, browser and device; the initial runtime download is substantial.

The source snapshot in `studio_source/` is a copy of the GitHub app at release time. In the GitHub repository's `browser_site/` directory, use `--source ..` instead. Runtime files and dependency caches are generated and excluded from Git. No local database, `.env`, credentials or customer documents belong in this source tree.

## Rebuild

Use Node 22.13+ and Python 3.11+. From this directory:

```sh
python3 scripts/dependencies/build_dependencies.py --output .build/browser-vendor --cache .cache/browser-dependencies
python3 scripts/assemble-runtime.py
npm ci
npm run build
npm run start -- --port 8790
```

For the GitHub checkout, run the builder at `../browser_runtime/dependencies/build_dependencies.py` with the same output/cache arguments, then `python3 scripts/assemble-runtime.py --source ..`.

The builder pins official inputs by hash and size. The assembler verifies the generated dependency manifest, preserves licenses, repacks identical archive members to fit the 25 MiB static-file limit, and records the exact application source snapshot. Do not swap versions or remove the worker bootstrap without repeating browser validation.

## Runtime boundaries

Use a current Chrome browser with cross-origin isolation available. Both document routes and static worker assets must retain the committed COOP/COEP headers. Workspace data and entered keys live in the tab's memory; navigating away, closing or reloading ends that workspace. Download a workspace export to resume later. Exported review data should be handled as private data.

Paid provider calls require a visitor-supplied key and explicit authorization in the app. The browser sends selected source material and the key directly to the chosen provider. No owner key is bundled. Six configured models use a restricted, nonstreaming fetch transport; arbitrary external connectors are disabled. Runs execute one answer at a time. Synthetic checks and mocked provider responses do not establish live-account access or evaluation accuracy.

## Validation scope

`npm run lint` and TypeScript check the authored wrapper. The unused, unchanged scaffold component catalog in `components/ui/` and `hooks/use-mobile.ts` is excluded from lint because of existing scaffold diagnostics. Vendored runtime code is also excluded. An npm audit covers the wrapper dependency graph, not the vendored Stlite, Pyodide or Python packages. Their versions and notices are preserved in the dependency manifest.

Use the Sites hosting skill to push this source, build/package the exact commit, save a version and publish to the intended audience. The existing `.openai/hosting.json` identifies the registered Site; do not create a duplicate.
