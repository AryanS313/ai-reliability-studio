from __future__ import annotations

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from build_dependencies import (
    allowed_url,
    fetch,
    read_provider_files,
    reproducible_zip,
    safe_path,
)


class BuildPolicyTests(unittest.TestCase):
    def test_offline_cache_is_rehashed_and_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            content = b"verified dependency fixture"
            digest = hashlib.sha256(content).hexdigest()
            asset = {
                "id": "fixture",
                "sha256": digest,
                "bytes": len(content),
                "url": "https://files.pythonhosted.org/fixture",
            }
            path = cache / digest
            path.write_bytes(content)
            with mock.patch("urllib.request.build_opener", side_effect=AssertionError("Network not allowed")):
                self.assertEqual(fetch(asset, cache, offline=True), path)
                path.write_bytes(b"different file at a hash-named path")
                with self.assertRaisesRegex(ValueError, "Corrupt"):
                    fetch(asset, cache, offline=True)
                path.unlink()
                with self.assertRaisesRegex(FileNotFoundError, "Missing"):
                    fetch(asset, cache, offline=True)

    def test_paths_and_remote_locations_reject_escape_and_credential_urls(self):
        for path in ["../escape", "/absolute", "dir/../../escape", "dir\\escape"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_path(path)
        for url in [
            "http://files.pythonhosted.org/a",
            "https://example.invalid/a",
            "https://key@files.pythonhosted.org/a",
            "https://files.pythonhosted.org/a?key=secret",
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                allowed_url(url)

    def test_repacking_ignores_mapping_order_and_preserves_exact_member_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            one, two = (Path(temporary) / name for name in ("one.zip", "two.zip"))
            reproducible_zip(one, {"b.py": b"second", "a.py": b"first"})
            reproducible_zip(two, {"a.py": b"first", "b.py": b"second"})
            self.assertEqual(one.read_bytes(), two.read_bytes())
            with zipfile.ZipFile(one) as archive:
                self.assertEqual(archive.namelist(), ["a.py", "b.py"])
                self.assertEqual(archive.read("b.py"), b"second")

    def test_wrong_member_hash_or_native_member_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            wheel = Path(temporary) / "fixture.whl"
            reproducible_zip(wheel, {"package/__init__.py": b"x=1", "package/native.so": b"binary"})
            members = {"package/__init__.py": "0" * 64}
            manifest = {"provider_variants": {"v2": {"wheels": [{"asset": "fixture", "members": members}]}}}
            with self.assertRaisesRegex(ValueError, "mismatch"):
                read_provider_files(manifest, {"fixture": wheel}, "v2")
            members.clear()
            members["package/native.so"] = hashlib.sha256(b"binary").hexdigest()
            with self.assertRaisesRegex(ValueError, "Native"):
                read_provider_files(manifest, {"fixture": wheel}, "v2")


if __name__ == "__main__":
    unittest.main()
