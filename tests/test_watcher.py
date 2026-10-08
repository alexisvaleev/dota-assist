"""Антифликер: герой засчитывается после 2 подряд одинаковых кадров.
Пропускается, если нет cv2/mss (лёгкий CI-джоб их не ставит)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

try:
    import numpy as np                          # noqa
    from draft_watcher import DraftWatcher      # noqa
    OK = True
except Exception:
    OK = False


@unittest.skipUnless(OK, "нет cv2/mss")
class Stable(unittest.TestCase):
    def setUp(self):
        self.w = DraftWatcher(on_change=lambda s: None)
        self.w.cal = {"team_left": {"slots": []}, "team_right": {"slots": []}}

    def test_two_consecutive(self):
        k = ("e", 0)
        self.assertIsNone(self.w._stable(k, "axe"))       # 1 кадр — нет
        self.assertEqual(self.w._stable(k, "axe"), "axe")  # 2 подряд — да
        self.assertEqual(self.w._stable(k, "axe"), "axe")

    def test_flicker_rejected(self):
        w = DraftWatcher(on_change=lambda s: None)
        k = ("e", 1)
        self.assertIsNone(w._stable(k, "axe"))
        self.assertIsNone(w._stable(k, "pudge"))
        self.assertIsNone(w._stable(k, "axe"))
        self.assertIsNone(w._stable(k, "pudge"))


class _QRec:
    """Фейковый распознаватель: отдаёт результаты hero_top2 по очереди."""
    threshold = 0.5

    def __init__(self, out):
        self.out = list(out)

    def hero_top2(self, crop):
        return self.out.pop(0) if self.out else (None, 0.0, 0.0)


@unittest.skipUnless(OK, "нет cv2/mss")
class ReadSlots(unittest.TestCase):
    """min_margin, подсчёт unknown-слотов и честная confidence."""

    def setUp(self):
        self.w = DraftWatcher(on_change=lambda s: None)
        self.w.cal = {"team_left": {"slots": []},
                      "team_right": {"slots": []}}
        self.w.min_margin = 0.06
        # шум: std >> 8, т.е. слот «не пустой»
        self.img = np.random.RandomState(1).randint(
            0, 255, (20, 20, 3), dtype=np.uint8)
        self.slots = [[0, 0, 10, 10], [10, 0, 10, 10]]

    def test_low_margin_is_unknown(self):
        # слот 0: score высокий, но margin < min_margin -> не доверяем
        self.w.rec = _QRec([
            ("axe", 0.90, 0.01), ("pudge", 0.90, 0.50),
            ("axe", 0.90, 0.01), ("pudge", 0.90, 0.50),
        ])
        self.w._read_slots(self.img, self.slots, "e")
        heroes, unk, worst = self.w._read_slots(self.img, self.slots, "e")
        self.assertEqual(heroes, [None, "pudge"])
        self.assertEqual(unk, [0])
        self.assertAlmostEqual(worst, 0.90)

    def _tick_watcher(self, rec_results):
        seen = []
        w = DraftWatcher(on_change=seen.append)
        w.min_margin = 0.06
        w.cal = {"resolution": [20, 20],
                 "team_left": {"slots": self.slots},
                 "team_right": {"slots": self.slots},
                 "bans": []}
        w.rec = _QRec(rec_results)
        w._grab = lambda sct: self.img
        return w, seen

    def test_tick_confidence_and_unknown(self):
        # my_side=radiant (default): enemy=team_right("e"), ally=team_left("a")
        w, seen = self._tick_watcher([
            ("axe", 0.90, 0.50), (None, 0.30, 0.10),     # enemy slots
            ("pudge", 0.80, 0.50), (None, 0.30, 0.10),   # ally slots
        ])
        # один кадр уже в истории -> герой засчитывается сразу
        w._history[("e", 0)] = ["axe"]
        w._history[("a", 0)] = ["pudge"]
        w._tick(None)
        self.assertEqual(len(seen), 1)
        st = seen[0]
        self.assertEqual(st["enemy_picks"], ["axe"])
        self.assertEqual(st["ally_picks"], ["pudge"])
        self.assertEqual(st["bans"], [])
        self.assertEqual(st["unknown_slots"], 2)   # 1 enemy + 1 ally
        # min(0.9, 0.8) * 2 распознанных / 4 занятых слота
        self.assertAlmostEqual(st["confidence"], 0.4)

    def test_nothing_recognized_zero_confidence(self):
        w, seen = self._tick_watcher([(None, 0.30, 0.10)] * 4)
        w._tick(None)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["confidence"], 0.0)
        self.assertEqual(seen[0]["unknown_slots"], 4)   # 2 + 2, обе стороны


if __name__ == "__main__":
    unittest.main()
