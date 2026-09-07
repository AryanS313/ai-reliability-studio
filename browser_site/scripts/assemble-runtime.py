"""Assemble the pinned browser distribution without host secrets or databases."""

import argparse
import copy
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_SHA256 = "1ba7da379d2b70de43ff22fdf969812b2b4a61cd6171a3d0088c499342c10e74"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_member(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, data, compresslevel=9)


def assemble(source: Path, vendor: Path) -> None:
    out = ROOT / "public/assets/studio"
    out.mkdir(parents=True, exist_ok=True)
    # Validate every dependency against the builder's manifest before copying.
    built = json.loads((vendor / "build-manifest.json").read_text())
    for entry in built["files"]:
        path = (vendor / entry["path"]).resolve()
        assert path.is_relative_to(vendor) and path.is_file()
        assert path.stat().st_size == entry["bytes"] and digest(path.read_bytes()) == entry["sha256"]
    # The pinned archive gets an independent integration assertion as well.
    provider = vendor / "provider-packages-v2.zip"
    assert digest(provider.read_bytes()) == PROVIDER_SHA256
    for directory in ("stlite", "runtime", "wheels"):
        if (out / directory).exists():
            shutil.rmtree(out / directory)
    shutil.copytree(
        vendor / "stlite-browser/package/build",
        out / "stlite",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("*.map"),
    )
    shutil.copy2(vendor / "stlite-browser/package/LICENSE", out / "stlite/LICENSE")
    shutil.copytree(vendor / "runtime", out / "runtime", dirs_exist_ok=True)
    shutil.copytree(vendor / "wheels", out / "wheels", dirs_exist_ok=True)
    shutil.copy2(provider, out / "provider-packages.zip")
    shutil.copy2(vendor / "THIRD_PARTY_NOTICES.md", out / "THIRD_PARTY_NOTICES.md")
    shutil.copy2(vendor / "runtime-packages.json", out / "runtime-packages.json")
    (out / "dependency-build-manifest.json").write_text(json.dumps(built, indent=2) + "\n")

    # Recompress unchanged members to fit the static host's 25 MiB file limit.
    repacks = []
    lock = json.loads((out / "runtime/pyodide-lock.json").read_text())
    for path in sorted((out / "runtime").iterdir()):
        if path.suffix not in {".whl", ".zip"}:
            continue
        before, before_size = digest(path.read_bytes()), path.stat().st_size
        temporary = path.with_suffix(path.suffix + ".tmp")
        with (
            zipfile.ZipFile(path) as original,
            zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target,
        ):
            entries = {info.filename: digest(original.read(info)) for info in original.infolist()}
            for info in original.infolist():
                copied = copy.copy(info)
                copied.compress_type = zipfile.ZIP_DEFLATED
                target.writestr(copied, original.read(info))
        with zipfile.ZipFile(temporary) as verified:
            assert entries == {info.filename: digest(verified.read(info)) for info in verified.infolist()}
        temporary.replace(path)
        after = digest(path.read_bytes())
        for package in lock["packages"].values():
            if package["file_name"] == path.name:
                package["sha256"] = after
        repacks.append(
            {
                "file": path.name,
                "source_sha256": before,
                "sha256": after,
                "original_bytes": before_size,
                "bytes": path.stat().st_size,
                "identical_archive_members": True,
            }
        )
    (out / "runtime/pyodide-lock.json").write_text(json.dumps(lock, separators=(",", ":")))
    (out / "runtime-repack-manifest.json").write_text(json.dumps(repacks, indent=2) + "\n")

    # Explicit allowlist excludes configuration secrets, local data and caches.
    names = {"app.py", ".streamlit/config.toml", "LICENSE"}
    for directory, suffixes in {
        "src": {".py"},
        "data": {".json", ".csv", ".txt", ".md"},
        "prompts": {".json", ".txt", ".md"},
        "examples": {".json", ".jsonl", ".csv", ".txt", ".md"},
    }.items():
        names.update(
            str(path.relative_to(source))
            for path in (source / directory).rglob("*")
            if path.is_file() and path.suffix in suffixes
        )
    names.update(str(path.relative_to(source)) for path in (source / "browser_runtime").glob("*.py"))
    source_manifest = []
    with zipfile.ZipFile(out / "source.zip", "w") as archive:
        for name in sorted(names):
            path = source / name
            assert path.is_file() and not path.is_symlink() and ".env" not in path.parts
            data = path.read_bytes()
            write_member(archive, name, data)
            source_manifest.append({"path": name, "sha256": digest(data)})
        source_hash = digest(json.dumps(source_manifest, sort_keys=True, separators=(",", ":")).encode())
        write_member(archive, "browser-source-sha256.txt", source_hash.encode())
    (out / "source-manifest.json").write_text(
        json.dumps({"source_sha256": source_hash, "files": source_manifest}, indent=2) + "\n"
    )
    shutil.copy2(source / "browser_runtime/entry.py", out / "entry.py")
    shutil.copy2(source / "browser_runtime/fetch-worker.js", out / "fetch-worker.js")

    # Await the provider-worker bootstrap before Stlite's synchronous runner.
    worker = out / "stlite/assets/worker-DB8fls9q.js"
    worker_code = worker.read_text()
    anchor = "import importlib\nimportlib.invalidate_caches()"
    assert worker_code.count(anchor) == 1
    hook = """import importlib
import sys
import js
sys.path[:0] = ['/app/browser_runtime', '/app', '/providers']
importlib.invalidate_caches()
from browser_bootstrap import prepare_browser_provider_runtime
await prepare_browser_provider_runtime(str(js.location.origin) + '/assets/studio/fetch-worker.js')"""
    # Stlite debug logs can contain uploaded bytes and widget response bodies.
    worker.write_text("console.debug = console.log = console.info = () => {};\n" + worker_code.replace(anchor, hook))
    assert all(path.stat().st_size <= 25 * 1024 * 1024 for path in out.rglob("*") if path.is_file())
    print(
        json.dumps(
            {
                "asset_bytes": sum(path.stat().st_size for path in out.rglob("*") if path.is_file()),
                "repacked_archives": len(repacks),
                "source_files": len(names),
                "source_sha256": source_hash,
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "studio_source")
    parser.add_argument("--vendor", type=Path, default=ROOT / ".build/browser-vendor")
    args = parser.parse_args()
    assemble(args.source.resolve(), args.vendor.resolve())
