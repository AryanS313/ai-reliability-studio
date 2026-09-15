"""Fetch hash-pinned browser dependencies without executing package code.

Python 3.11+ standard library only. No pip, npm, shell, environment proxy,
credential discovery, native compilation, or dynamic version resolution.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import shutil
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ALLOWED_HOSTS = {"registry.npmjs.org", "files.pythonhosted.org", "cdn.jsdelivr.net", "raw.githubusercontent.com"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("Unsafe archive/output path")
    return path


def allowed_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Dependency URL is outside the pinned official hosts")


class OfficialRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        allowed_url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def fetch(asset: dict, cache: Path, *, offline: bool = False) -> Path:
    expected = asset["sha256"]
    size = asset["bytes"]
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("Invalid pinned hash")
    if type(size) is not int or not 0 < size <= 512 * 1024 * 1024:
        raise ValueError("Invalid pinned size")
    destination = cache / expected
    if destination.exists():
        data = destination.read_bytes()
        if len(data) != size or sha256(data) != expected:
            raise ValueError(f"Corrupt cached dependency: {asset['id']}")
        return destination
    if offline:
        raise FileNotFoundError(f"Missing cached dependency: {asset['id']}")
    allowed_url(asset["url"])
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), OfficialRedirectHandler())
    temporary = cache / (expected + ".partial")
    digest = hashlib.sha256()
    written = 0
    try:
        with opener.open(asset["url"], timeout=60) as response, temporary.open("wb") as output:
            if response.status != 200:
                raise ValueError(f"Dependency download failed: {asset['id']}")
            while block := response.read(1024 * 1024):
                written += len(block)
                if written > size:
                    raise ValueError(f"Dependency exceeded pinned size: {asset['id']}")
                digest.update(block)
                output.write(block)
        if written != size or digest.hexdigest() != expected:
            raise ValueError(f"Dependency hash/size mismatch: {asset['id']}")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def reproducible_zip(path: Path, files: dict[str, bytes]) -> None:
    # ZIP_STORED avoids zlib-version-dependent output. HTTP compression can be
    # applied by the static host. Names, timestamps, modes and order are fixed.
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            safe_path(name)
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)


def read_provider_files(manifest: dict, assets: dict[str, Path], variant: str) -> dict[str, bytes]:
    files = {}
    for specification in manifest["provider_variants"][variant]["wheels"]:
        with zipfile.ZipFile(assets[specification["asset"]]) as archive:
            for name, expected in specification["members"].items():
                safe_path(name)
                data = archive.read(name)
                if sha256(data) != expected:
                    raise ValueError(f"Provider wheel member mismatch: {name}")
                if name in files:
                    raise ValueError(f"Duplicate provider member: {name}")
                if name.endswith((".so", ".dylib", ".dll", ".pyc")) or name.split("/")[0] == "jiter":
                    raise ValueError("Native or jiter files are forbidden in provider archive")
                files[name] = data
    return files


def build(manifest_path: Path, output: Path, cache: Path, offline: bool = False) -> dict:
    manifest = json.loads(manifest_path.read_text())
    if manifest["schema_version"] != "browser-dependencies-v1":
        raise ValueError("Unsupported dependency manifest")
    if output.exists():
        raise FileExistsError("Choose a fresh output directory; existing assets are never overwritten")
    cache.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    assets = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        pending = {pool.submit(fetch, asset, cache, offline=offline): asset for asset in manifest["assets"]}
        for future in concurrent.futures.as_completed(pending):
            asset = pending[future]
            assets[asset["id"]] = future.result()
    with tempfile.TemporaryDirectory(prefix="browser-dependency-build-", dir=output.parent) as temp:
        stage = Path(temp)
        for asset in manifest["assets"]:
            if "output" in asset:
                path = stage / safe_path(asset["output"])
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(assets[asset["id"]], path)
        with tarfile.open(assets["stlite-browser-0.76.0"], "r:gz") as archive:
            for member in archive:
                safe_path(member.name)
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError("Npm archive links/special files are not allowed")
                if not member.name.startswith("package/"):
                    raise ValueError("Unexpected Stlite archive layout")
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("Unreadable npm archive file")
                destination = stage / "stlite-browser" / member.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read())
        variants = {}
        for variant, specification in manifest["provider_variants"].items():
            files = read_provider_files(manifest, assets, variant)
            path = stage / specification["output"]
            reproducible_zip(path, files)
            variants[variant] = {
                "path": specification["output"],
                "members": len(files),
                "sha256": sha256(path.read_bytes()),
            }
        (stage / "runtime-packages.json").write_text(json.dumps(manifest["runtime"], indent=2, sort_keys=True) + "\n")
        (stage / "THIRD_PARTY_NOTICES.md").write_text(
            "# Browser dependency attribution\n\n"
            "Stlite 0.76.0 is from https://github.com/whitphx/stlite/tree/v0.76.0 "
            "and its npm package declares Apache-2.0. Its official license is retained "
            "in stlite-browser/package/LICENSE; its original README/package metadata "
            "and bundled wheels are unchanged.\n\n"
            "Pyodide 0.26.4 is obtained from its official versioned CDN. Its MPL-2.0 license "
            "is in runtime/LICENSE and its corresponding source is available at "
            "https://github.com/pyodide/pyodide/tree/0.26.4 . "
            "Original Wasm/pure wheels remain intact with their bundled license notices. "
            "Provider bundle v2 retains official distribution metadata and supplied license/notice files. "
            "Provider v1 is reconstruction evidence and omits notices absent from the original test bundle.\n\n"
            "dependencies.lock.json in the source build records all archive URLs and hashes. "
            "This build does not perform a vulnerability audit. An npm audit of a separate hosting wrapper "
            "does not audit these pinned Stlite, Pyodide, or Python dependencies.\n"
        )
        tree = [
            {"path": p.relative_to(stage).as_posix(), "bytes": p.stat().st_size, "sha256": sha256(p.read_bytes())}
            for p in sorted(stage.rglob("*"))
            if p.is_file()
        ]
        report = {"manifest_sha256": sha256(manifest_path.read_bytes()), "provider_variants": variants, "files": tree}
        (stage / "build-manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        output.mkdir()
        for child in stage.iterdir():
            shutil.move(str(child), str(output / child.name))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("dependencies.lock.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path(__file__).with_name("cache"))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    report = build(args.manifest, args.output, args.cache, args.offline)
    print(json.dumps({"files": len(report["files"]), "providers": report["provider_variants"]}, indent=2))


if __name__ == "__main__":
    main()
