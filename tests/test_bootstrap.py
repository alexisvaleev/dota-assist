"""Тесты свежести кэша, решений bootstrap и Recognizer.reload().

Без сети и Qt: fetch_data/fetch_icons подменяются фейками в sys.modules,
DOTA_ASSIST_HOME указывает на tempdir — user_dir()/layered_dir() смотрят
туда, репо остаётся запасным слоем (в нём нет heroes.json — не мешает).
"""
import json
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

# Тестовый процесс всегда без дисплея: форсируем headless-платформу Qt
# до импорта соседних модулей с PyQt6 — их setdefault("QT_QPA_PLATFORM")
# бессилен, если в шелле переменная уже выставлена (напр. wayland).
os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import bootstrap                     # noqa: E402

try:
    import recognizer               # noqa: E402  (тащит cv2)
except Exception:
    recognizer = None

DAY = 86400


def write_json(d: Path, name: str, obj):
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(obj), encoding="utf-8")


def core_files(d: Path, fetched_at=None):
    """heroes.json+meta.json. fetched_at — ISO-строка в _meta (формат
    старых кэшей) либо None — файлы вообще без метки."""
    wrap = {"data": {}} if fetched_at is None \
        else {"_meta": {"fetched_at": fetched_at}, "data": {}}
    write_json(d, "heroes.json", wrap)
    write_json(d, "meta.json", wrap)


def iso(ts: float) -> str:
    """Формат engine.dataload.now_iso(): локальное время без таймзоны."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts))


class EnvHome(unittest.TestCase):
    """DOTA_ASSIST_HOME -> tempdir на время теста."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.tmp = Path(self.td.name)
        self._old = os.environ.get("DOTA_ASSIST_HOME")
        os.environ["DOTA_ASSIST_HOME"] = str(self.tmp)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("DOTA_ASSIST_HOME", None)
        else:
            os.environ["DOTA_ASSIST_HOME"] = self._old
        self.td.cleanup()


class DataReady(EnvHome):
    def test_requires_both_files(self):
        d = self.tmp / "data"
        self.assertFalse(bootstrap.data_ready(d))
        write_json(d, "heroes.json", {"data": {}})
        self.assertFalse(bootstrap.data_ready(d))
        write_json(d, "meta.json", {"data": {}})
        self.assertTrue(bootstrap.data_ready(d))

    def test_ready_via_env_layers(self):
        self.assertFalse(bootstrap.data_ready())
        core_files(self.tmp / "data")
        self.assertTrue(bootstrap.data_ready())


class Freshness(EnvHome):
    def test_marker_fresh_and_stale(self):
        d = self.tmp / "data"
        core_files(d)
        now = time.time()
        write_json(d, "_meta.json", {"fetched_at": now})
        self.assertTrue(bootstrap._is_fresh(d, now))
        self.assertTrue(bootstrap._is_fresh(
            d, now + bootstrap.REFRESH_DAYS * DAY - 1))
        self.assertFalse(bootstrap._is_fresh(
            d, now + bootstrap.REFRESH_DAYS * DAY + 1))
        self.assertFalse(bootstrap._is_fresh(d, now + 10 * DAY))

    def test_future_stamp_is_fresh(self):
        # часы сбились вперёд — не повод перекачивать каждый запуск
        d = self.tmp / "data"
        core_files(d)
        now = time.time()
        write_json(d, "_meta.json", {"fetched_at": now + DAY})
        self.assertTrue(bootstrap._is_fresh(d, now))

    def test_no_timestamp_is_stale(self):
        # кэш без меток (дописан вручную/очень старый) — протухший
        d = self.tmp / "data"
        core_files(d)
        self.assertIsNone(bootstrap.read_fetched_at(d))
        self.assertFalse(bootstrap._is_fresh(d))

    def test_missing_files_not_fresh(self):
        self.assertFalse(bootstrap._is_fresh(self.tmp / "data"))

    def test_iso_fallback(self):
        # кэш до появления _meta.json: метка внутри heroes/meta
        d = self.tmp / "data"
        now = time.time()
        core_files(d, fetched_at=iso(now - DAY))
        got = bootstrap.read_fetched_at(d)
        # delta: naive-ISO→epoch — до часа разницы на DST-переходах
        self.assertAlmostEqual(got, now - DAY, delta=3700)
        self.assertTrue(bootstrap._is_fresh(d, now))
        self.assertFalse(bootstrap._is_fresh(d, now + 2 * DAY))

    def test_marker_beats_file_meta(self):
        d = self.tmp / "data"
        now = time.time()
        core_files(d, fetched_at=iso(now - 100 * DAY))
        write_json(d, "_meta.json", {"fetched_at": now})
        self.assertAlmostEqual(bootstrap.read_fetched_at(d), now, delta=1)

    def test_broken_marker_falls_back(self):
        d = self.tmp / "data"
        now = time.time()
        core_files(d, fetched_at=iso(now))
        (d / "_meta.json").write_text("{not json", encoding="utf-8")
        self.assertAlmostEqual(bootstrap.read_fetched_at(d), now, delta=3700)
        self.assertTrue(bootstrap._is_fresh(d, now))

    def test_garbage_stamp_is_stale(self):
        d = self.tmp / "data"
        core_files(d)
        write_json(d, "_meta.json", {"fetched_at": "не дата"})
        self.assertIsNone(bootstrap.read_fetched_at(d))
        self.assertFalse(bootstrap._is_fresh(d))

    def test_data_fresh_layered(self):
        d = self.tmp / "data"
        core_files(d)
        self.assertFalse(bootstrap.data_fresh())
        write_json(d, "_meta.json", {"fetched_at": time.time()})
        self.assertTrue(bootstrap.data_fresh())
        write_json(d, "_meta.json",
                   {"fetched_at": time.time() - 10 * DAY})
        self.assertFalse(bootstrap.data_fresh())


