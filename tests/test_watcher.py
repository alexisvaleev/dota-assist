"""Антифликер: герой засчитывается после 2 подряд одинаковых кадров.
Пропускается, если нет cv2/mss (лёгкий CI-джоб их не ставит)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

try:
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


if __name__ == "__main__":
    unittest.main()
