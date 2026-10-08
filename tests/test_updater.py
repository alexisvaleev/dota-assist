"""Автообновление: _ver, check() по мокнутому httpx, _verify на tmp-файле.
Без сети и без Qt."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import updater                        # noqa: E402


REL = {
    "tag_name": "v1.2.0",
    "assets": [
        {"name": "DotaAssist.exe",
         "browser_download_url": "https://dl/DotaAssist.exe",
         "size": 4096},
        {"name": "checksums.txt",
         "browser_download_url": "https://dl/checksums.txt",
         "size": 130},
        {"name": "DotaAssist-Setup.exe",
         "browser_download_url": "https://dl/Setup.exe",
         "size": 9999},
    ],
}


class _Resp:
    """Минимальный суррогат httpx.Response для check()."""
    def __init__(self, payload, code=200):
        self._payload, self.status_code = payload, code

    def json(self):
        return self._payload


def _get(payload=REL, code=200):
    return mock.patch.object(updater.httpx, "get",
                             return_value=_Resp(payload, code))


class Ver(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(updater._ver("v1.2.3"), (1, 2, 3))
        self.assertEqual(updater._ver("1.2"), (1, 2))
        self.assertEqual(updater._ver("junk"), (0,))
        self.assertEqual(updater._ver(""), (0,))
        self.assertGreater(updater._ver("v1.2.0"), updater._ver("1.1.9"))


class Check(unittest.TestCase):
    def test_dev_short_circuits(self):
        with mock.patch.object(updater, "current_version",
                               return_value="dev"), _get() as g:
            self.assertIsNone(updater.check())
            g.assert_not_called()          # dev не ходит в сеть

    def test_newer_release_parsed(self):
        with mock.patch.object(updater, "current_version",
                               return_value="1.0.0"), _get():
            info = updater.check()
        self.assertEqual(info["tag"], "v1.2.0")
        self.assertEqual(info["url"], "https://dl/DotaAssist.exe")
        self.assertEqual(info["size"], 4096)
        self.assertEqual(info["checksums_url"],
                         "https://dl/checksums.txt")

    def test_no_checksums_asset(self):
        rel = {"tag_name": "v1.2.0", "assets": [REL["assets"][0]]}
        with mock.patch.object(updater, "current_version",
                               return_value="1.0.0"), _get(rel):
            info = updater.check()
        self.assertIsNotNone(info)
        self.assertNotIn("checksums_url", info)

    def test_older_or_equal(self):
        with mock.patch.object(updater, "current_version",
                               return_value="1.2.0"), _get():
            self.assertIsNone(updater.check())

    def test_http_error_and_exception(self):
        with mock.patch.object(updater, "current_version",
                               return_value="1.0.0"), _get(code=404):
            self.assertIsNone(updater.check())
        with mock.patch.object(updater, "current_version",
                               return_value="1.0.0"), \
             mock.patch.object(updater.httpx, "get",
                               side_effect=OSError("нет сети")):
            self.assertIsNone(updater.check())


class Apply(unittest.TestCase):
    def test_not_frozen_returns_false(self):
        msgs = []
        self.assertFalse(
            updater.apply_update("https://x/DotaAssist.exe", msgs.append))
        self.assertTrue(msgs)              # «только для exe-сборки»


class ParseChecksums(unittest.TestCase):
    TXT = ("a" * 64 + "  DotaAssist.exe\n"
           + "b" * 64 + "  DotaAssist-Setup.exe\n")

    def test_finds_by_name(self):
        self.assertEqual(updater._parse_checksums(self.TXT, "DotaAssist.exe"),
                         "a" * 64)
        self.assertIsNone(updater._parse_checksums(self.TXT, "other.exe"))


class Verify(unittest.TestCase):
    def test_ok_size_and_hash(self):
        data = b"fake exe payload" * 100
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.exe"
            p.write_bytes(data)
            sha = hashlib.sha256(data).hexdigest()
            self.assertIsNone(updater._verify(p, len(data), sha))
            self.assertIsNone(updater._verify(p, 0, sha))   # size не задан

    def test_bad_size(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.exe"
            p.write_bytes(b"abc")
            sha = hashlib.sha256(b"abc").hexdigest()
            self.assertIsNotNone(updater._verify(p, 999, sha))

    def test_bad_hash_empty_hash_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.exe"
            p.write_bytes(b"abc")
            self.assertIsNotNone(updater._verify(p, 3, "0" * 64))
            self.assertIsNotNone(updater._verify(p, 3, ""))
            self.assertIsNotNone(
                updater._verify(Path(d) / "no.exe", 0, "0" * 64))


if __name__ == "__main__":
    unittest.main()