class IconsReady(EnvHome):
    def _mk(self, d: Path, heroes: int, with_png: bool = True):
        for i in range(heroes):
            hd = d / f"hero_{i:03d}"
            hd.mkdir(parents=True)
            if with_png:
                (hd / "icon.png").write_bytes(b"\x89PNGfake")

    def test_missing_dir(self):
        self.assertFalse(bootstrap.icons_ready(self.tmp / "nope"))

    def test_below_threshold(self):
        d = self.tmp / "data" / "icons"
        self._mk(d, 3)
        self.assertFalse(bootstrap.icons_ready(d))      # < 100

    def test_threshold(self):
        d = self.tmp / "data" / "icons"
        self._mk(d, 3)
        with mock.patch.object(bootstrap, "ICON_MIN_HEROES", 3):
            self.assertTrue(bootstrap.icons_ready(d))
        with mock.patch.object(bootstrap, "ICON_MIN_HEROES", 4):
            self.assertFalse(bootstrap.icons_ready(d))

    def test_empty_hero_dirs_dont_count(self):
        # папка без png — fetch_icons всё равно будет её качать
        d = self.tmp / "data" / "icons"
        self._mk(d, 3, with_png=False)
        with mock.patch.object(bootstrap, "ICON_MIN_HEROES", 1):
            self.assertFalse(bootstrap.icons_ready(d))

    def test_env_layer(self):
        d = self.tmp / "data" / "icons"
        self._mk(d, 2)
        with mock.patch.object(bootstrap, "ICON_MIN_HEROES", 2):
            self.assertTrue(bootstrap.icons_ready())


class BootstrapFlow(EnvHome):
    """Оркестрация bootstrap(): что и когда скачивается, без сети."""

    def setUp(self):
        super().setUp()
        self.calls = {"data": [], "icons": 0, "done": 0}
        fd = types.ModuleType("fetch_data")
        fd.main = lambda argv=None: self.calls["data"].append(argv)
        fi = types.ModuleType("fetch_icons")
        fi.main = lambda: self.calls.__setitem__(
            "icons", self.calls["icons"] + 1)
        self.mods = {"fetch_data": fd, "fetch_icons": fi}

    def _mk_icons(self, n: int):
        d = self.tmp / "data" / "icons"
        for i in range(n):
            hd = d / f"hero_{i:03d}"
            hd.mkdir(parents=True)
            (hd / "icon.png").write_bytes(b"\x89PNG")

    def _fresh_data(self):
        d = self.tmp / "data"
        core_files(d)
        write_json(d, "_meta.json", {"fetched_at": time.time()})

    def _stale_data(self):
        d = self.tmp / "data"
        core_files(d)
        write_json(d, "_meta.json",
                   {"fetched_at": time.time() - 10 * DAY})

    def _boom(self, *a, **kw):
        raise RuntimeError("no net")

    def run_boot(self):
        with mock.patch.dict(sys.modules, self.mods):
            bootstrap.bootstrap(
                status_cb=lambda m: None,
                on_done=lambda: self.calls.__setitem__(
                    "done", self.calls["done"] + 1))

    def test_noop_when_all_fresh(self):
        self._fresh_data()
        self._mk_icons(2)
        self.mods["fetch_data"].main = self._boom   # не должны дёргаться
        self.mods["fetch_icons"].main = self._boom
        with mock.patch.object(bootstrap, "ICON_MIN_HEROES", 2):
            self.run_boot()
        self.assertEqual(self.calls["done"], 1)

    def test_stale_data_refetched(self):
        self._stale_data()
        self._mk_icons(2)
        with mock.patch.object(bootstrap, "ICON_MIN_HEROES", 2):
            self.run_boot()
        self.assertEqual(self.calls["data"], [[]])
        self.assertEqual(self.calls["icons"], 0)
        self.assertEqual(self.calls["done"], 1)

    def test_missing_data_and_icons_fetched(self):
        self.run_boot()                             # пустой tmp
        self.assertEqual(self.calls["data"], [[]])
        self.assertEqual(self.calls["icons"], 1)
        self.assertEqual(self.calls["done"], 1)

    def test_fresh_data_but_missing_icons(self):
        # баг: раньше иконки качались только вместе с данными
        self._fresh_data()
        self.run_boot()
        self.assertEqual(self.calls["data"], [])
        self.assertEqual(self.calls["icons"], 1)
        self.assertEqual(self.calls["done"], 1)

    def test_fetch_failure_no_cache(self):
        self.mods["fetch_data"].main = self._boom
        self.run_boot()
        self.assertEqual(self.calls["icons"], 0)    # без кэша — стоп
        self.assertEqual(self.calls["done"], 0)

    def test_fetch_failure_stale_cache_survives(self):
        self._stale_data()
        self.mods["fetch_data"].main = self._boom
        self.run_boot()
        self.assertEqual(self.calls["icons"], 1)    # иконки пробуем всё равно
        self.assertEqual(self.calls["done"], 1)

    def test_icons_failure_nonfatal(self):
        self._fresh_data()
        self.mods["fetch_icons"].main = self._boom
        self.run_boot()
        self.assertEqual(self.calls["done"], 1)

    def test_icons_systemexit_tolerated(self):
        # fetch_icons делает sys.exit, если не нашёл heroes.json
        self._fresh_data()
        self.mods["fetch_icons"].main = lambda: sys.exit("no heroes.json")
        self.run_boot()
        self.assertEqual(self.calls["done"], 1)


class Stamp(EnvHome):
    def test_stamp_written_and_readable(self):
        # fetch_data резолвит DATA при импорте — импортируем уже под env
        sys.modules.pop("fetch_data", None)
        import fetch_data
        before = time.time()
        fetch_data.stamp_fetched()
        marker = self.tmp / "data" / "_meta.json"
        self.assertTrue(marker.is_file())
        ts = json.loads(marker.read_text(encoding="utf-8"))["fetched_at"]
        self.assertGreaterEqual(ts, before)
        self.assertLessEqual(ts, time.time())
        # bootstrap видит такой кэш свежим
        core_files(self.tmp / "data")
        self.assertTrue(bootstrap.data_fresh())


@unittest.skipUnless(recognizer, "cv2 недоступен")
class RecognizerReload(EnvHome):
    def _mk_icon(self, hero: str, seed: int = 0) -> Path:
        rng = recognizer.np.random.default_rng(seed)
        img = rng.integers(0, 256, (32, 32, 3), dtype=recognizer.np.uint8)
        d = self.tmp / "data" / "icons" / hero
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{hero}.png"
        self.assertTrue(recognizer.cv2.imwrite(str(p), img))
        return p

    def test_lazy_dirs_loads_from_user_dir(self):
        # icon_dirs() резолвится при _load, а не при импорте модуля —
        # иконки, появившиеся после импорта, видны
        self._mk_icon("antimage")
        rec = recognizer.Recognizer()
        self.assertIn("antimage", rec.hero_templates)

    def test_reload_picks_up_new_icons(self):
        self._mk_icon("antimage")
        rec = recognizer.Recognizer()
        self.assertEqual(set(rec.hero_templates), {"antimage"})
        self._mk_icon("crystal_maiden", seed=1)
        rec.reload()
        self.assertEqual(set(rec.hero_templates),
                         {"antimage", "crystal_maiden"})

    def test_reload_clears_scaled_cache(self):
        p = self._mk_icon("antimage")
        rec = recognizer.Recognizer()
        rec.hero(recognizer.cv2.imread(str(p)))   # заполняет _scaled
        self.assertTrue(rec._scaled)
        rec.reload()
        self.assertFalse(rec._scaled)

    def test_recognizes_own_template(self):
        p = self._mk_icon("antimage")
        rec = recognizer.Recognizer()
        name, score = rec.hero(recognizer.cv2.imread(str(p)))
        self.assertEqual(name, "antimage")
        self.assertGreaterEqual(score, rec.threshold)

    def test_reload_empty_dir_no_crash(self):
        (self.tmp / "data" / "icons").mkdir(parents=True)
        rec = recognizer.Recognizer()
        rec.reload()                              # не должно падать
        self.assertEqual(rec.hero_templates, {})

    def test_missing_icons_dir_no_crash(self):
        rec = recognizer.Recognizer()
        rec.reload()
        name, score, margin = rec.hero_top2(
            recognizer.np.zeros((16, 16, 3), recognizer.np.uint8))
        self.assertIsNone(name)


if __name__ == "__main__":
    unittest.main()
